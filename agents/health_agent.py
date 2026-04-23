"""
agents/health_agent.py
───────────────────────
Health Agent: Deterministic health risk engine.
All persona data returned as plain dicts in payload.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, List, Optional

from agents.base_agent import BaseAgent
from config import PERSONAS, POLLUTANT_LIMITS, get_aqi_label
from schemas.agent_messages import (
    AgentName, HealthAgentOutput, MessageStatus, RiskLevel,
)
from tools.health_tools import (
    PERSONA_RULES,
    aqi_to_category,
    calculate_risk_score,
    compute_hazard_index,
    compute_synergy_penalty,
    get_mask_recommendation,
    get_outdoor_recommendation,
    get_pollutant_health_note,
)
from utils.logger import get_logger

logger = get_logger("HealthAgent")


class HealthAgent(BaseAgent):
    agent_name = AgentName.HEALTH

    def _execute(
        self,
        message_id: str,
        data_output=None,          # dict payload OR AgentMessage
        city: str = "Mumbai",
        aqi: Optional[float] = None,
        pollutants: Optional[Dict[str, float]] = None,
        station: Optional[str] = None,
        persona: Optional[str] = None,
        exposure_hours: float = 8.0,
        activity_level: str = "light",       # Feature 2
        environment: str = "outdoor",        # Feature 2
        **kwargs,
    ) -> HealthAgentOutput:

        # ── Resolve readings from flat dict payload ───────────────────────────
        readings = []
        if data_output is not None:
            if isinstance(data_output, dict):
                readings = data_output.get("readings", [])
                city = data_output.get("city", city)
            elif hasattr(data_output, "payload"):
                p = data_output.payload
                readings = (p.get("readings", []) if isinstance(p, dict) else [])
                city = (p.get("city", city) if isinstance(p, dict) else city)

        # Use median AQI across stations (representative city value, matches websites)
        if readings:
            import statistics
            aqi_values = sorted([float(r.get("aqi") or 0) for r in readings if r.get("aqi")])
            resolved_aqi = statistics.median(aqi_values) if aqi_values else 0.0
            # Pick name from the station closest to median
            ref = min(readings, key=lambda r: abs((r.get("aqi") or 0) - resolved_aqi))
            station = station or ref.get("station_name")

            # Aggregate pollutants: use median across all stations for each pollutant.
            # This gives a representative city-level concentration, not the worst case.
            resolved_pollutants = {}
            for poll_key in ["pm25", "pm10", "no2", "co", "so2", "o3"]:
                vals = [float(r.get(poll_key)) for r in readings
                        if r.get(poll_key) is not None and float(r.get(poll_key)) > 0]
                resolved_pollutants[poll_key] = statistics.median(vals) if vals else 0.0
        else:
            resolved_aqi = aqi or 0.0
            resolved_pollutants = pollutants or {}

        logger.info(f"HealthAgent: city={city}, AQI={resolved_aqi:.1f}, persona={persona or 'all'}")
        logger.info(f"HealthAgent pollutants: {resolved_pollutants}")

        # ── Build persona keys to analyze ─────────────────────────────────────
        if persona and persona in PERSONA_RULES:
            target_keys = [persona]
        elif persona and persona.lower() != "all":
            # Try fuzzy match
            slug = persona.lower().replace(" ", "_")
            target_keys = [slug] if slug in PERSONA_RULES else list(PERSONA_RULES.keys())
        else:
            target_keys = list(PERSONA_RULES.keys())

        # ── Score each persona ────────────────────────────────────────────────
        persona_risks: Dict[str, dict] = {}
        for p_key in target_keys:
            persona_risks[p_key] = self._analyze_persona(
                p_key, resolved_aqi, resolved_pollutants, exposure_hours,
                activity_level, environment,
            )

        # ── Feature 1: Hazard Index (multi-pollutant combined risk) ───────────
        hazard_index, hazard_interpretation = compute_hazard_index(resolved_pollutants)

        # ── Feature 3: Synergy warnings ──────────────────────────────────────
        _, synergy_warnings = compute_synergy_penalty(resolved_pollutants)

        # ── Feature 2: Mask recommendation ───────────────────────────────────
        mask_rec = get_mask_recommendation(resolved_aqi, target_keys[0] if target_keys else "general_population")

        # ── Alert logic ───────────────────────────────────────────────────────
        max_score = max((v["risk_score"] for v in persona_risks.values()), default=0)
        alert_triggered = resolved_aqi > 200 or max_score >= 7.0
        if resolved_aqi > 300:
            alert_message = f"🚨 SEVERE AQI {resolved_aqi:.0f} in {city}. All residents shelter indoors immediately."
        elif resolved_aqi > 200:
            alert_message = f"⚠️ HIGH AQI {resolved_aqi:.0f} in {city}. Sensitive groups at serious risk."
        elif resolved_aqi > 150:
            alert_message = f"⚠️ Elevated AQI {resolved_aqi:.0f} in {city}. Sensitive groups avoid outdoor activity."
        else:
            alert_message = ""

        # ── Pollutant notes (flat dicts) ──────────────────────────────────────
        pollutant_notes = self._compute_pollutant_notes(resolved_pollutants, list(target_keys)[0])

        # ── Danger zones from all readings ────────────────────────────────────
        danger_zones = []
        for r in readings:
            r_aqi = float(r.get("aqi") or 0)
            if r_aqi > 200:
                danger_zones.append({
                    "station_name": r.get("station_name"),
                    "aqi": r_aqi,
                    "pm25": r.get("pm25"),
                    "reason": f"AQI {r_aqi:.0f} — {get_aqi_label(int(r_aqi))}",
                })

        # ── Persist (best-effort) ─────────────────────────────────────────────
        self._persist(persona_risks, city, resolved_aqi, station)

        return HealthAgentOutput(
            message_id=message_id,
            status=MessageStatus.SUCCESS,
            payload={
                "city":                city,
                "station":             station,
                "aqi":                 resolved_aqi,
                "aqi_category":        get_aqi_label(int(resolved_aqi)),
                "persona_risks":       persona_risks,
                "hazard_index":        hazard_index,
                "hazard_interpretation": hazard_interpretation,
                "synergy_warnings":    synergy_warnings,
                "mask_recommendation": mask_rec,
                "alert_triggered":     alert_triggered,
                "alert_message":       alert_message,
                "pollutant_notes":     pollutant_notes,
                "danger_zones":        danger_zones,
                "exposure_context":    {
                    "activity_level": activity_level,
                    "environment":    environment,
                    "exposure_hours": exposure_hours,
                },
                "timestamp":           datetime.now(timezone.utc).isoformat(),
            },
        )

    # ─── Per-persona analysis → plain dict ────────────────────────────────────

    def _analyze_persona(
        self,
        persona: str,
        aqi: float,
        pollutants: Dict[str, float],
        exposure_hours: float,
        activity_level: str = "light",
        environment: str = "outdoor",
    ) -> dict:
        rules = PERSONA_RULES.get(persona, PERSONA_RULES["general_population"])
        risk_score, risk_level = calculate_risk_score(
            aqi, persona, pollutants, exposure_hours,
            activity_level=activity_level, environment=environment,
        )

        symptoms = rules["symptoms"].get(risk_level, [])
        if not symptoms:
            symptoms = ["No significant symptoms expected at current AQI"]

        preventive = rules["preventive_actions"].get(risk_level, ["Monitor air quality"])
        outdoor_rec = get_outdoor_recommendation(aqi, persona)
        mask_rec = get_mask_recommendation(aqi, persona)

        short_term_notes = rules.get("short_term_notes", {})
        long_term_notes = rules.get("long_term_notes", {})
        short_term_note = short_term_notes.get(risk_level, short_term_notes.get(RiskLevel.LOW, "")) if short_term_notes else ""
        long_term_note = long_term_notes.get(risk_level, long_term_notes.get(RiskLevel.LOW, "")) if long_term_notes else ""

        return {
            "persona":               persona,
            "persona_label":         rules.get("label", persona.replace("_", " ").title()),
            "aqi":                   round(aqi, 1),
            "aqi_category":          get_aqi_label(int(aqi)),
            "risk_level":            risk_level.value if hasattr(risk_level, "value") else str(risk_level),
            "risk_score":            round(risk_score, 2),
            "symptoms":              symptoms,
            "short_term_note":       short_term_note,
            "long_term_note":        long_term_note,
            "preventive_actions":    preventive,
            "outdoor_recommendation": outdoor_rec,
            "mask_recommendation":   mask_rec,
            "exposure_hours":        exposure_hours,
            "activity_level":        activity_level,
            "environment":           environment,
        }

    # ─── Pollutant notes → list of plain dicts ────────────────────────────────

    def _compute_pollutant_notes(self, pollutants: Dict[str, float], persona: str) -> List[dict]:
        notes = []
        rules = PERSONA_RULES.get(persona, PERSONA_RULES["general_population"])
        primary_vuln = rules.get("primary_vulnerabilities", [])

        for poll_name in ["pm25", "pm10", "no2", "co", "so2", "o3"]:
            value = pollutants.get(poll_name)
            if not value or value <= 0:
                continue
            limits = POLLUTANT_LIMITS.get(poll_name, {})
            who_limit   = limits.get("who_24h") or limits.get("who_8h", 0)
            india_limit = limits.get("india_24h") or limits.get("india_8h", 0)
            unit = limits.get("unit", "µg/m³")
            health_note = get_pollutant_health_note(poll_name, value)
            if poll_name in primary_vuln:
                health_note = f"[PRIMARY RISK] {health_note}"
            notes.append({
                "pollutant":        poll_name.upper(),
                "value":            round(value, 2),
                "unit":             unit,
                "who_limit":        who_limit,
                "india_limit":      india_limit,
                "exceedance_who":   round(value / who_limit, 2) if who_limit else 0.0,
                "exceedance_india": round(value / india_limit, 2) if india_limit else 0.0,
                "health_note":      health_note,
            })
        return notes

    # ─── Persistence ──────────────────────────────────────────────────────────

    def _persist(self, persona_risks: dict, city: str, aqi: float, station: Optional[str]):
        try:
            from data.database import db
            from data.vector_store import vector_store
            for p_key, risk in persona_risks.items():
                db.save_health_report(
                    city=city, persona=p_key, aqi=aqi,
                    risk_level=risk["risk_level"],
                    risk_score=risk["risk_score"],
                    report=risk, station=station,
                )
                summary = (
                    f"Health risk for {risk['persona_label']} in {city}: "
                    f"AQI {aqi:.0f}, Risk {risk['risk_level']} ({risk['risk_score']:.1f}/10). "
                    f"Symptoms: {', '.join(risk['symptoms'][:2])}. {risk['outdoor_recommendation']}"
                )
                vector_store.add_health_summary(
                    city=city, persona=p_key,
                    risk_level=risk["risk_level"], summary=summary,
                )
        except Exception:
            pass
