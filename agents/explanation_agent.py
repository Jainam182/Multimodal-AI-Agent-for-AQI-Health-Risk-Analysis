"""
agents/explanation_agent.py
────────────────────────────
All inputs are plain dict payloads. LLM path + rule-based fallback.
"""

# ─── Imports ──────────────────────────────────────────────────────────────────
from __future__ import annotations
from typing import Dict, List, Optional

from agents.base_agent import BaseAgent
from config import (
    GROQ_API_KEY, LLM_MAX_TOKENS, LLM_MODEL, LLM_PROVIDER,
    LLM_TEMPERATURE, OPENAI_API_KEY, PERSONAS,
)
from schemas.agent_messages import AgentName, ExplanationAgentOutput, MessageStatus
from utils.logger import get_logger
from utils.retry import llm_retry

logger = get_logger("ExplanationAgent")


# ─── Explanation agent — narrative summaries (LLM with rule-based fallback) ──
class ExplanationAgent(BaseAgent):
    agent_name = AgentName.EXPLANATION

    # ─── BaseAgent contract: produce the narrative payload ───────────────────
    def _execute(
        self,
        message_id: str,
        data_output=None,
        gis_output=None,
        health_output=None,
        query: Optional[str] = None,
        city: str = "Mumbai",
        persona: Optional[str] = None,
        **kwargs,
    ) -> ExplanationAgentOutput:

        # Unwrap all inputs to plain dicts
        data_p   = self._unwrap(data_output)
        gis_p    = self._unwrap(gis_output)
        health_p = self._unwrap(health_output)
        city     = data_p.get("city") or gis_p.get("city") or health_p.get("city") or city

        logger.info(f"ExplanationAgent: city={city}, persona={persona}, query='{query}'")

        # RAG context — pull relevant prior summaries from ChromaDB if the user asked something specific.
        rag_context = ""
        if query:
            try:
                from data.vector_store import vector_store
                rag_context = vector_store.get_context_for_query(query, city)
            except Exception:
                pass

        structured = self._build_context(gis_p, health_p, city, persona)

        if self._llm_available():
            try:
                exp = self._llm_explain(query or "", structured, rag_context, city, persona)
            except Exception as e:
                logger.warning(f"LLM explanation failed: {e}. Using rule-based fallback.")
                exp = self._rule_based_explain(gis_p, health_p, city, persona)
        else:
            exp = self._rule_based_explain(gis_p, health_p, city, persona)

        return ExplanationAgentOutput(
            message_id=message_id,
            status=MessageStatus.SUCCESS,
            payload={
                "summary":             exp.get("summary", ""),
                "spatial_explanation": exp.get("spatial", ""),
                "health_explanation":  exp.get("health", ""),
                "recommendations":     exp.get("recommendations", []),
                "persona_summaries":   exp.get("persona_summaries", {}),
                "alert_text":          exp.get("alert") or "",
                "confidence":          0.9 if self._llm_available() else 0.7,
            },
        )

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _unwrap(self, output) -> dict:
        if output is None:
            return {}
        if isinstance(output, dict):
            return output
        if hasattr(output, "payload"):
            p = output.payload
            return p if isinstance(p, dict) else {}
        return {}

    def _llm_available(self) -> bool:
        return bool(GROQ_API_KEY or OPENAI_API_KEY)

    # ─── LLM path ─────────────────────────────────────────────────────────────

    @llm_retry
    def _llm_explain(self, query, structured, rag_context, city, persona) -> Dict:
        system_prompt = """You are an expert air quality health analyst.
Convert structured AQI analysis data into clear, actionable natural language.
Rules: Be concise. Lead with the most health-relevant insight.
Include specific, actionable recommendations. Do NOT invent data.
Respond in this exact JSON format (no markdown fences):
{
  "summary": "2-3 sentence overall summary",
  "spatial": "1-2 sentence geographic explanation",
  "health": "2-3 sentence health risk explanation",
  "recommendations": ["action 1", "action 2", "action 3"],
  "persona_summaries": {"persona_key": "summary text"},
  "alert": "alert message or null"
}"""
        user_msg = (
            f"Query: {query or 'General AQI and health analysis'}\n"
            f"City: {city}\nPersona: {persona or 'all personas'}\n\n"
            f"Analysis Data:\n{structured}\n\n"
            f"Prior Context:\n{rag_context or 'None'}\n\n"
            "Generate explanations."
        )
        import json
        if LLM_PROVIDER == "groq" and GROQ_API_KEY:
            from groq import Groq
            resp = Groq(api_key=GROQ_API_KEY).chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role":"system","content":system_prompt},{"role":"user","content":user_msg}],
                temperature=LLM_TEMPERATURE, max_tokens=LLM_MAX_TOKENS,
            )
            content = resp.choices[0].message.content.strip()
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        elif OPENAI_API_KEY:
            from openai import OpenAI
            resp = OpenAI(api_key=OPENAI_API_KEY).chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role":"system","content":system_prompt},{"role":"user","content":user_msg}],
                temperature=LLM_TEMPERATURE, max_tokens=LLM_MAX_TOKENS,
                response_format={"type":"json_object"},
            )
            return json.loads(resp.choices[0].message.content)
        raise RuntimeError("No LLM available")

    # ─── Rule-based fallback ──────────────────────────────────────────────────

    def _rule_based_explain(self, gis_p: dict, health_p: dict, city: str, persona: Optional[str]) -> Dict:
        parts = []
        spatial = gis_p.get("spatial_summary", "")
        health  = ""
        recommendations = []
        persona_summaries = {}
        alert = None

        avg_aqi = gis_p.get("avg_aqi") or health_p.get("aqi", 0)
        if avg_aqi:
            parts.append(f"In {city}, the average AQI is {avg_aqi:.0f}.")

        hotspots = gis_p.get("hotspot_stations", [])
        if hotspots:
            names = [h.get("station_name","?") for h in hotspots[:3]]
            parts.append(f"Hotspot areas include: {', '.join(names)}.")

        # Health section
        risks = health_p.get("persona_risks", {})
        if isinstance(risks, dict) and risks:
            worst = max(risks.values(), key=lambda r: r.get("risk_score",0))
            health = (
                f"At AQI {avg_aqi:.0f}, {worst.get('persona_label','?')} face "
                f"{worst.get('risk_level','?').lower()} health risk "
                f"(score {worst.get('risk_score',0):.1f}/10). "
                f"Watch for: {', '.join((worst.get('symptoms') or ['N/A'])[:2])}."
            )
            recommendations = (worst.get("preventive_actions") or [])[:4]
            for pk, pr in risks.items():
                icon = PERSONAS.get(pk, {}).get("icon", "")
                persona_summaries[pk] = (
                    f"{icon} {pr.get('persona_label',pk)}: "
                    f"{pr.get('risk_level','?')} risk. "
                    f"{pr.get('outdoor_recommendation','')}. "
                    f"Symptoms: {', '.join((pr.get('symptoms') or ['none'])[:2])}."
                )

        if health_p.get("alert_triggered"):
            alert = health_p.get("alert_message", "")

        if not recommendations:
            recommendations = [
                "Monitor AQI throughout the day",
                "Limit outdoor activity during peak traffic hours (8–10am, 6–8pm)",
                "Use HEPA air purifiers indoors",
                "Stay hydrated to support respiratory health",
            ]

        return {
            "summary":           " ".join(parts) or f"AQI analysis complete for {city}.",
            "spatial":           spatial,
            "health":            health,
            "recommendations":   recommendations,
            "persona_summaries": persona_summaries,
            "alert":             alert,
        }

    # ─── Context builder ──────────────────────────────────────────────────────

    def _build_context(self, gis_p: dict, health_p: dict, city: str, persona: Optional[str]) -> str:
        lines = [f"City: {city}"]
        if gis_p:
            lines.append(f"Avg AQI: {gis_p.get('avg_aqi', 0):.1f}")
            lines.append(f"Worst Station: {gis_p.get('max_aqi_station','?')}")
            lines.append(f"Best Station: {gis_p.get('min_aqi_station','?')}")
            for c in gis_p.get("clusters", [])[:2]:
                lines.append(f"Cluster AQI {c.get('avg_aqi',0):.0f} – stations: {', '.join(c.get('stations',[])[:3])}")
        if health_p:
            lines.append(f"Overall AQI: {health_p.get('aqi',0):.1f}")
            if health_p.get("alert_triggered"):
                lines.append(f"ALERT: {health_p.get('alert_message','')}")
            risks = health_p.get("persona_risks", {})
            if isinstance(risks, dict):
                for pk, pr in list(risks.items())[:5]:
                    lines.append(
                        f"{pr.get('persona_label',pk)}: {pr.get('risk_level','?')} "
                        f"({pr.get('risk_score',0):.1f}/10) – {pr.get('outdoor_recommendation','')}"
                    )
        return "\n".join(lines)
