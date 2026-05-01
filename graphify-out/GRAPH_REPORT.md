# Graph Report - Multimodal-AI-Agent-for-AQI-Health-Risk-Analysis  (2026-05-01)

## Corpus Check
- 23 files · ~31,154 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 409 nodes · 1246 edges · 37 communities detected
- Extraction: 38% EXTRACTED · 62% INFERRED · 0% AMBIGUOUS · INFERRED: 776 edges (avg confidence: 0.55)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]

## God Nodes (most connected - your core abstractions)
1. `AgentName` - 78 edges
2. `BaseAgent` - 66 edges
3. `MessageStatus` - 65 edges
4. `ReasoningAgent` - 61 edges
5. `DataAgent` - 54 edges
6. `AQICategory` - 51 edges
7. `LocationReading` - 50 edges
8. `PollutantReading` - 49 edges
9. `GISAgent` - 43 edges
10. `DataAgentOutput` - 43 edges

## Surprising Connections (you probably didn't know these)
- `Multi-Agent AQI Health Risk Analysis System Streamlit UI — Production Dashboard` --uses--> `ReasoningAgent`  [INFERRED]
  app.py → agents/reasoning_agent.py
- `Convert Plotly dict → Figure if needed. Returns None if invalid.` --uses--> `ReasoningAgent`  [INFERRED]
  app.py → agents/reasoning_agent.py
- `Load all agents once and cache.` --uses--> `ReasoningAgent`  [INFERRED]
  app.py → agents/reasoning_agent.py
- `Cached AQI historical fetch (prevents infinite API calls).` --uses--> `ReasoningAgent`  [INFERRED]
  app.py → agents/reasoning_agent.py
- `Production-safe fetch pipeline:     1. Try DB     2. Else cached API` --uses--> `ReasoningAgent`  [INFERRED]
  app.py → agents/reasoning_agent.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (55): ExplanationAgent, _llm_explain(), GISAgent, HealthAgent, agents/reasoning_agent.py ────────────────────────── Thin orchestrator shell — u, Extract an area/location name after 'near', 'of', 'around'., Extract a radius in km from natural language e.g. 'within 5km of Andheri'., Extract a radius in km from natural language e.g. 'within 5km of Andheri'. (+47 more)

### Community 1 - "Community 1"
Cohesion: 0.12
Nodes (69): ABC, BaseAgent, _execute(), agents/base_agent.py ───────────────────── Abstract base. run() accepts either:, Unified entry point.         If the first positional arg is an AgentMessage we u, Unified entry point.         If the first positional arg is an AgentMessage we u, agents/data_agent.py ───────────────────── Real-data AQI ingestion — aqi.in as p, Add real pollutant concentrations from Open-Meteo to every reading.          WAQ (+61 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (30): DataAgent, _fetch_openweather(), get_aqi_category(), Returns the full category dict {range, label, color, hex}., add_derived_features(), compute_aqi_from_pollutants(), compute_sub_index(), impute_missing_values() (+22 more)

### Community 3 - "Community 3"
Cohesion: 0.09
Nodes (38): Enum, _render_trend_charts(), AnalysisStep, AQICategory, HealthAgentOutput, schemas/agent_messages.py ────────────────────────── All agents communicate via, ReasoningPlan, RiskLevel (+30 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (38): aqi_badge(), fetch_historical_data_cached(), get_historical_data(), load_agents(), main(), Multi-Agent AQI Health Risk Analysis System Streamlit UI — Production Dashboard, Render GIS results from session_state — called every rerun., # IMPORTANT: Convert Folium Map objects → HTML strings before storing, (+30 more)

### Community 5 - "Community 5"
Cohesion: 0.16
Nodes (10): AgentLogModel, AQIReadingModel, Base, DatabaseManager, HealthReportModel, data/database.py ───────────────── SQLAlchemy-based SQLite database manager. Sch, CRUD interface for all AQI system tables., Bulk insert AQI readings, skip existing (same station + timestamp). (+2 more)

### Community 6 - "Community 6"
Cohesion: 0.13
Nodes (9): data/vector_store.py ───────────────────── ChromaDB vector store for semantic se, Simple TF-style keyword overlap search for fallback., Convenience method to store an AQI summary document., Store a health analysis summary., Retrieve relevant context snippets for a user query.         Used by the Reasoni, ChromaDB-backed vector store with sentence-transformers embeddings.     Falls ba, Add a text document to the vector store., Semantic search for documents similar to the query.         Returns list of {"te (+1 more)

### Community 7 - "Community 7"
Cohesion: 0.16
Nodes (11): _aqi_advice_line(), _avg_aqi(), classify_intent(), decide_agents(), _decide_chart(), generate_response(), _llm_health_advice(), _llm_response() (+3 more)

### Community 8 - "Community 8"
Cohesion: 0.52
Nodes (6): diurnal_factor(), generate_mock_current_data(), generate_mock_historical_data(), generate_multi_station_snapshot(), generate_pollutants(), seasonal_factor()

### Community 9 - "Community 9"
Cohesion: 0.4
Nodes (3): get_logger(), utils/logger.py – Centralized logging configuration using loguru., Return a bound logger with component name context.

### Community 10 - "Community 10"
Cohesion: 1.0
Nodes (1): utils/retry.py – Retry decorator using tenacity for robust API calls.

### Community 11 - "Community 11"
Cohesion: 1.0
Nodes (1): Flat dict for payload["readings"] lists.

### Community 15 - "Community 15"
Cohesion: 1.0
Nodes (1): Compute CPCB sub-index for a single pollutant using linear interpolation.     Re

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (1): Compute composite AQI as the maximum sub-index across all available pollutants.

### Community 17 - "Community 17"
Cohesion: 1.0
Nodes (1): Normalize a raw DataFrame from any source to the canonical schema.     - Rename

### Community 18 - "Community 18"
Cohesion: 1.0
Nodes (1): Compute data quality metrics for a processed DataFrame.     Returns dict with co

### Community 19 - "Community 19"
Cohesion: 1.0
Nodes (1): Impute missing pollutant values using time-series interpolation.     Falls back

### Community 20 - "Community 20"
Cohesion: 1.0
Nodes (1): Add engineered features useful for health and GIS analysis.

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (1): Great-circle distance in kilometres between two lat/lon points.

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (1): Return (lat, lon) for a city name.     First checks local INDIAN_CITIES dict; fa

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (1): Return a bounding box [min_lat, min_lon, max_lat, max_lon] for a radius.

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (1): Validate lat/lon are within India's approximate bounds.

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (1): Generate deterministic mock coordinates for a station within a city.     Used wh

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (1): Filter a list of station dicts to those within radius_km of center.

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (1): Generate concise health advice using LLM — only for persona-specific guidance.

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (1): Return a bound logger with component name context.

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (1): Universal inter-agent envelope. payload is always a plain dict.

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (1): Flat dict for payload["readings"] lists.

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (1): ChromaDB-backed vector store with sentence-transformers embeddings.     Falls ba

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (1): Add a text document to the vector store.

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (1): Semantic search for documents similar to the query.         Returns list of {"te

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): Simple TF-style keyword overlap search for fallback.

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): Convenience method to store an AQI summary document.

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): Store a health analysis summary.

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (1): Retrieve relevant context snippets for a user query.         Used by the Reasoni

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (1): CRUD interface for all AQI system tables.

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (1): Bulk insert AQI readings, skip existing (same station + timestamp).

## Knowledge Gaps
- **75 isolated node(s):** `config.py – Central configuration, constants, and environment loading. All modul`, `Returns the full category dict {range, label, color, hex}.`, `Returns just the label string e.g. 'Good', 'Poor'.`, `tools/aqi_tools.py ────────────────── AQI calculation, pollutant normalization,`, `Compute CPCB sub-index for a single pollutant using linear interpolation.     Re` (+70 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 10`** (2 nodes): `retry.py`, `utils/retry.py – Retry decorator using tenacity for robust API calls.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 11`** (2 nodes): `.to_dict()`, `Flat dict for payload["readings"] lists.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 15`** (1 nodes): `Compute CPCB sub-index for a single pollutant using linear interpolation.     Re`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 16`** (1 nodes): `Compute composite AQI as the maximum sub-index across all available pollutants.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 17`** (1 nodes): `Normalize a raw DataFrame from any source to the canonical schema.     - Rename`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 18`** (1 nodes): `Compute data quality metrics for a processed DataFrame.     Returns dict with co`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 19`** (1 nodes): `Impute missing pollutant values using time-series interpolation.     Falls back`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 20`** (1 nodes): `Add engineered features useful for health and GIS analysis.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 21`** (1 nodes): `Great-circle distance in kilometres between two lat/lon points.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (1 nodes): `Return (lat, lon) for a city name.     First checks local INDIAN_CITIES dict; fa`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (1 nodes): `Return a bounding box [min_lat, min_lon, max_lat, max_lon] for a radius.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (1 nodes): `Validate lat/lon are within India's approximate bounds.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (1 nodes): `Generate deterministic mock coordinates for a station within a city.     Used wh`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (1 nodes): `Filter a list of station dicts to those within radius_km of center.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (1 nodes): `Generate concise health advice using LLM — only for persona-specific guidance.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (1 nodes): `Return a bound logger with component name context.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (1 nodes): `Universal inter-agent envelope. payload is always a plain dict.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (1 nodes): `Flat dict for payload["readings"] lists.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (1 nodes): `ChromaDB-backed vector store with sentence-transformers embeddings.     Falls ba`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (1 nodes): `Add a text document to the vector store.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `Semantic search for documents similar to the query.         Returns list of {"te`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `Simple TF-style keyword overlap search for fallback.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `Convenience method to store an AQI summary document.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `Store a health analysis summary.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `Retrieve relevant context snippets for a user query.         Used by the Reasoni`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `CRUD interface for all AQI system tables.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `Bulk insert AQI readings, skip existing (same station + timestamp).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ReasoningAgent` connect `Community 0` to `Community 1`, `Community 2`, `Community 4`, `Community 7`?**
  _High betweenness centrality (0.191) - this node is a cross-community bridge._
- **Why does `DataAgent` connect `Community 2` to `Community 0`, `Community 1`?**
  _High betweenness centrality (0.111) - this node is a cross-community bridge._
- **Why does `AgentName` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Are the 75 inferred relationships involving `AgentName` (e.g. with `VisualizationAgent` and `agents/visualization_agent.py ────────────────────────────── All inputs are plai`) actually correct?**
  _`AgentName` has 75 INFERRED edges - model-reasoned connections that need verification._
- **Are the 61 inferred relationships involving `BaseAgent` (e.g. with `VisualizationAgent` and `agents/visualization_agent.py ────────────────────────────── All inputs are plai`) actually correct?**
  _`BaseAgent` has 61 INFERRED edges - model-reasoned connections that need verification._
- **Are the 62 inferred relationships involving `MessageStatus` (e.g. with `VisualizationAgent` and `agents/visualization_agent.py ────────────────────────────── All inputs are plai`) actually correct?**
  _`MessageStatus` has 62 INFERRED edges - model-reasoned connections that need verification._
- **Are the 48 inferred relationships involving `ReasoningAgent` (e.g. with `Multi-Agent AQI Health Risk Analysis System Streamlit UI — Production Dashboard` and `Convert Plotly dict → Figure if needed. Returns None if invalid.`) actually correct?**
  _`ReasoningAgent` has 48 INFERRED edges - model-reasoned connections that need verification._