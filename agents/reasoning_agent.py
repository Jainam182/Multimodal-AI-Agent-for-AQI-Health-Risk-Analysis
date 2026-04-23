"""
agents/reasoning_agent.py
──────────────────────────
Thin orchestrator shell — uses agents/orchestrator.py for intent
classification and agent-selection logic.

process_query() returns a chat-ready dict:
  {
    "text":        str,        # main message to render in chat
    "alert":       str|None,   # high-AQI alert text
    "map":         bool,       # whether to render a map
    "chart":       str|None,   # "health" | "map" | None
    "intent":      str,
    "city":        str,
    "visualizations": dict,    # populated only when chart/map is needed
    "health":      dict,       # health payload (for chart rendering)
    "duration_ms": float,
  }
"""

from __future__ import annotations
from email.mime import text
import time
from tracemalloc import start
from typing import Any, Dict, Optional
from urllib import response

import pandas as pd

from agents.base_agent import BaseAgent
from agents.orchestrator import classify_intent, decide_agents, generate_response
from config import INDIAN_CITIES
from schemas.agent_messages import AgentMessage, AgentName, MessageStatus
from utils.logger import get_logger

logger = get_logger("ReasoningAgent")


class ReasoningAgent(BaseAgent):
    agent_name = AgentName.REASONING

    def __init__(self):
        super().__init__()
        from agents.data_agent import DataAgent
        from agents.gis_agent import GISAgent
        from agents.health_agent import HealthAgent
        from agents.visualization_agent import VisualizationAgent
        from agents.explanation_agent import ExplanationAgent

        self._data_agent   = DataAgent()
        self._gis_agent    = GISAgent()
        self._health_agent = HealthAgent()
        self._viz_agent    = VisualizationAgent()
        self._exp_agent    = ExplanationAgent()

        # Map string names → actual agent instances
        self._agent_map = {
            "data_agent":   self._data_agent,
            "health_agent": self._health_agent,
            "gis_agent":    self._gis_agent,
        }
    
    def _extract_radius(self, query: str) -> Optional[float]:
        """Extract a radius in km from natural language e.g. 'within 5km of Andheri'."""
        import re
        q = query.lower()
        patterns = [
            r"within\s+(\d+(?:\.\d+)?)\s*(?:km|kms|kilometer|km's)?",
            r"(\d+(?:\.\d+)?)\s*(?:km|kms|kilometer|km's)?\s+(?:of|around|from)\s+\w+",
            r"near\s+\w+(?:\s+(\d+(?:\.\d+)?)\s*(?:km|kms|kilometer))?",
        ]
        for pattern in patterns:
            m = re.search(pattern, q)
            if m:
                val = m.group(1) if m.group(1) else (m.group(2) if m.group(2) else None)
                if val:
                    return float(val)
        return None

    def _extract_pollutant(self, query: str) -> Optional[str]:
        """Extract a pollutant name from query e.g. 'NO2 heatmap'."""
        q = query.lower()
        mapping = {
            "pm2.5": "pm25", "pm 2.5": "pm25",
            "pm10": "pm10", "pm 10": "pm10",
            "no2": "no2", "no 2": "no2",
            "so2": "so2", "so 2": "so2",
            "o3": "o3",
            "co": "co",
        }
        for keyword, field in mapping.items():
            if keyword in q:
                return field
        return None

    def _extract_area_name(self, query: str) -> Optional[str]:
        """Extract an area/location name after 'near', 'of', 'around'."""
        import re
        q = query.lower()
        # patterns: "near Bandra", "of Andheri", "around Kurla"
        patterns = [
            r"near\s+(\w+)",
            r"(?:of|around|in)\s+(\w+)",
        ]
        stop_words = {"the", "a", "an", "in", "mumbai", "delhi", "bangalore", "city", "area"}
        for pattern in patterns:
            m = re.search(pattern, q)
            if m:
                word = m.group(1)
                if word not in stop_words:
                    return word.title()  # return capitalized
        return None

    def _extract_persona(self, query: str, default_persona: Optional[str]) -> str:
        q = query.lower()

        mapping = {
        "asthma": "Asthma Patients",
        "copd": "COPD Patients",
        "heart": "Heart Patients",
        "children": "Children",
        "elderly": "Elderly",
        "pregnant": "Pregnant Women",
        "diabetic": "Diabetic Patients",
        "athlete": "Athletes",
        "worker": "Outdoor Workers",
    }

        for key, val in mapping.items():
            if key in q:
                return val

        return default_persona or "General Population"


    def _extract_cities(self, query: str, default_city: str) -> list:
        q = query.lower()
        found = []

        for city_name in INDIAN_CITIES:
            if city_name.lower() in q:
                found.append(city_name)

    # aliases
        aliases = {
        "delhi": "Delhi", "new delhi": "Delhi",
        "bombay": "Mumbai", "bangalore": "Bengaluru",
        "calcutta": "Kolkata", "madras": "Chennai",
    }

        for alias, mapped in aliases.items():
            if alias in q and mapped not in found:
                found.append(mapped)

        return found if found else [default_city]

    # ─── Feature 2: Activity & environment extraction ─────────────────────────

    ACTIVITY_KEYWORDS = {
        "run": "vigorous", "running": "vigorous", "jog": "vigorous", "jogging": "vigorous",
        "sprint": "vigorous", "exercise": "vigorous", "gym": "vigorous", "workout": "vigorous",
        "sport": "vigorous", "football": "vigorous", "cricket": "vigorous", "training": "vigorous",
        "walk": "moderate", "walking": "moderate", "cycle": "moderate", "cycling": "moderate",
        "bike": "moderate", "hike": "moderate", "garden": "moderate",
        "commute": "light", "work": "light", "office": "light", "shop": "light",
        "rest": "resting", "sleep": "resting", "relax": "resting", "sit": "resting",
    }

    def _extract_activity_level(self, query: str) -> str:
        q = query.lower()
        for keyword, level in self.ACTIVITY_KEYWORDS.items():
            if keyword in q:
                return level
        return "light"  # default

    def _extract_environment(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ["indoor", "inside", "home", "office", "room"]):
            if any(w in q for w in ["hepa", "purifier", "filter"]):
                return "indoor_hepa"
            elif any(w in q for w in ["ac", "air condition"]):
                return "indoor_basic"
            return "indoor_no_filter"
        return "outdoor"

    # ─── BaseAgent contract ───────────────────────────────────────────────────

    def _execute(self, message_id: str, **kwargs) -> AgentMessage:
        result = self.process_query(
            query=kwargs.get("query", ""),
            city=kwargs.get("city", "Mumbai"),
            persona=kwargs.get("persona"),
            uploaded_df=kwargs.get("uploaded_df"),
        )
        return AgentMessage(
            message_id=message_id,
            source_agent=AgentName.REASONING,
            status=MessageStatus.SUCCESS,
            payload=result,
        )

    # ─── Main entry point ─────────────────────────────────────────────────────

    def process_query(
    self,
    query: str,
    city: str = "Mumbai",
    persona: Optional[str] = None,
    uploaded_df: Optional[pd.DataFrame] = None,
    exposure_hours: float = 8.0,
    ) -> dict:

        start = time.perf_counter()

    # ── 1. Extract entities ─────────────────────────────
        cities = self._extract_cities(query, city)
        persona = self._extract_persona(query, persona)
        activity_level = self._extract_activity_level(query)
        environment = self._extract_environment(query)
        city = cities[0]

        logger.info(f"Query: '{query}' | cities={cities} | persona={persona} | activity={activity_level} | env={environment}")

        q = query.lower()

    # 🚨 STRONG comparison detection
        is_comparison = (
            len(cities) >= 2 or
            any(word in q for word in ["compare", "comparison", "vs", "versus", "difference"])
    )

    # ── 2. HANDLE COMPARISON (FORCE OVERRIDE) ───────────
        if is_comparison:

            comparison_data = []
            all_readings = []
            alerts = []

            for c in cities:
                data_out = self._data_agent.run(city=c, uploaded_df=uploaded_df)
                data_p = data_out.payload if data_out else {}

                readings = data_p.get("readings", [])
                if not readings:
                    continue

                avg_aqi = int(sum(r.get("aqi", 0) for r in readings) / len(readings))

                # Get top 3 most/least polluted stations for this city
                sorted_stations = sorted(readings, key=lambda r: r.get("aqi", 0), reverse=True)
                top_stations = [
                    {"name": s.get("station_name", "?"), "aqi": int(s.get("aqi", 0))}
                    for s in sorted_stations[:3]
                ]
                bottom_stations = [
                    {"name": s.get("station_name", "?"), "aqi": int(s.get("aqi", 0))}
                    for s in sorted_stations[-3:]
                ]

                health_out = self._health_agent.run(
                    data_output=data_p,
                    city=c,
                    persona=persona,
                    exposure_hours=exposure_hours,
                )
                health_p = health_out.payload if health_out else {}

                # Extract risk level from persona_risks (correct path)
                persona_key = persona.lower().replace(" ", "_")
                persona_risks = health_p.get("persona_risks", {})
                risk_info = persona_risks.get(persona_key, {})
                if not risk_info and persona_risks:
                    risk_info = next(iter(persona_risks.values()), {})
                risk_level = risk_info.get("risk_level", health_p.get("risk_level", "Unknown"))
                risk_score = risk_info.get("risk_score", 0)

                from config import get_aqi_label
                category = get_aqi_label(avg_aqi)

                comparison_data.append({
                    "city": c,
                    "aqi": avg_aqi,
                    "category": category,
                    "risk_level": risk_level,
                    "risk_score": risk_score,
                    "station_count": len(readings),
                    "top_stations": top_stations,
                    "bottom_stations": bottom_stations,
                })

                # Tag each reading with its city for combined display
                for r in readings:
                    r["city"] = c
                all_readings.extend(readings)

                if avg_aqi >= 400:
                    alerts.append(f"🚨 SEVERE AQI {avg_aqi} in {c}. All residents shelter indoors.")
                elif avg_aqi >= 300:
                    alerts.append(f"⚠️ Very Poor AQI {avg_aqi} in {c}. Avoid outdoor exposure.")

            # Build comparison text
            text = "## 📊 AQI Comparison\n\n"

            if len(comparison_data) >= 2:
                sorted_data = sorted(comparison_data, key=lambda x: x["aqi"], reverse=True)

                # Summary table
                text += "| City | AQI | Category | Health Risk | Stations |\n"
                text += "|------|-----|----------|------------|----------|\n"
                for item in sorted_data:
                    text += (f"| **{item['city']}** | {item['aqi']} | "
                             f"{item['category']} | {item['risk_level']} | "
                             f"{item['station_count']} |\n")

                worst = sorted_data[0]
                best = sorted_data[-1]
                diff = worst["aqi"] - best["aqi"]
                text += f"\n**{worst['city']}** is more polluted than **{best['city']}** by **{diff} AQI points**.\n"

                # Station highlights per city
                for item in sorted_data:
                    text += f"\n### {item['city']} — Top Stations\n"
                    text += "**Most polluted:**\n"
                    for s in item["top_stations"]:
                        text += f"- {s['name']}: AQI **{s['aqi']}**\n"
                    text += "\n**Cleanest:**\n"
                    for s in item["bottom_stations"]:
                        text += f"- {s['name']}: AQI **{s['aqi']}**\n"

            elif comparison_data:
                item = comparison_data[0]
                text += f"**{item['city']}**: AQI {item['aqi']} ({item['category']}, {item['risk_level']} risk)\n"

            duration_ms = (time.perf_counter() - start) * 1000

            return {
                "text": text,
                "alert": "\n".join(alerts) if alerts else None,
                "intent": "comparison_query",
                "city": ", ".join(cities),
                "map": False,
                "chart": None,
                "comparison_data": comparison_data,  # structured for chart rendering
                "data": {"readings": all_readings, "sources_used": ["waqi_api"]},
                "visualizations": {},
                "duration_ms": round(duration_ms, 1),
            }

    # ── 3. NORMAL PIPELINE ──────────────────────────────
        intent = classify_intent(query)
        agents_needed = decide_agents(intent, query)

        data_out = health_out = gis_out = None
        radius = 3.0
        pollutant = None
        area_name = None

        if "data_agent" in agents_needed:
            mode = "historical" if intent == "trend_query" else "current"
            data_out = self._data_agent.run(
            city=city, mode=mode, uploaded_df=uploaded_df
        )

        if "health_agent" in agents_needed and data_out:
            health_out = self._health_agent.run(
            data_output=data_out.payload,
            city=city,
            persona=persona,
            exposure_hours=exposure_hours,
            activity_level=activity_level,
            environment=environment,
        )

        if "gis_agent" in agents_needed and data_out:
            radius = self._extract_radius(query) or 3.0
            pollutant = self._extract_pollutant(query)
            area_name = self._extract_area_name(query)
            gis_out = self._gis_agent.run(
            data_output=data_out.payload,
            city=city,
            eps_km=radius,
            radius_km=radius,
            area_name=area_name,
        )

        data_p   = data_out.payload   if data_out   else {}
        health_p = health_out.payload if health_out else {}
        gis_p    = gis_out.payload    if gis_out    else {}

        response = generate_response(
        query=query,
        intent=intent,
        city=city,
        data_payload=data_p,
        health_payload=health_p,
        gis_payload=gis_p,
        )

        viz_payload = {}
        if response.get("map") or response.get("chart"):
            try:
                viz_out = self._viz_agent.run(
                data_output=data_p,
                gis_output=gis_p,
                health_output=health_p,
                city=city,
                persona=persona,
                pollutant=pollutant,
            )
                viz_payload = viz_out.payload if viz_out else {}
            except Exception as e:
                logger.warning(f"Viz skipped: {e}")

        duration_ms = (time.perf_counter() - start) * 1000

        return {
        **response,
        "visualizations": viz_payload,
        "health": health_p,
        "data": data_p,
        "gis": gis_p,
        "pollutant": pollutant,
        "radius_km": radius,
        "duration_ms": round(duration_ms, 1),
    }
    # ─── Historical data (for Trends tab) ────────────────────────────────────

    def get_historical_data(self, city: str, days: int = 30) -> Optional[pd.DataFrame]:
        try:
            raw = self._data_agent._fetch_open_meteo_historical(city=city, days=days)
            return pd.DataFrame(raw) if raw else None
        except Exception as e:
            logger.warning(f"Historical fetch failed: {e}")
            return None
