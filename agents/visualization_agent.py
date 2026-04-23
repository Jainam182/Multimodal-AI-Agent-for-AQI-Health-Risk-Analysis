"""
agents/visualization_agent.py
──────────────────────────────
All inputs are plain dict payloads. Returns Folium map object + Plotly dicts.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

import folium
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from folium.plugins import HeatMap

from agents.base_agent import BaseAgent
from config import AQI_CATEGORIES, PERSONAS, get_aqi_category, get_aqi_label
from schemas.agent_messages import (
    AgentName, MessageStatus, VisualizationAgentOutput,
)
from utils.logger import get_logger

logger = get_logger("VisualizationAgent")

RISK_COLORS = {
    "Minimal":   "#00b300",
    "Low":       "#80cc00",
    "Moderate":  "#ffcc00",
    "High":      "#ff6600",
    "Very High": "#cc0000",
    "Critical":  "#660033",
}

AQI_CIRCLE_COLOR = {
    "Good":                "#4ade80",
    "Satisfactory":        "#a3e635",
    "Moderately Polluted": "#fbbf24",
    "Poor":                "#fb923c",
    "Very Poor":           "#f87171",
    "Severe / Hazardous":  "#ef4444",
    "Unknown":             "#8b949e",
}


class VisualizationAgent(BaseAgent):
    agent_name = AgentName.VISUALIZATION

    def _execute(
        self,
        message_id: str,
        data_output=None,
        gis_output=None,
        health_output=None,
        historical_df: Optional[pd.DataFrame] = None,
        city: str = "Mumbai",
        persona: Optional[str] = None,
        show_heatmap: bool = True,
        pollutant: Optional[str] = None,
        **kwargs,
    ) -> VisualizationAgentOutput:

        # ── Unwrap dict payloads ──────────────────────────────────────────────
        data_p   = self._unwrap(data_output)
        gis_p    = self._unwrap(gis_output)
        health_p = self._unwrap(health_output)

        readings = data_p.get("readings", [])
        city     = data_p.get("city", city)

        folium_map   = None
        trend_chart  = None
        health_chart = None
        pollutant_heatmap = None
        risk_table   = None

        # ── Map ───────────────────────────────────────────────────────────────
        if readings:
            folium_map = self._build_folium_map(readings, gis_p, city, persona, show_heatmap, pollutant)

        # ── Trend chart ───────────────────────────────────────────────────────
        if historical_df is not None and isinstance(historical_df, pd.DataFrame) and not historical_df.empty:
            trend_chart = self._build_trend_chart(historical_df, city)

        # ── Health chart ──────────────────────────────────────────────────────
        if health_p:
            health_chart  = self._build_health_chart(health_p)
            risk_table    = self._build_risk_table(health_p)

        # ── Pollutant heatmap ─────────────────────────────────────────────────
        if readings:
            pollutant_heatmap = self._build_pollutant_heatmap(readings, city)

        # ── Feature 4: Risk timeline ──────────────────────────────────────────
        risk_timeline = None
        hourly_data = kwargs.get("hourly_data")
        if hourly_data and persona:
            risk_timeline = self._build_risk_timeline(hourly_data, persona, city)

        return VisualizationAgentOutput(
            message_id=message_id,
            status=MessageStatus.SUCCESS,
            payload={
                "folium_map":        folium_map,       # Folium Map object
                "trend_chart":       trend_chart,      # Plotly dict
                "health_chart":      health_chart,     # Plotly dict
                "pollutant_heatmap": pollutant_heatmap,
                "risk_table":        risk_table,
                "risk_timeline":     risk_timeline,    # Feature 4: Plotly dict
                "city":              city,
            },
        )

    # ─── Helper ───────────────────────────────────────────────────────────────

    def _unwrap(self, output) -> dict:
        """Accept AgentMessage or plain dict, always return the payload dict."""
        if output is None:
            return {}
        if isinstance(output, dict):
            return output
        if hasattr(output, "payload"):
            p = output.payload
            return p if isinstance(p, dict) else {}
        return {}

    # ─── Folium Map ───────────────────────────────────────────────────────────

    def _build_folium_map(
        self,
        readings: List[dict],
        gis_p: dict,
        city: str,
        persona: Optional[str],
        show_heatmap: bool,
        pollutant: Optional[str] = None,
    ) -> folium.Map:
        from config import INDIAN_CITIES
        coords = INDIAN_CITIES.get(city, {"lat": 19.076, "lon": 72.877})
        center = [coords["lat"], coords["lon"]]

        m = folium.Map(location=center, zoom_start=11, tiles="CartoDB dark_matter")

        # Heatmap layer
        if show_heatmap:
            # Use pollutant value if specified, else fall back to AQI
            heat_data = []
            for r in readings:
                val = r.get(pollutant, r.get("aqi")) if pollutant else r.get("aqi")
                if val:
                    # Normalise: divide by 500 for AQI, or use a reasonable max for pollutants
                    max_val = 500 if (pollutant is None or pollutant == "aqi") else 200
                    heat_data.append([
                        r.get("lat", center[0]),
                        r.get("lon", center[1]),
                        (val or 0) / max_val
                    ])
            if heat_data:
                HeatMap(heat_data, radius=20, blur=15, max_zoom=13,
                        gradient={0.2:"blue", 0.4:"lime", 0.6:"yellow", 0.8:"orange", 1.0:"red"}
                        ).add_to(m)

        # Station markers
        for r in readings:
            lat  = r.get("lat") or center[0]
            lon  = r.get("lon") or center[1]
            aqi  = r.get("aqi") or 0
            cat  = r.get("aqi_category") or get_aqi_label(int(aqi))
            color = AQI_CIRCLE_COLOR.get(cat, "#8b949e")
            popup_html = self._popup_html(r, persona)

            folium.CircleMarker(
                location=[lat, lon],
                radius=12 + aqi / 40,
                color=color, fill=True, fill_color=color, fill_opacity=0.75,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"{r.get('station_name','?')}: AQI {aqi:.0f}",
            ).add_to(m)

            folium.Marker(
                location=[lat, lon],
                icon=folium.DivIcon(
                    html=f'<div style="font-size:9px;font-weight:bold;color:#fff;'
                         f'background:{color};padding:1px 4px;border-radius:3px">'
                         f'{aqi:.0f}</div>',
                    icon_size=(36, 18), icon_anchor=(18, 9),
                ),
            ).add_to(m)

        # Hotspot rings from GIS
        for c in gis_p.get("clusters", []):
            avg = c.get("avg_aqi", 0)
            if avg > 150:
                folium.Circle(
                    location=[c.get("centroid_lat", center[0]), c.get("centroid_lon", center[1])],
                    radius=3000,
                    color="red", weight=2, fill=True,
                    fill_color="red", fill_opacity=0.06,
                    tooltip=f"⚠️ Cluster AQI {avg:.0f}",
                ).add_to(m)

        # Legend
        m.get_root().html.add_child(folium.Element(self._legend_html()))
        return m

    def _popup_html(self, r: dict, persona: Optional[str]) -> str:
        polls = [("PM2.5","pm25","µg/m³"),("PM10","pm10","µg/m³"),
                 ("NO₂","no2","µg/m³"),("CO","co","mg/m³"),
                 ("SO₂","so2","µg/m³"),("O₃","o3","µg/m³")]
        rows = "".join(
            f"<tr><td><b>{lbl}</b></td><td>{r.get(k,'N/A')} {unit}</td></tr>"
            for lbl, k, unit in polls if r.get(k) is not None
        )
        persona_html = ""
        if persona:
            from tools.health_tools import calculate_risk_score, get_outdoor_recommendation
            polls_dict = {k: float(r.get(k) or 0) for _, k, _ in polls}
            score, lvl = calculate_risk_score(r.get("aqi") or 0, persona, polls_dict)
            rec = get_outdoor_recommendation(r.get("aqi") or 0, persona)
            lv = lvl.value if hasattr(lvl, "value") else str(lvl)
            persona_html = f"<hr><b>{persona.replace('_',' ').title()}</b><br>Risk: {lv} ({score:.1f}/10)<br>{rec}"
        aqi = r.get("aqi") or 0
        cat = r.get("aqi_category") or get_aqi_label(int(aqi))
        return f"""
        <div style="font-family:sans-serif;font-size:12px;min-width:220px">
          <b>{r.get('station_name','?')}</b><br>
          <span style="font-size:18px;font-weight:bold">AQI {aqi:.0f}</span>
          <span style="font-size:11px"> – {cat}</span><hr>
          <table>{"".join([f'<tr><td><b>{lbl}</b></td><td>{r.get(k,"N/A")} {unit}</td></tr>' for lbl,k,unit in polls if r.get(k)])}</table>
          <small>Source: {r.get('source','?')}</small>
          {persona_html}
        </div>"""

    def _legend_html(self) -> str:
        items = "".join(
            f'<div><span style="display:inline-block;width:10px;height:10px;'
            f'background:{color};border-radius:50%;margin-right:5px"></span>{label}</div>'
            for label, color in [
                ("Good (0–50)",        "#4ade80"),
                ("Satisfactory (51–100)", "#a3e635"),
                ("Moderate (101–200)", "#fbbf24"),
                ("Poor (201–300)",     "#fb923c"),
                ("Very Poor (301–400)","#f87171"),
                ("Severe (401–500)",   "#ef4444"),
            ]
        )
        return f"""<div style="position:fixed;bottom:30px;right:10px;z-index:9999;
            background:rgba(0,0,0,0.8);color:#ccc;padding:10px;border-radius:8px;
            font-family:sans-serif;font-size:11px"><b>AQI</b><br>{items}</div>"""

    # ─── Trend Chart ──────────────────────────────────────────────────────────

    def _build_trend_chart(self, df: pd.DataFrame, city: str) -> dict:
        if not isinstance(df, pd.DataFrame) or df.empty:
            return {}
        fig = go.Figure()
        for lo, hi, color, label in [
            (0,50,"rgba(0,228,0,0.1)","Good"),
            (50,100,"rgba(255,255,0,0.1)","Satisfactory"),
            (100,200,"rgba(255,126,0,0.1)","Moderate"),
            (200,300,"rgba(255,0,0,0.1)","Poor"),
            (300,500,"rgba(143,63,151,0.1)","Very Poor"),
        ]:
            fig.add_hrect(y0=lo, y1=hi, fillcolor=color, line_width=0,
                          annotation_text=label, annotation_position="right",
                          annotation_font_size=9)

        ts_col = next((c for c in ["timestamp","datetime","date"] if c in df.columns), None)
        if ts_col and "station_name" in df.columns:
            for stn, grp in df.groupby("station_name"):
                grp = grp.sort_values(ts_col)
                fig.add_trace(go.Scatter(x=grp[ts_col], y=pd.to_numeric(grp.get("aqi", grp.get("AQI")), errors="coerce"),
                    mode="lines", name=str(stn), line=dict(width=2)))
        elif ts_col and "aqi" in df.columns:
            fig.add_trace(go.Scatter(x=df[ts_col], y=pd.to_numeric(df["aqi"], errors="coerce"),
                mode="lines", name="AQI", line=dict(color="#00d2ff", width=2)))

        fig.update_layout(title=f"AQI Trend – {city}", xaxis_title="Time",
            yaxis=dict(title="AQI", range=[0,500]),
            template="plotly_dark", hovermode="x unified", height=360,
            legend=dict(orientation="h", y=1.05))
        return fig.to_dict()

    # ─── Health Chart ─────────────────────────────────────────────────────────

    def _build_health_chart(self, health_p: dict) -> dict:
        risks = health_p.get("persona_risks", {})
        if not risks:
            return {}
        rows = [{"persona": k, **v} for k, v in risks.items()] if isinstance(risks, dict) else risks
        rows = sorted(rows, key=lambda r: r.get("risk_score", 0), reverse=True)

        labels = [r.get("persona_label", r.get("persona","?")).replace("_"," ").title() for r in rows]
        scores = [r.get("risk_score", 0) for r in rows]
        colors = [RISK_COLORS.get(r.get("risk_level","Moderate"), "#888") for r in rows]
        hovers = [
            f"<b>{r.get('persona_label',r.get('persona','?'))}</b><br>"
            f"Risk: {r.get('risk_level','?')} ({r.get('risk_score',0):.1f}/10)<br>"
            f"{r.get('outdoor_recommendation','')}"
            for r in rows
        ]

        fig = go.Figure(go.Bar(
            x=scores, y=labels, orientation="h",
            marker_color=colors, hovertext=hovers, hoverinfo="text",
            text=[f"{s:.1f}" for s in scores], textposition="outside",
        ))
        aqi = health_p.get("aqi", 0)
        city = health_p.get("city", "")
        fig.update_layout(
            title=f"Health Risk by Persona – AQI {aqi:.0f} ({city})",
            xaxis=dict(title="Risk Score (0–10)", range=[0,11]),
            template="plotly_dark",
            height=max(300, len(rows) * 40 + 100),
            margin=dict(l=180, r=60),
        )
        return fig.to_dict()

    # ─── Pollutant Heatmap ────────────────────────────────────────────────────

    def _build_pollutant_heatmap(self, readings: List[dict], city: str) -> dict:
        if not readings:
            return {}
        poll_names = ["pm25","pm10","no2","co","so2","o3"]
        stations = [r.get("station_name","?") for r in readings]
        matrix = []
        for r in readings:
            matrix.append([float(r.get(p) or 0) * (100 if p == "co" else 1) for p in poll_names])

        fig = go.Figure(go.Heatmap(
            z=matrix, x=[p.upper() for p in poll_names], y=stations,
            colorscale="RdYlGn_r",
            hovertemplate="<b>%{y}</b><br>%{x}: %{z:.1f}<extra></extra>",
        ))
        fig.update_layout(title=f"Pollutant Levels – {city}",
            template="plotly_dark",
            height=max(300, len(stations)*30+120))
        return fig.to_dict()

    # ─── Risk Table ───────────────────────────────────────────────────────────

    def _build_risk_table(self, health_p: dict) -> List[dict]:
        risks = health_p.get("persona_risks", {})
        if isinstance(risks, dict):
            rows = [{"persona": k, **v} for k, v in risks.items()]
        else:
            rows = risks
        table = []
        for r in sorted(rows, key=lambda x: x.get("risk_score",0), reverse=True):
            icon = PERSONAS.get(r.get("persona",""), {}).get("icon", "")
            table.append({
                "Persona":       f"{icon} {r.get('persona_label', r.get('persona','?'))}",
                "AQI":           r.get("aqi", 0),
                "Risk Level":    r.get("risk_level", "?"),
                "Risk Score":    f"{r.get('risk_score',0):.1f}/10",
                "Outdoor Rec":   (r.get("outdoor_recommendation","") or "")[:50],
                "Top Symptom":   (r.get("symptoms",["None"])[0] if r.get("symptoms") else "None"),
            })
        return table

    # ─── Standalone utils ─────────────────────────────────────────────────────

    def build_gauge_chart(self, aqi: float, title: str = "Current AQI") -> dict:
        cat_str = get_aqi_label(int(aqi))
        color_map = {
            "Good": "#4ade80", "Satisfactory": "#a3e635",
            "Moderately Polluted": "#fbbf24", "Poor": "#fb923c",
            "Very Poor": "#f87171", "Severe / Hazardous": "#ef4444",
        }
        color = color_map.get(cat_str, "#8b949e")
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=aqi,
            title={"text": title, "font": {"color": "white"}},
            gauge={"axis": {"range": [0, 500]}, "bar": {"color": color},
                   "steps": [
                       {"range":[0,50],"color":"#004d00"},{"range":[50,100],"color":"#808000"},
                       {"range":[100,200],"color":"#804000"},{"range":[200,300],"color":"#800000"},
                       {"range":[300,500],"color":"#400040"},
                   ]},
            number={"font": {"color": color}, "suffix": f" – {cat_str}"},
        ))
        fig.update_layout(template="plotly_dark", height=260, margin=dict(t=50,b=20))
        return fig.to_dict()

    # ─── Feature 4: Risk Timeline ─────────────────────────────────────────────

    def _build_risk_timeline(
        self,
        hourly_data: list,
        persona: str,
        city: str,
    ) -> dict:
        """
        Build a 24-hour risk timeline chart for a persona.
        Shows risk score over hours with color-coded zones.
        """
        from tools.health_tools import compute_hourly_risk_scores, PERSONA_RULES

        hourly_scores = compute_hourly_risk_scores(hourly_data, persona)
        if not hourly_scores:
            return {}

        hours = [str(s["hour"]) for s in hourly_scores]
        scores = [s["risk_score"] for s in hourly_scores]
        aqis = [s["aqi"] for s in hourly_scores]
        levels = [s["risk_level"] for s in hourly_scores]
        is_safe = [s["is_safe"] for s in hourly_scores]

        # Color each bar by risk level
        from tools.health_tools import PERSONA_RULES as _PR
        risk_colors = {
            "Minimal":   "#4ade80",
            "Low":       "#a3e635",
            "Moderate":  "#fbbf24",
            "High":      "#fb923c",
            "Very High": "#f87171",
            "Critical":  "#ef4444",
        }
        bar_colors = [risk_colors.get(l, "#8b949e") for l in levels]

        rules = PERSONA_RULES.get(persona, PERSONA_RULES["general_population"])
        label = rules.get("label", persona.replace("_", " ").title())

        fig = go.Figure()

        # Risk score bars
        fig.add_trace(go.Bar(
            x=hours, y=scores,
            marker_color=bar_colors,
            text=[f"{s:.1f}" for s in scores],
            textposition="outside",
            hovertext=[
                f"<b>{h}:00</b><br>AQI: {a}<br>Risk: {l} ({s:.1f}/10)"
                for h, a, l, s in zip(hours, aqis, levels, scores)
            ],
            hoverinfo="text",
            name="Risk Score",
        ))

        # Safe zone threshold line
        fig.add_hline(
            y=4.0, line_dash="dash", line_color="#4ade80",
            annotation_text="Safe threshold", annotation_position="top right",
            annotation_font_color="#4ade80", annotation_font_size=10,
        )

        # Danger zone threshold line
        fig.add_hline(
            y=7.5, line_dash="dash", line_color="#f87171",
            annotation_text="Danger threshold", annotation_position="top right",
            annotation_font_color="#f87171", annotation_font_size=10,
        )

        # Highlight safe hours with subtle green background
        for i, safe in enumerate(is_safe):
            if safe:
                fig.add_vrect(
                    x0=i-0.4, x1=i+0.4,
                    fillcolor="rgba(74, 222, 128, 0.08)", line_width=0,
                )

        fig.update_layout(
            title=f"24h Health Risk Timeline — {label} · {city}",
            xaxis_title="Hour of Day",
            yaxis=dict(title="Risk Score (0–10)", range=[0, 11]),
            template="plotly_dark",
            height=380,
            margin=dict(l=40, r=40, t=60, b=40),
            showlegend=False,
            hovermode="x unified",
        )

        return fig.to_dict()
