"""
data/vector_store.py
─────────────────────
ChromaDB vector store for semantic search over AQI summaries,
health reports, and past query results.
Enables context-aware retrieval augmented generation (RAG).
"""

# ─── Imports ──────────────────────────────────────────────────────────────────
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import CHROMA_PATH, ENABLE_VECTOR_SEARCH
from utils.logger import get_logger

logger = get_logger("vector_store")
Path(CHROMA_PATH).mkdir(parents=True, exist_ok=True)


# ─── Vector store with ChromaDB primary path + keyword fallback ───────────────
class VectorStore:
    """
    ChromaDB-backed vector store with sentence-transformers embeddings.
    Falls back to a simple in-memory keyword search if ChromaDB isn't available.
    """

    def __init__(self):
        self._client = None
        self._collection = None
        self._fallback_store: List[Dict] = []
        self._use_chroma = False

        if ENABLE_VECTOR_SEARCH:
            self._init_chroma()

    # ─── Backend initialization (chroma if available, fallback otherwise) ───
    def _init_chroma(self):
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            self._client = chromadb.PersistentClient(path=CHROMA_PATH)

            # Use sentence-transformers for embeddings (runs locally, free)
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )

            self._collection = self._client.get_or_create_collection(
                name="aqi_knowledge",
                embedding_function=ef,
                metadata={"description": "AQI summaries, health reports, spatial insights"},
            )
            self._use_chroma = True
            logger.info(f"ChromaDB initialized at {CHROMA_PATH}")
        except ImportError:
            logger.warning("ChromaDB or sentence-transformers not installed. Using fallback keyword search.")
        except Exception as e:
            logger.warning(f"ChromaDB init failed: {e}. Using fallback.")

    # ─── Public CRUD ────────────────────────────────────────────────────────
    def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Add a text document to the vector store."""
        metadata = metadata or {}
        metadata["added_at"] = datetime.utcnow().isoformat()

        if self._use_chroma and self._collection is not None:
            try:
                self._collection.upsert(
                    ids=[doc_id],
                    documents=[text],
                    metadatas=[metadata],
                )
                return
            except Exception as e:
                logger.warning(f"ChromaDB upsert failed: {e}")

        # Fallback: in-memory store
        self._fallback_store.append({
            "id": doc_id,
            "text": text,
            "metadata": metadata,
        })

    def search(
        self,
        query: str,
        n_results: int = 5,
        where: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Semantic search for documents similar to the query.
        Returns list of {"text": ..., "metadata": ..., "distance": ...}
        """
        if self._use_chroma and self._collection is not None:
            try:
                kwargs = {"query_texts": [query], "n_results": n_results}
                if where:
                    kwargs["where"] = where
                results = self._collection.query(**kwargs)

                output = []
                for i, (doc, meta, dist) in enumerate(zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                )):
                    output.append({"text": doc, "metadata": meta, "distance": dist})
                return output
            except Exception as e:
                logger.warning(f"ChromaDB query failed: {e}")

        # Keyword fallback
        return self._keyword_search(query, n_results)

    def _keyword_search(self, query: str, n_results: int) -> List[Dict]:
        """Simple TF-style keyword overlap search for fallback."""
        query_words = set(query.lower().split())
        scored = []
        for doc in self._fallback_store:
            doc_words = set(doc["text"].lower().split())
            overlap = len(query_words & doc_words)
            if overlap > 0:
                scored.append({"text": doc["text"], "metadata": doc["metadata"], "distance": 1.0 / (overlap + 1)})
        return sorted(scored, key=lambda x: x["distance"])[:n_results]

    # ─── Convenience wrappers for the agent layer ───────────────────────────
    def add_aqi_summary(self, city: str, station: str, aqi: float, summary: str, timestamp: str):
        """Convenience method to store an AQI summary document."""
        doc_id = f"aqi_{city}_{station}_{timestamp}".replace(" ", "_")
        self.add_document(
            doc_id=doc_id,
            text=summary,
            metadata={"type": "aqi_summary", "city": city, "station": station, "aqi": aqi, "timestamp": timestamp},
        )

    def add_health_summary(self, city: str, persona: str, risk_level: str, summary: str):
        """Store a health analysis summary."""
        doc_id = f"health_{city}_{persona}_{datetime.utcnow().date()}"
        self.add_document(
            doc_id=doc_id,
            text=summary,
            metadata={"type": "health_report", "city": city, "persona": persona, "risk_level": risk_level},
        )

    def get_context_for_query(self, query: str, city: Optional[str] = None) -> str:
        """
        Retrieve relevant context snippets for a user query.
        Used by the Reasoning and Explanation agents for RAG.
        """
        where = {"city": city} if city else None
        results = self.search(query, n_results=3, where=where)
        if not results:
            return ""
        snippets = [f"[Context {i+1}]: {r['text']}" for i, r in enumerate(results)]
        return "\n".join(snippets)

    @property
    def document_count(self) -> int:
        if self._use_chroma and self._collection:
            return self._collection.count()
        return len(self._fallback_store)


# ─── Module-level singleton — every caller imports `vector_store` from here ──
vector_store = VectorStore()
