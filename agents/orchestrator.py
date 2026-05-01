"""
agents/orchestrator.py
───────────────────────
Intelligent orchestration layer — decides which agents to call
based on query intent, then generates a minimal, conversational response.

Intent → Agent mapping:
  simple_aqi         → data_agent only
  health_query        → data_agent + health_agent
  hotspot_query       → data_agent + gis_agent
  comparison_query    → data_agent + gis_agent + health_agent
  trend_query         → data_agent (historical mode)
  recommendation_query→ data_agent + health_agent
  general_query       → data_agent
"""

# ─── Imports ──────────────────────────────────────────────────────────────────
from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Tuple

from config import GROQ_API_KEY, LLM_MODEL, LLM_PROVIDER, LLM_TEMPERATURE, OPENAI_API_KEY
from utils.logger import get_logger

logger = get_logger("Orchestrator")


# ─── Intent → required-agents map ─────────────────────────────────────────────
# Each intent declares which sub-agents must run before generate_response().
INTENTS = {
    "simple_aqi":          ["data_agent"],
    "health_query":        ["data_agent", "health_agent"],
    "hotspot_query":       ["data_agent", "gis_agent"],
    "gis_query":           ["data_agent", "gis_agent"],
    "comparison_query":    ["data_agent", "gis_agent", "health_agent"],
    "trend_query":         ["data_agent"],
    "recommendation_query":["data_agent", "health_agent"],
    "general_query":       ["data_agent"],
}


# ─── Intent classification rules ──────────────────────────────────────────────
# Ordered keyword → intent table; first match wins, so put most specific first.
INTENT_RULES: List[Tuple[List[str], str]] = [
    (["trend", "history", "historical", "past", "over time"], "trend_query"),
    (["hotspot", "dangerous area", "worst area", "polluted area",
      "map", "heatmap", "heat map", "spatial", "within", "nearby", "near"], "hotspot_query"),
    (["gis", "choropleth", "spatial map", "pollutant map",
      "pm2.5 map", "pm10 map", "no2 map", "so2 map", "o3 map",
      "heat map of", "heatmap of"], "gis_query"),
    (["compare", "comparison", "vs", "versus", "difference between"], "comparison_query"),
    (["health", "risk", "safe", "asthma", "elderly", "children", "pregnant",
      "best time", "when to go", "safe to run", "safe to walk", "safe to exercise",
      "mask", "indoor", "outdoor activity"], "health_query"),
    (["recommend", "advice", "precaution", "what should i do"], "recommendation_query"),
    (["aqi", "air quality", "pollution level"], "simple_aqi"),
]


# ─── Public: intent + agent routing ───────────────────────────────────────────
def classify_intent(query: str) -> str:
    q = query.lower().strip()
    for keywords, intent in INTENT_RULES:
        if any(kw in q for kw in keywords):
            return intent
    return "general_query"


def decide_agents(intent: str, query: str) -> List[str]:
    return INTENTS.get(intent, INTENTS["general_query"])


# ─── Public: response generation ──────────────────────────────────────────────
# Combines structured agent payloads into the final UI-bound response dict.
def generate_response(
    query: str,
    intent: str,
    city: str,
    data_payload: Dict,
    health_payload: Dict,
    gis_payload: Dict,
) -> Dict[str, Any]:

    # Aggregate the raw readings into a single AQI summary used by every branch below.
    readings = data_payload.get("readings", [])
    avg_aqi = _avg_aqi(readings)
    category = readings[0].get("aqi_category", "Unknown") if readings else "Unknown"

    alert_text = health_payload.get("alert_message") if health_payload.get("alert_triggered") else None

    # ── For GIS / hotspot queries: always use rule-based text so real station
    #    data appears in the response. The LLM tends to hallucinate generic text
    #    even when GIS context is provided. Append LLM health advice if available.
    if intent in ("hotspot_query", "gis_query"):
        text = _rule_based_response(
            intent, city, avg_aqi, category,
            readings, health_payload, gis_payload
        )
        # If health data is available, enhance with LLM-generated health advice
        if (health_payload and (GROQ_API_KEY or OPENAI_API_KEY)):
            try:
                health_text = _llm_health_advice(
                    query, city, avg_aqi, category, health_payload
                )
                if health_text:
                    text = text.strip() + "\n\n" + health_text
            except Exception as e:
                logger.warning(f"LLM health advice failed: {e}")

        return {
            "text": text,
            "alert": alert_text,
            "map": intent in ("hotspot_query", "gis_query"),
            "chart": _decide_chart(intent),
            "intent": intent,
            "city": city,
        }

    # ── For non-GIS queries: use LLM normally, fall back to rules if it fails ──
    if GROQ_API_KEY or OPENAI_API_KEY:
        try:
            text = _llm_response(
                query, intent, city, avg_aqi, category,
                data_payload, health_payload, gis_payload
            )
            return {
                "text": text,
                "alert": alert_text,
                "map": intent in ("hotspot_query", "gis_query"),
                "chart": _decide_chart(intent),
                "intent": intent,
                "city": city,
            }
        except Exception as e:
            logger.warning(f"LLM failed: {e}")

    # No LLM keys configured — deterministic rule-based response only.
    text = _rule_based_response(
        intent, city, avg_aqi, category,
        readings, health_payload, gis_payload
    )

    return {
        "text": text,
        "alert": alert_text,
        "map": intent in ("hotspot_query", "gis_query"),
        "chart": _decide_chart(intent),
        "intent": intent,
        "city": city,
    }


# ─── Private: LLM-backed response generation ──────────────────────────────────
def _llm_response(
    query, intent, city, avg_aqi, category,
    data_payload, health_payload, gis_payload
) -> str:

    # Build a structured context string from all available agent payloads.
    ctx = [
        f"City: {city}",
        f"AQI: {avg_aqi:.0f} ({category})"
    ]

    # GIS context — stations, hotspots, spatial summary
    if gis_payload and intent in ("hotspot_query", "gis_query"):
        readings = data_payload.get("readings", []) if data_payload else []
        hotspots = gis_payload.get("hotspot_stations", [])
        spatial_summary = gis_payload.get("spatial_summary", "")
        clusters = gis_payload.get("clusters", [])
        if hotspots:
            ctx.append(f"Hotspot stations: {', '.join(hotspots[:5])}")
        if spatial_summary:
            ctx.append(f"Spatial summary: {spatial_summary}")
        if clusters:
            ctx.append(f"Pollution clusters: {len(clusters)} detected")

    # Persona context
    if health_payload:
        persona = health_payload.get("persona", "General Population")
        ctx.append(f"User Persona: {persona}")

    # Map context — tell LLM a map is being shown
    if intent in ("hotspot_query", "gis_query"):
        ctx.append("A spatial heat map and station markers are being shown alongside this response.")
        readings = data_payload.get("readings", []) if data_payload else []
        if readings:
            top = sorted(readings, key=lambda r: r.get("aqi", 0), reverse=True)[:5]
            station_lines = [f"- {s.get('station_name')}: AQI {s.get('aqi')}" for s in top]
            ctx.append("Top polluted stations:\n" + "\n".join(station_lines))

    context = "\n".join(ctx)

    system = (
        "You are an AQI health assistant.\n"
        "- Keep answers short (1-3 sentences)\n"
        "- Tailor health advice to the user persona\n"
        "- Do NOT tell users to use external apps or websites\n"
        "- Always reference the actual station data and spatial analysis provided in the context\n"
        "- If a map is being shown, mention the key findings from it\n"
        "- Do NOT be generic\n"
    )

    user_msg = f"{context}\n\nUser: {query}"

    # Provider dispatch — Groq preferred for latency, OpenAI as fallback.
    if LLM_PROVIDER == "groq" and GROQ_API_KEY:
        from groq import Groq
        resp = Groq(api_key=GROQ_API_KEY).chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg}
            ],
            temperature=LLM_TEMPERATURE,
        )
        return resp.choices[0].message.content.strip()

    else:
        from openai import OpenAI
        resp = OpenAI(api_key=OPENAI_API_KEY).chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg}
            ],
            temperature=LLM_TEMPERATURE,
        )
        return resp.choices[0].message.content.strip()


def _llm_health_advice(
    query, city, avg_aqi, category, health_payload
) -> str:
    """Generate concise health advice using LLM — only for persona-specific guidance."""
    persona = health_payload.get("persona", "General Population")
    risks = health_payload.get("persona_risks", {})
    from tools.health_tools import resolve_persona_key
    persona_key = resolve_persona_key(persona)
    risk_info = risks.get(persona_key, next(iter(risks.values()), {})) if risks else {}
    risk_level = risk_info.get("risk_level", "Unknown")
    risk_score = risk_info.get("risk_score", 0)
    rec = risk_info.get("outdoor_recommendation", "")
    symptoms = risk_info.get("symptoms", [])
    mask = risk_info.get("mask_recommendation", "")

    system = (
        "You are an AQI health advisor. Keep answers to 2-3 sentences only.\n"
        "Do NOT mention external apps or websites.\n"
        "Do NOT repeat the city or AQI number — the user already knows them.\n"
    )

    user_msg = (
        f"Persona: {persona} | Risk: {risk_level} ({risk_score:.1f}/10) | "
        f"Recommendation: {rec} | Mask advice: {mask} | "
        f"Symptoms: {', '.join(symptoms[:3]) if symptoms else 'None'}.\n"
        f"User asked: {query}\n"
        f"Give a brief, specific health advisory."
    )

    try:
        if GROQ_API_KEY:
            from groq import Groq
            resp = Groq(api_key=GROQ_API_KEY).chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg}
                ],
                temperature=LLM_TEMPERATURE,
                max_tokens=200,
            )
            return resp.choices[0].message.content.strip()
        else:
            from openai import OpenAI
            resp = OpenAI(api_key=OPENAI_API_KEY).chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg}
                ],
                temperature=LLM_TEMPERATURE,
                max_tokens=200,
            )
            return resp.choices[0].message.content.strip()
    except Exception:
        return ""


# ─── Private: deterministic rule-based response (LLM-free fallback) ───────────
def _rule_based_response(
    intent, city, avg_aqi, category,
    readings, health_payload, gis_payload
) -> str:

    aqi_str = f"{avg_aqi:.0f} ({category})"

    if intent == "simple_aqi":
        return f"AQI in {city} is {aqi_str}. {_aqi_advice_line(avg_aqi)}"

    elif intent == "health_query":

        persona_label = health_payload.get("persona", "general population").lower()
        risks = (health_payload or {}).get("persona_risks", {})

        selected = None

        for r in risks.values():
            if r.get("persona_label", "").lower() == persona_label:
                selected = r
                break

        if not selected and risks:
            selected = max(risks.values(), key=lambda r: r.get("risk_score", 0))

        if not selected:
            return f"AQI in {city} is {aqi_str}"

        label = selected.get("persona_label")
        level = selected.get("risk_level")
        score = selected.get("risk_score", 0)
        rec = selected.get("outdoor_recommendation")
        mask = selected.get("mask_recommendation", "")
        symptoms = selected.get("symptoms", [])

        text = (
            f"AQI in {city} is {aqi_str}.\n\n"
            f"{label} are at **{level}** risk (score: {score:.1f}/10).\n\n"
            f"{rec}\n\n"
        )

        # Feature 2: Mask recommendation
        if mask:
            text += f"{mask}\n\n"

        # Predicted symptoms
        if symptoms and symptoms[0] != "No significant symptoms expected at current AQI":
            text += f"**Possible symptoms:** {', '.join(symptoms[:3])}.\n\n"

        # Feature 1: Hazard Index
        hi = health_payload.get("hazard_index", 0)
        if hi and hi > 0.5:
            hi_text = health_payload.get("hazard_interpretation", "")
            text += f"**Hazard Index:** {hi:.2f} — {hi_text}\n\n"

        # Feature 3: Synergy warnings
        synergies = health_payload.get("synergy_warnings", [])
        if synergies:
            text += "**⚗️ Pollutant Interactions:**\n"
            for sw in synergies:
                text += f"- 🧬 {sw}\n"

        return text

    elif intent == "hotspot_query":

        # Use GIS-filtered stations if available (radius-limited), else all readings
        gis_stations = gis_payload.get("stations") if gis_payload else None
        top_readings = sorted(
            gis_stations if gis_stations else readings,
            key=lambda x: x.get("aqi", 0), reverse=True
        )[:5]

        text = f"Most polluted areas in {city}:\n"
        for r in top_readings:
            text += f"- {r.get('station_name')} (AQI {r.get('aqi')})\n"

        # Enrich with GIS data if available
        clusters = gis_payload.get("clusters", []) if gis_payload else []
        hotspot_stations = gis_payload.get("hotspot_stations", []) if gis_payload else []
        spatial_summary = gis_payload.get("spatial_summary", "") if gis_payload else ""

        if clusters:
            text += f"\n**{len(clusters)} pollution cluster(s)** detected.\n"
        if hotspot_stations:
            text += f"**{len(hotspot_stations)} hotspot station(s)** (AQI > 200).\n"
        if spatial_summary:
            text += f"\n{spatial_summary}\n"

        return text

    elif intent == "gis_query":
        top = sorted(readings, key=lambda x: x.get("aqi", 0), reverse=True)[:5]
        text = f"Spatial analysis for {city}:\n"
        for r in top:
            text += f"- {r.get('station_name')}: AQI {r.get('aqi')}\n"
        if gis_payload.get("spatial_summary"):
            text += f"\n{gis_payload['spatial_summary']}"
        return text

    elif intent == "comparison_query":
        return "Comparison handled separately."

    elif intent == "recommendation_query":
        return f"AQI in {city} is {aqi_str}. {_aqi_advice_line(avg_aqi)}"

    return f"AQI in {city} is {aqi_str}."


# ─── Private: small helpers ───────────────────────────────────────────────────
def _avg_aqi(readings):
    if not readings:
        return 0
    vals = [r.get("aqi", 0) for r in readings]
    return sum(vals) / len(vals)


def _aqi_advice_line(aqi):
    if aqi <= 100:
        return "Air quality is acceptable."
    if aqi <= 200:
        return "Limit outdoor activity."
    if aqi <= 300:
        return "Avoid outdoor exposure."
    return "Stay indoors."


def _decide_chart(intent):
    if intent == "health_query":
        return "health"
    if intent in ("hotspot_query", "gis_query"):
        return "map"
    return None
