"""
Multi-Agent AQI Health Risk Analysis System
Streamlit UI — Production Dashboard
"""

import logging as _logging
logger = _logging.getLogger(__name__)

from aiohttp import payload
import streamlit as st
import pandas as pd
import json
import time
import os
from datetime import datetime, timedelta
from pathlib import Path
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go
import plotly.express as px
from dotenv import load_dotenv

load_dotenv()

# ─── Page config (must be first Streamlit call) ───────────────────────────────
st.set_page_config(
    page_title="AQI Health Risk Intelligence",
    page_icon="🌫️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─── Plotly safe render helper ────────────────────────────────────────────────
def _safe_fig(obj):
    """Convert Plotly dict → Figure if needed. Returns None if invalid."""
    if obj is None:
        return None
    try:
        import plotly.graph_objects as _go
        if isinstance(obj, dict):
            return _go.Figure(obj)
        return obj  # already a Figure
    except Exception:
        return None


# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Global theme */
[data-testid="stAppViewContainer"] { background: #0e1117; }
[data-testid="stSidebar"] { background: #161b22; }

/* Card styling */
.metric-card {
    background: #1c2333;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 12px;
}
.metric-card h3 { color: #8b949e; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.08em; margin: 0 0 4px 0; }
.metric-card .value { font-size: 2rem; font-weight: 700; color: #f0f6fc; }
.metric-card .sub { font-size: 0.75rem; color: #6e7681; margin-top: 2px; }

/* AQI badge */
.aqi-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-weight: 700;
    font-size: 0.85rem;
    letter-spacing: 0.04em;
}
.aqi-good    { background: #1a4731; color: #4ade80; }
.aqi-satisf  { background: #3d4a1a; color: #a3e635; }
.aqi-mod     { background: #4a3b1a; color: #fbbf24; }
.aqi-poor    { background: #4a2a1a; color: #fb923c; }
.aqi-vpoor   { background: #4a1a1a; color: #f87171; }
.aqi-severe  { background: #3b0c0c; color: #ef4444; }

/* Alert box */
.alert-box {
    background: #2d1b1b;
    border-left: 4px solid #ef4444;
    border-radius: 6px;
    padding: 12px 16px;
    margin: 8px 0;
    color: #fca5a5;
    font-size: 0.88rem;
}
.info-box {
    background: #0c2340;
    border-left: 4px solid #3b82f6;
    border-radius: 6px;
    padding: 12px 16px;
    margin: 8px 0;
    color: #93c5fd;
    font-size: 0.88rem;
}

/* Section headers */
.section-header {
    font-size: 1.1rem;
    font-weight: 600;
    color: #f0f6fc;
    border-bottom: 1px solid #30363d;
    padding-bottom: 8px;
    margin: 20px 0 14px 0;
}

/* Risk score bar */
.risk-bar-wrap { margin: 6px 0; }
.risk-label { font-size: 0.78rem; color: #8b949e; margin-bottom: 2px; }
.risk-bar-bg { background: #21262d; border-radius: 4px; height: 10px; }
.risk-bar-fill { border-radius: 4px; height: 10px; }

/* Query chip */
.query-chip {
    display: inline-block;
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 20px;
    padding: 5px 14px;
    font-size: 0.78rem;
    color: #8b949e;
    margin: 4px 4px 4px 0;
    cursor: pointer;
}

/* Agent step */
.step-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 0;
    border-bottom: 1px solid #21262d;
    font-size: 0.82rem;
    color: #8b949e;
}
.step-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.step-done { background: #4ade80; }
.step-run  { background: #fbbf24; }
.step-wait { background: #374151; }
</style>
""", unsafe_allow_html=True)

# ─── Lazy imports (expensive at startup) ─────────────────────────────────────
@st.cache_resource(show_spinner=False)
def load_agents():
    """Load all agents once and cache."""
    from agents.reasoning_agent import ReasoningAgent
    # ReasoningAgent owns all sub-agents internally.
    # We also expose them individually so dashboard tabs can call them directly.
    ra = ReasoningAgent()
    return {
        "reasoning":     ra,
        "data":          ra._data_agent,
        "gis":           ra._gis_agent,
        "health":        ra._health_agent,
        "visualization": ra._viz_agent,
        "explanation":   ra._exp_agent,
    }
# ─── SMART DATA FETCH LAYER (PRODUCTION CACHE) ───────────────────────────────

@st.cache_data(ttl=300)  # 5 minutes caching
def fetch_historical_data_cached(city: str, days: int):
    """Cached AQI historical fetch (prevents infinite API calls)."""
    try:
        agents = load_agents()
        return agents["data"]._fetch_open_meteo_historical(city=city, days=days)
    except Exception as e:
        return None


def get_historical_data(city: str, days: int):
    """
    Production-safe fetch pipeline:
    1. Try DB
    2. Else cached API
    """

    # Try DB first
    try:
        from data.database import db
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=days)

        hist = db.get_historical_readings(
            city=city,
            start_dt=start_dt,
            end_dt=end_dt,
            limit=days * 24 * 30,
        )

        if hist and len(hist) > days * 2:
            return pd.DataFrame(hist)

    except Exception:
        pass

    # Fallback to cached API
    raw = fetch_historical_data_cached(city, days)

    if raw:
        return pd.DataFrame(raw)

    return pd.DataFrame()

# ─── Session state init ───────────────────────────────────────────────────────
def init_session():
    defaults = {
        "agents_loaded": False,
        "last_result": None,
        "query_history": [],
        "uploaded_df": None,
        "selected_city": "Mumbai",
        "selected_persona": "General Population",
        "analysis_running": False,
        "active_tab": "Dashboard",
        "chat_messages": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()


# ─── AQI colour helpers ───────────────────────────────────────────────────────
AQI_COLOURS = {
    "Good": ("#4ade80", "aqi-good"),
    "Satisfactory": ("#a3e635", "aqi-satisf"),
    "Moderately Polluted": ("#fbbf24", "aqi-mod"),
    "Poor": ("#fb923c", "aqi-poor"),
    "Very Poor": ("#f87171", "aqi-vpoor"),
    "Severe / Hazardous": ("#ef4444", "aqi-severe"),
}

def aqi_badge(category: str) -> str:
    colour, css = AQI_COLOURS.get(category, ("#8b949e", "aqi-mod"))
    return f'<span class="aqi-badge {css}">{category}</span>'

def risk_colour(score: float) -> str:
    if score < 3:   return "#4ade80"
    if score < 5:   return "#fbbf24"
    if score < 7:   return "#fb923c"
    return "#ef4444"


# ─── Sidebar ─────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown("## 🌫️ AQI Intelligence")
        st.markdown("---")

        # City selection
        from config import INDIAN_CITIES
        city_list = list(INDIAN_CITIES.keys())
        st.session_state.selected_city = st.selectbox(
            "📍 City", city_list,
            index=city_list.index(st.session_state.selected_city)
                  if st.session_state.selected_city in city_list else 0,
        )

        # Persona selection
        personas = [
            "General Population", "Children", "Elderly", "Asthma Patients",
            "COPD Patients", "Heart Patients", "Athletes", "Outdoor Workers",
            "Pregnant Women", "Diabetic Patients",
        ]
        st.session_state.selected_persona = st.selectbox(
            "👤 Persona", personas,
            index=personas.index(st.session_state.selected_persona)
                  if st.session_state.selected_persona in personas else 0,
        )

        st.markdown("---")

        # File upload
        st.markdown("**📂 Upload CSV**")
        uploaded = st.file_uploader(
            "Custom AQI data", type=["csv"],
            help="Must have columns: datetime, pm25, pm10, no2 (optional: aqi, so2, co, o3)",
            label_visibility="collapsed",
        )
        if uploaded:
            try:
                df = pd.read_csv(uploaded)
                st.session_state.uploaded_df = df
                st.success(f"✓ {len(df)} rows loaded")
            except Exception as e:
                st.error(f"Parse error: {e}")

        if st.session_state.uploaded_df is not None:
            if st.button("🗑 Clear upload", use_container_width=True):
                st.session_state.uploaded_df = None
                st.rerun()

        st.markdown("---")
        if st.button("🔄 Force Refresh Data"):
            fetch_historical_data_cached.clear()
            st.success("Cache cleared. New data will be fetched.")
        st.markdown("---")

        # API key status
        st.markdown("**🔑 API Keys**")
        keys = {
            "Groq": os.getenv("GROQ_API_KEY"),
            "OpenAI": os.getenv("OPENAI_API_KEY"),
            "WAQI": os.getenv("WAQI_API_KEY"),
        }
        for name, val in keys.items():
            status = "🟢" if val else "🔴"
            st.markdown(f"{status} {name}")

        st.markdown("---")
        st.caption("v1.0 · Built with Multi-Agent AI")


# ─── Dashboard Tab ────────────────────────────────────────────────────────────
def render_dashboard(agents):
    city = st.session_state.selected_city
    persona = st.session_state.selected_persona

    col_hdr, col_btn = st.columns([5, 1])
    with col_hdr:
        st.markdown(f"### 📊 Live Dashboard · {city}")
    with col_btn:
        refresh = st.button("⟳ Refresh", use_container_width=True)

    # Load data
    with st.spinner(f"Fetching AQI data for {city}…"):
        @st.cache_data(ttl=120)
        def get_live_data_payload(city):
            """Cache only serializable payload, not agent object"""
            agents = load_agents()
            result = agents["data"].run(city=city, uploaded_df=None)
            if result and hasattr(result, "payload"):
                return result.payload  # ✅ dict (serializable)
            return None

        payload = get_live_data_payload(city)

        if not payload or payload.get("status") == "error":
            st.error("Failed to load AQI data.")
            return

        # recreate lightweight object (no need full class)
        class SimpleData:
            def __init__(self, payload):
                self.payload = payload

        data_out = SimpleData(payload)

    if not data_out.payload or data_out.payload.get("status") == "error":
        st.error("Failed to load AQI data. Check logs.")
        return

    readings = data_out.payload.get("readings", [])

    # ── Top metrics ──────────────────────────────────────────────────────────
    avg_aqi   = sum(r.get("aqi", 0) for r in readings) / max(len(readings), 1)
    avg_pm25  = sum(r.get("pm25", 0) for r in readings if r.get("pm25")) / max(len(readings), 1)
    avg_no2   = sum(r.get("no2", 0)  for r in readings if r.get("no2"))  / max(len(readings), 1)
    from config import get_aqi_label
    category = get_aqi_label(int(avg_aqi))

    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        st.markdown(f"""<div class="metric-card">
            <h3>Overall AQI</h3>
            <div class="value">{avg_aqi:.0f}</div>
            <div class="sub">{aqi_badge(category)}</div>
        </div>""", unsafe_allow_html=True)
    with mc2:
        st.markdown(f"""<div class="metric-card">
            <h3>PM2.5 (µg/m³)</h3>
            <div class="value">{avg_pm25:.1f}</div>
            <div class="sub">WHO limit: 15 µg/m³</div>
        </div>""", unsafe_allow_html=True)
    with mc3:
        st.markdown(f"""<div class="metric-card">
            <h3>NO₂ (µg/m³)</h3>
            <div class="value">{avg_no2:.1f}</div>
            <div class="sub">WHO limit: 40 µg/m³</div>
        </div>""", unsafe_allow_html=True)
    with mc4:
        station_count = len(readings)
        st.markdown(f"""<div class="metric-card">
            <h3>Stations</h3>
            <div class="value">{station_count}</div>
            <div class="sub">{city} coverage</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── Map + Health panel ───────────────────────────────────────────────────
    map_col, health_col = st.columns([3, 2])

    with map_col:
        st.markdown('<div class="section-header">📍 AQI Station Map</div>', unsafe_allow_html=True)
        _render_quick_map(readings, city)

    with health_col:
        st.markdown(f'<div class="section-header">🏥 Health Risk · {persona}</div>', unsafe_allow_html=True)
        _render_health_panel(agents, data_out, persona, avg_aqi)

    # ── Station table ────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">📋 Station Details</div>', unsafe_allow_html=True)
    _render_station_table(readings)


def _render_quick_map(readings, city):
    from config import INDIAN_CITIES
    coords = INDIAN_CITIES.get(city, {"lat": 19.076, "lon": 72.877})
    m = folium.Map(
        location=[coords["lat"], coords["lon"]],
        zoom_start=11,
        tiles="CartoDB dark_matter",
    )
    AQI_CIRCLE_COLOUR = {
        "Good": "#4ade80", "Satisfactory": "#a3e635",
        "Moderately Polluted": "#fbbf24", "Poor": "#fb923c",
        "Very Poor": "#f87171", "Severe / Hazardous": "#ef4444",
    }
    from config import get_aqi_label
    for r in readings:
        lat = r.get("lat", coords["lat"] + (hash(r.get("station_name","")) % 100) * 0.002)
        lon = r.get("lon", coords["lon"] + (hash(r.get("station_name","") + "x") % 100) * 0.002)
        aqi = r.get("aqi", 0)
        cat = get_aqi_label(int(aqi))
        colour = AQI_CIRCLE_COLOUR.get(cat, "#8b949e")
        popup_html = f"""
        <b>{r.get('station_name','Unknown')}</b><br>
        AQI: <b>{aqi:.0f}</b> ({cat})<br>
        PM2.5: {r.get('pm25','N/A')} µg/m³<br>
        PM10: {r.get('pm10','N/A')} µg/m³<br>
        NO₂: {r.get('no2','N/A')} µg/m³
        """
        folium.CircleMarker(
            location=[lat, lon],
            radius=12 + aqi / 30,
            color=colour,
            fill=True,
            fill_color=colour,
            fill_opacity=0.7,
            popup=folium.Popup(popup_html, max_width=220),
            tooltip=f"{r.get('station_name','?')}: AQI {aqi:.0f}",
        ).add_to(m)

    st_folium(m, height=380, use_container_width=True)


def _render_health_panel(agents, data_out, persona, avg_aqi):
    h_out = agents["health"].run(
        data_output=data_out.payload,
        persona=persona,
        exposure_hours=8,
    )
    h = h_out.payload or {}
    risks = h.get("persona_risks", {})
    persona_key = persona.lower().replace(" ", "_")
    risk = risks.get(persona_key, risks.get(list(risks.keys())[0], {})) if risks else {}

    score = risk.get("risk_score", 0)
    level = risk.get("risk_level", "Unknown")
    symptoms = risk.get("symptoms", [])
    rec = risk.get("outdoor_recommendation", "N/A")
    actions = risk.get("preventive_actions", [])

    colour = risk_colour(score)
    # Risk score gauge
    pct = min(score / 10, 1.0) * 100
    st.markdown(f"""
    <div class="risk-bar-wrap">
        <div class="risk-label">Risk Score: <b style="color:{colour}">{score:.1f}/10 ({level})</b></div>
        <div class="risk-bar-bg"><div class="risk-bar-fill" style="width:{pct}%;background:{colour}"></div></div>
    </div>
    """, unsafe_allow_html=True)

    if h.get("alert_triggered"):
        st.markdown(f'<div class="alert-box">⚠️ {h.get("alert_message","High risk alert")}</div>', unsafe_allow_html=True)

    st.markdown(f"**Outdoor Activity:** {rec}")

    if symptoms:
        st.markdown("**Potential Symptoms:**")
        for s in symptoms[:4]:
            st.markdown(f"  · {s}")

    if actions:
        st.markdown("**Preventive Actions:**")
        for a in actions[:3]:
            st.markdown(f"  ✓ {a}")

    st.markdown("---")

    # All personas quick view
    if risks:
        st.markdown("**All Personas · Risk Scores**")
        rows = []
        for pk, pr in risks.items():
            rows.append({
                "Persona": pk.replace("_", " ").title(),
                "Score": pr.get("risk_score", 0),
                "Level": pr.get("risk_level", "?"),
            })
        df_risk = pd.DataFrame(rows).sort_values("Score", ascending=False)
        fig = px.bar(
            df_risk, x="Score", y="Persona", orientation="h",
            color="Score", color_continuous_scale=["#4ade80", "#fbbf24", "#ef4444"],
            range_color=[0, 10], height=280,
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#8b949e",
            margin=dict(l=0, r=0, t=10, b=0),
            coloraxis_showscale=False,
            xaxis=dict(range=[0, 10], gridcolor="#21262d"),
            yaxis=dict(gridcolor="rgba(0,0,0,0)"),
        )
        st.plotly_chart(fig, use_container_width=True)


def _render_station_table(readings):
    if not readings:
        return
    from config import get_aqi_label
    rows = []
    for r in readings:
        aqi = r.get("aqi", 0)
        rows.append({
            "Station": r.get("station_name", "Unknown"),
            "AQI": round(aqi),
            "Category": get_aqi_label(int(aqi)),
            "PM2.5": round(r.get("pm25") or 0, 1),
            "PM10": round(r.get("pm10") or 0, 1),
            "NO₂": round(r.get("no2") or 0, 1),
            "SO₂": round(r.get("so2") or 0, 1),
            "CO": round(r.get("co") or 0, 2),
            "O₃": round(r.get("o3") or 0, 1),
            "Source": r.get("source", "—"),
        })
    df = pd.DataFrame(rows)
    # Colour-code AQI column
    def colour_aqi(val):
        cat = get_aqi_label(int(val))
        colours = {
            "Good": "color: #4ade80",
            "Satisfactory": "color: #a3e635",
            "Moderately Polluted": "color: #fbbf24",
            "Poor": "color: #fb923c",
            "Very Poor": "color: #f87171",
            "Severe / Hazardous": "color: #ef4444",
        }
        return colours.get(cat, "")

    styled = df.style.applymap(colour_aqi, subset=["AQI"])
    st.dataframe(styled, use_container_width=True, height=280)


# ─── Ask Agent Tab ────────────────────────────────────────────────────────────
def render_ask_agent(agents):
    """
    Clean ChatGPT-style chat interface.
    Responses are minimal and conversational — no forced dashboards.
    """
    city    = st.session_state.selected_city
    persona = st.session_state.selected_persona

    # ── Suggestion chips (compact, top of chat) ───────────────────────────────
    SUGGESTIONS = [
        f"What is the AQI in {city}?",
        "Is it safe to go outside?",
        f"Which areas are most polluted in {city}?",
        "What should asthma patients do today?",
        f"Compare pollution across {city} stations",
        "What are the health risks right now?",
        "Show me a heat map",
        f"Show pollution hotspots within 5km of {city}",
    ]

    with st.container():
        chip_cols = st.columns(3)
        for i, s in enumerate(SUGGESTIONS):
            with chip_cols[i % 3]:
                if st.button(s, key=f"chip_{i}", use_container_width=True,
                             help="Click to ask this question"):
                    st.session_state["prefill_query"] = s

    st.markdown("---")

    # ── Chat history ──────────────────────────────────────────────────────────
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                if msg["role"] == "user":
                    st.markdown(msg["content"])
                else:
                    _render_chat_response(msg["content"])

    # ── Input ─────────────────────────────────────────────────────────────────
    prefill = st.session_state.pop("prefill_query", "")
    query   = st.chat_input(
        f"Ask about AQI, health risks, hotspots… (City: {city})",
        key="chat_input"
    )
    if prefill and not query:
        query = prefill

    if query:
        # 1. Show user message immediately
        with st.chat_message("user"):
            st.markdown(query)

        # 2. Compute response (spinner shown while working)
        with st.chat_message("assistant"):
            with st.spinner("Analyzing…"):
                result = _run_query(agents, query)
            _render_chat_response(result)

        # 3. Save BOTH messages to history AFTER rendering succeeds.
        #    Do this as a single atomic write so no rerun can fire between them.
        st.session_state.chat_messages.append({"role": "user",      "content": query})
        st.session_state.chat_messages.append({"role": "assistant", "content": result})
        # 4. Explicit rerun so the history container re-renders cleanly on the
        #    next pass (chat_input is now cleared, no double-render risk).
        st.rerun()


def _run_query(agents, query: str) -> dict:
    """
    Execute query through the orchestrated reasoning pipeline.
    IMPORTANT: No st.session_state mutations here — mutations inside a
    spinner context can interrupt the Streamlit render pass and cause
    content to vanish. All session_state writes happen in the caller.
    """
    city    = st.session_state.selected_city
    persona = st.session_state.selected_persona

    try:
        result = agents["reasoning"].process_query(
            query=query,
            city=city,
            persona=persona,
            uploaded_df=st.session_state.uploaded_df,
        )
        return result
    except Exception as e:
        return {"text": f"Sorry, I ran into an error: {e}", "intent": "error"}


def _render_chat_response(result):
    """
    Minimal, intent-aware response renderer.
    Shows only what the query actually needs — no forced dashboards.
    """
    if isinstance(result, str):
        st.markdown(result)
        return
    if not isinstance(result, dict):
        st.markdown(str(result))
        return

    # Error
    if result.get("error") or result.get("intent") == "error":
        st.error(result.get("text", result.get("error", "Unknown error")))
        return

    # ── Main text ──────────────────────────────────────────────────────────────
    text = result.get("text", "")
    if text:
        st.markdown(text)

    # ── Alert (only when truly needed) ────────────────────────────────────────
    alert = result.get("alert")
    if alert:
        st.markdown(
            f'<div class="alert-box">⚠️ {alert}</div>',
            unsafe_allow_html=True
        )

    # ── Comparison chart (for comparison_query intent) ────────────────────────
    comparison_data = result.get("comparison_data", [])
    if comparison_data and len(comparison_data) >= 2:
        try:
            comp_df = pd.DataFrame(comparison_data)
            comp_df = comp_df.sort_values("aqi", ascending=True)

            fig = px.bar(
                comp_df, x="aqi", y="city", orientation="h",
                color="aqi",
                color_continuous_scale=["#4ade80", "#a3e635", "#fbbf24", "#fb923c", "#f87171", "#ef4444"],
                range_color=[0, 500],
                text="aqi",
                labels={"aqi": "AQI", "city": "City"},
                height=50 + len(comparison_data) * 80,
            )
            fig.update_traces(texttemplate="%{text}", textposition="outside")
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(14,17,23,1)",
                font_color="#8b949e",
                coloraxis_showscale=False,
                xaxis=dict(gridcolor="#21262d", title=""),
                yaxis=dict(gridcolor="rgba(0,0,0,0)", title=""),
                margin=dict(l=0, r=60, t=10, b=0),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True, key=f"comp_chart_{time.time_ns()}")
        except Exception:
            pass  # graceful fallback — text is already shown above

    # ── Intent-gated visualizations ───────────────────────────────────────────
    intent   = result.get("intent", "")
    viz      = result.get("visualizations", {})
    chart    = result.get("chart")
    show_map = result.get("map", False)

    # Map — only for hotspot / comparison / gis queries
    if show_map and viz:
        fmap = viz.get("folium_map")
        if fmap:
            import folium as _folium
            pollutant = result.get("pollutant")
            radius = result.get("radius_km")
            label = "🗺️ Spatial Map"
            if pollutant and pollutant != "aqi":
                label = f"🗺️ {pollutant.upper()} Heat Map"
            elif radius and radius != 3.0:
                label = f"🗺️ Spatial Map ({radius:.0f}km radius)"
            with st.expander(label, expanded=True):
                if isinstance(fmap, _folium.Map):
                    st_folium(fmap, height=360, use_container_width=True)
                elif isinstance(fmap, str):
                    st.components.v1.html(fmap, height=360)

    # Health chart — only for health / recommendation / comparison queries
    if chart == "health" and viz:
        hc = _safe_fig(viz.get("health_chart"))
        if hc:
            with st.expander("📊 Risk by Persona", expanded=False):
                st.plotly_chart(hc, use_container_width=True, key=f"chat_chart_{time.time_ns()}")

    # ── Metadata footer (subtle, not dominant) ────────────────────────────────
    city    = result.get("city", "")
    dur     = result.get("duration_ms", 0)
    sources = (result.get("data", {}) or {}).get("sources_used", [])
    src_str = ", ".join(s.replace("_", " ").title() for s in sources) if sources else ""
    footer_parts = []
    if city:
        footer_parts.append(city)
    if src_str:
        footer_parts.append(f"Source: {src_str}")
    if dur:
        footer_parts.append(f"{dur:.0f}ms")
    if footer_parts:
        st.caption(" · ".join(footer_parts))


# ─── Legacy _run_full_pipeline alias (used by Batch tab) ─────────────────────
def _run_full_pipeline(agents, query: str) -> dict:
    return _run_query(agents, query)


# ─── Legacy _render_agent_response alias (used by history replay) ─────────────
def _render_agent_response(result):
    _render_chat_response(result)


# ─── Trend Analysis Tab ───────────────────────────────────────────────────────
def render_trends(agents):
    city = st.session_state.selected_city
    st.markdown(f"### 📈 AQI Trend Analysis · {city}")

    col1, col2, col3 = st.columns(3)
    with col1:
        days = st.slider("History (days)", 7, 90, 30)
    with col2:
        pollutants = st.multiselect(
            "Pollutants", ["AQI", "PM2.5", "PM10", "NO₂", "SO₂", "CO", "O₃"],
            default=["AQI", "PM2.5"],
        )
    with col3:
        station_filter = st.text_input("Filter station (optional)", "")

    if st.button("📊 Generate Trend", use_container_width=True):
        hist_df = pd.DataFrame()

        # Try DB first (has previously-fetched readings)
        with st.spinner("Checking local database…"):
            try:
                from data.database import db
                end_dt   = datetime.now(timezone.utc)
                start_dt = end_dt - timedelta(days=days)
                hist = db.get_historical_readings(
                    city=city, start_dt=start_dt, end_dt=end_dt,
                    limit=days * 24 * 30,
                )
                if hist:
                    hist_df = pd.DataFrame(hist)
                    st.caption(f"Loaded {len(hist_df)} readings from local database.")
            except Exception as e:
                st.caption(f"DB unavailable: {e}")

        # If DB empty or too sparse, fetch real historical data from Open-Meteo
        if hist_df.empty or len(hist_df) < days * 2:
            with st.spinner(f"Fetching {days}-day historical data from Open-Meteo…"):
                try:
                    raw = agents["data"]._fetch_open_meteo_historical(city=city, days=days)
                    if raw:
                        hist_df = pd.DataFrame(raw)
                        st.caption(
                            f"Loaded {len(hist_df)} hourly readings from Open-Meteo "
                            f"(real atmospheric model data for {city})."
                        )
                    else:
                        st.error(
                            f"Could not fetch historical data for {city}. "
                            "Check internet connection."
                        )
                        return
                except Exception as e:
                    st.error(f"Historical fetch error: {e}")
                    return

        if hist_df.empty:
            st.warning("No historical data available.")
            return

        # Ensure datetime column
        ts_col = next((c for c in ["timestamp", "datetime", "date"] if c in hist_df.columns), None)
        if ts_col:
            hist_df[ts_col] = pd.to_datetime(hist_df[ts_col], errors="coerce")
            hist_df = hist_df.dropna(subset=[ts_col])
            hist_df = hist_df.sort_values(ts_col)

        # Store in session_state so it survives reruns (e.g. when timeline
        # selectboxes change persona/activity, Streamlit reruns the script
        # and st.button returns False — without this the timeline vanishes).
        st.session_state["_trend_df"] = hist_df
        st.session_state["_trend_pollutants"] = pollutants
        st.session_state["_trend_ts_col"] = ts_col
        st.session_state["_trend_station_filter"] = station_filter

    # Render from session_state (persists across reruns)
    if "_trend_df" in st.session_state and not st.session_state["_trend_df"].empty:
        _render_trend_charts(
            st.session_state["_trend_df"],
            st.session_state.get("_trend_pollutants", pollutants),
            st.session_state.get("_trend_ts_col"),
            st.session_state.get("_trend_station_filter"),
        )


def _render_trend_charts(df, pollutants, ts_col, station_filter):
    col_map = {"AQI": "aqi", "PM2.5": "pm25", "PM10": "pm10",
               "NO₂": "no2", "SO₂": "so2", "CO": "co", "O₃": "o3"}

    if station_filter:
        station_col = next((c for c in ["station_name","station","location"] if c in df.columns), None)
        if station_col:
            df = df[df[station_col].str.contains(station_filter, case=False, na=False)]

    fig = go.Figure()
    band_colours = {
        "Good": "rgba(74,215,128,0.06)",
        "Moderate": "rgba(251,191,36,0.06)",
        "Very Poor": "rgba(248,113,113,0.06)",
    }

    for p in pollutants:
        col = col_map.get(p)
        if col and col in df.columns:
            y = pd.to_numeric(df[col], errors="coerce")
            fig.add_trace(go.Scatter(
                x=df[ts_col] if ts_col else df.index,
                y=y,
                name=p,
                mode="lines",
                line=dict(width=2),
            ))

    # AQI category bands
    if "AQI" in pollutants:
        for level, y0, y1, colour in [
            ("Good", 0, 50, "rgba(74,215,128,0.08)"),
            ("Satisfactory", 50, 100, "rgba(163,230,53,0.08)"),
            ("Moderate", 100, 200, "rgba(251,191,36,0.08)"),
            ("Poor", 200, 300, "rgba(251,146,60,0.08)"),
            ("Very Poor", 300, 400, "rgba(248,113,113,0.08)"),
            ("Severe", 400, 500, "rgba(239,68,68,0.08)"),
        ]:
            fig.add_hrect(y0=y0, y1=y1, fillcolor=colour, line_width=0, annotation_text=level,
                          annotation_position="right", annotation_font_size=9,
                          annotation_font_color="#6e7681")

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(14,17,23,1)",
        font_color="#8b949e",
        height=420,
        margin=dict(l=0, r=60, t=20, b=0),
        xaxis=dict(gridcolor="#21262d", showgrid=True),
        yaxis=dict(gridcolor="#21262d", showgrid=True),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Daily average table
    if ts_col and len(df) > 0:
        df["date"] = pd.to_datetime(df[ts_col]).dt.date
        agg_cols = {col_map[p]: "mean" for p in pollutants if col_map.get(p) in df.columns}
        if agg_cols:
            daily = df.groupby("date").agg(agg_cols).round(1).reset_index()
            daily.columns = ["Date"] + [p for p in pollutants if col_map.get(p) in df.columns]
            st.markdown("**Daily Averages**")
            st.dataframe(daily.tail(14), use_container_width=True)

    # ── Feature 4: 24h Health Risk Timeline ──────────────────────────────────
    if ts_col and "aqi" in df.columns and len(df) >= 6:
      try:
        st.markdown("---")
        st.markdown("#### 📅 24-Hour Health Risk Timeline")

        tl_col1, tl_col2 = st.columns([2, 1])
        with tl_col1:
            tl_persona = st.selectbox("Persona for timeline", [
                "general_population", "children", "elderly", "asthma_patient",
                "copd_patient", "heart_patient", "athlete", "outdoor_worker", "pregnant",
            ], format_func=lambda x: x.replace("_", " ").title(), key="tl_persona")
        with tl_col2:
            tl_activity = st.selectbox("Activity", [
                "resting", "light", "moderate", "vigorous",
            ], index=1, format_func=lambda x: x.title(), key="tl_activity")

        # Extract latest day's hourly data
        df_copy = df.copy()
        df_copy["_ts"] = pd.to_datetime(df_copy[ts_col], errors="coerce")
        df_copy["_hour"] = df_copy["_ts"].dt.hour

        # Use the most recent date with enough data
        df_copy["_date"] = df_copy["_ts"].dt.date
        latest_date = df_copy["_date"].max()
        day_df = df_copy[df_copy["_date"] == latest_date]

        if len(day_df) < 6:
            # Fall back to last 24 rows
            day_df = df_copy.tail(24)

        # Build hourly data list
        hourly_data = []
        for _, row in day_df.iterrows():
            hourly_data.append({
                "hour": int(row.get("_hour", 0)),
                "aqi": float(row.get("aqi", 0) or 0),
                "pm25": float(row.get("pm25", 0) or 0),
                "pm10": float(row.get("pm10", 0) or 0),
                "no2": float(row.get("no2", 0) or 0),
                "so2": float(row.get("so2", 0) or 0),
                "co": float(row.get("co", 0) or 0),
                "o3": float(row.get("o3", 0) or 0),
            })

        if hourly_data:
            from tools.health_tools import compute_hourly_risk_scores, get_best_outdoor_time_recommendation

            # Compute risk scores
            hourly_scores = compute_hourly_risk_scores(
                hourly_data, tl_persona, activity_level=tl_activity,
            )

            # Build chart
            hours = [f"{s['hour']:02d}:00" for s in hourly_scores]
            scores = [s["risk_score"] for s in hourly_scores]
            aqis = [s["aqi"] for s in hourly_scores]
            levels = [s["risk_level"] for s in hourly_scores]
            is_safe = [s["is_safe"] for s in hourly_scores]

            risk_colors = {
                "Minimal": "#4ade80", "Low": "#a3e635", "Moderate": "#fbbf24",
                "High": "#fb923c", "Very High": "#f87171", "Critical": "#ef4444",
            }
            bar_colors = [risk_colors.get(l, "#8b949e") for l in levels]

            fig_tl = go.Figure()
            fig_tl.add_trace(go.Bar(
                x=hours, y=scores,
                marker_color=bar_colors,
                text=[f"{s:.1f}" for s in scores],
                textposition="outside",
                hovertext=[
                    f"<b>{h}</b><br>AQI: {a:.0f}<br>Risk: {l} ({s:.1f}/10)"
                    for h, a, l, s in zip(hours, aqis, levels, scores)
                ],
                hoverinfo="text",
            ))
            fig_tl.add_hline(y=4.0, line_dash="dash", line_color="#4ade80",
                             annotation_text="Safe", annotation_position="top right",
                             annotation_font_color="#4ade80", annotation_font_size=10)
            fig_tl.add_hline(y=7.5, line_dash="dash", line_color="#f87171",
                             annotation_text="Danger", annotation_position="top right",
                             annotation_font_color="#f87171", annotation_font_size=10)

            for i, safe in enumerate(is_safe):
                if safe:
                    fig_tl.add_vrect(x0=i-0.4, x1=i+0.4,
                                     fillcolor="rgba(74, 222, 128, 0.08)", line_width=0)

            from tools.health_tools import PERSONA_RULES
            label = PERSONA_RULES.get(tl_persona, {}).get("label", tl_persona.replace("_"," ").title())
            fig_tl.update_layout(
                title=f"24h Risk Timeline — {label} · {tl_activity.title()} activity",
                xaxis_title="Hour of Day",
                yaxis=dict(title="Risk Score (0–10)", range=[0, 11]),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(14,17,23,1)",
                font_color="#8b949e", height=380,
                margin=dict(l=40, r=40, t=60, b=40),
                showlegend=False, hovermode="x unified",
            )
            st.plotly_chart(fig_tl, use_container_width=True, key=f"risk_timeline_{time.time_ns()}")

            # Best outdoor time recommendation
            hourly_aqi_map = {f"{e['hour']:02d}:00": e["aqi"] for e in hourly_data}
            best_time = get_best_outdoor_time_recommendation(hourly_aqi_map, tl_persona)
            st.markdown(f'<div class="info-box">{best_time}</div>', unsafe_allow_html=True)

            # Safe hours summary
            safe_count = sum(1 for s in is_safe if s)
            danger_count = sum(1 for l in levels if l in ("Very High", "Critical"))
            s_col1, s_col2, s_col3 = st.columns(3)
            with s_col1:
                st.metric("✅ Safe Hours", f"{safe_count}/{len(hourly_scores)}")
            with s_col2:
                st.metric("⚠️ Danger Hours", danger_count)
            with s_col3:
                avg_risk = sum(scores) / len(scores) if scores else 0
                st.metric("Avg Risk Score", f"{avg_risk:.1f}/10")

      except Exception as e:
        st.error(f"❌ Timeline error: {e}")
        import traceback
        st.code(traceback.format_exc(), language="text")

# ─── GIS / Spatial Tab ───────────────────────────────────────────────────────
def _render_gis_results(gis_state: dict):
    """Render GIS results from session_state — called every rerun."""
    gis_data  = gis_state.get("gis_data", {})
    viz_data  = gis_state.get("viz_data", {})
    data_payload = gis_state.get("data_payload", {})
    city      = gis_state.get("city", "Mumbai")

    clusters = gis_data.get("clusters", [])
    hotspots = gis_data.get("hotspot_stations", [])
    summary  = gis_data.get("spatial_summary", "")

    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        st.metric("Pollution Clusters", len(clusters))
    with mc2:
        st.metric("Hotspot Stations", len(hotspots))
    with mc3:
        avg_aqi_cluster = sum(c.get("avg_aqi", 0) for c in clusters) / max(len(clusters), 1)
        st.metric("Avg Cluster AQI", f"{avg_aqi_cluster:.0f}")

    map_col, info_col = st.columns([3, 2])
    with map_col:
        fmap = viz_data.get("folium_map")
        if fmap and isinstance(fmap, str):
            # Stored as HTML string (preferred — survives session_state reruns)
            st.components.v1.html(fmap, height=450, scrolling=True)
        elif fmap and hasattr(fmap, "_repr_html_"):
            # Live Folium Map object (fallback if called directly without storage)
            st_folium(fmap, height=450, use_container_width=True)
        else:
            # No map from viz agent — render basic station dots
            readings = data_payload.get("readings", [])
            _render_quick_map(readings, city)

    with info_col:
        if summary:
            st.markdown("**Spatial Summary**")
            st.markdown(f'<div class="info-box">{summary}</div>', unsafe_allow_html=True)

        if hotspots:
            st.markdown("**🔴 Hotspot Stations**")
            for h in hotspots[:5]:
                st.markdown(f"- **{h.get('station_name','?')}** · AQI {h.get('aqi',0):.0f}")

        if clusters:
            st.markdown("**Cluster Details**")
            for c in clusters:
                label = c.get("label", "?")
                n     = c.get("station_count", 0)
                avg   = c.get("avg_aqi", 0)
                worst = c.get("worst_pollutant", "?")
                st.markdown(f"**Cluster {label}** · {n} stations · AQI {avg:.0f} · Worst: {worst}")


def render_gis(agents):
    city = st.session_state.selected_city
    st.markdown(f"### 🗺️ Spatial Intelligence · {city}")

    run_col, opt_col = st.columns([2, 1])
    with run_col:
        run_gis = st.button("🔍 Run Spatial Analysis", use_container_width=True)
    with opt_col:
        show_heatmap = st.checkbox("Heatmap layer", value=True)

    # ── Button clicked: compute and SAVE to session_state ─────────────────────
    if run_gis:
        with st.spinner("Running GIS analysis…"):
            data_out = agents["data"].run(city=city, uploaded_df=None)
            gis_out  = agents["gis"].run(data_output=data_out.payload, city=city)
            viz_out  = agents["visualization"].run(
                data_output=data_out.payload,
                gis_output=gis_out.payload,
                city=city,
                show_heatmap=show_heatmap,
            )
        # Store everything in session_state so it survives reruns.
        # IMPORTANT: Convert Folium Map objects → HTML strings before storing,
        # because Folium Map objects don't serialise reliably in session_state.
        viz_payload = viz_out.payload or {}
        fmap = viz_payload.get("folium_map")
        if fmap and hasattr(fmap, "_repr_html_"):
            viz_payload["folium_map"] = fmap._repr_html_()

        st.session_state["gis_result"] = {
            "gis_data":    gis_out.payload or {},
            "viz_data":    viz_payload,
            "data_payload": data_out.payload or {},
            "city":        city,
        }

    # ── Always render from session_state (survives every rerun) ───────────────
    if "gis_result" in st.session_state and st.session_state["gis_result"].get("city") == city:
        _render_gis_results(st.session_state["gis_result"])
    elif "gis_result" in st.session_state:
        # City changed — clear stale result
        del st.session_state["gis_result"]
        st.info("City changed. Click **Run Spatial Analysis** to refresh.")


# ─── Health Analysis Tab ──────────────────────────────────────────────────────
def render_health(agents):
    city = st.session_state.selected_city
    st.markdown(f"### 🏥 Health Risk Analysis · {city}")

    col_p, col_h, col_btn = st.columns([2, 1, 1])
    with col_p:
        persona = st.selectbox("Focus persona", [
            "General Population", "Children", "Elderly", "Asthma Patients",
            "COPD Patients", "Heart Patients", "Athletes", "Outdoor Workers",
            "Pregnant Women", "Diabetic Patients",
        ], key="health_persona")
    with col_h:
        exposure = st.number_input("Exposure hours/day", 1, 24, 8)
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        run_health = st.button("🔬 Analyze", use_container_width=True)

    # Feature 2: Exposure context controls
    ctx_col1, ctx_col2 = st.columns(2)
    with ctx_col1:
        activity_level = st.select_slider(
            "🏃 Activity Level",
            options=["resting", "light", "moderate", "vigorous"],
            value="light",
            format_func=lambda x: {
                "resting": "🛋️ Resting (6–10 L/min)",
                "light": "🚶 Light (15–25 L/min)",
                "moderate": "🚴 Moderate (30–50 L/min)",
                "vigorous": "🏃 Vigorous (60–100 L/min)",
            }.get(x, x),
        )
    with ctx_col2:
        environment = st.select_slider(
            "🏠 Environment",
            options=["outdoor", "indoor_no_filter", "indoor_basic", "indoor_hepa"],
            value="outdoor",
            format_func=lambda x: {
                "outdoor": "🌳 Outdoor (full exposure)",
                "indoor_no_filter": "🏠 Indoor (no filter)",
                "indoor_basic": "❄️ Indoor (basic AC)",
                "indoor_hepa": "🌀 Indoor (HEPA filter)",
            }.get(x, x),
        )

    if run_health:
        with st.spinner("Running health analysis pipeline…"):
            data_out   = agents["data"].run(city=city, uploaded_df=st.session_state.uploaded_df)
            health_out = agents["health"].run(
                data_output=data_out.payload,
                persona=persona,
                exposure_hours=exposure,
                activity_level=activity_level,
                environment=environment,
            )
            exp_out = agents["explanation"].run(
                data_output=data_out.payload,
                health_output=health_out.payload,
                query=f"Health risk for {persona} in {city} with {exposure}h exposure",
                city=city,
                persona=persona,
            )

        # Store results in session_state so they persist across reruns
        st.session_state["health_result"] = {
            "health_payload": health_out.payload or {},
            "exp_payload":    exp_out.payload or {},
            "persona":        persona,
            "city":           city,
        }

    # Always render from session_state
    if "health_result" in st.session_state and st.session_state["health_result"].get("city") == city:
        hr = st.session_state["health_result"]
        _render_health_detail(hr["health_payload"], hr["exp_payload"], hr["persona"])



def _render_health_detail(health_data: dict, exp_data: dict, focus_persona: str):
    risks = health_data.get("persona_risks", {})
    pollutant_notes = health_data.get("pollutant_notes", [])
    alert = health_data.get("alert_triggered", False)
    alert_msg = health_data.get("alert_message", "")
    danger_zones = health_data.get("danger_zones", [])
    hazard_index = health_data.get("hazard_index", 0)
    hazard_interp = health_data.get("hazard_interpretation", "")
    synergy_warnings = health_data.get("synergy_warnings", [])
    mask_rec = health_data.get("mask_recommendation", "")

    if alert:
        st.markdown(f'<div class="alert-box">⚠️ ALERT: {alert_msg}</div>', unsafe_allow_html=True)

    # ── Feature 3: Synergy Warnings ───────────────────────────────────────────
    if synergy_warnings:
        st.markdown("#### ⚗️ Pollutant Interaction Warnings")
        for sw in synergy_warnings:
            st.markdown(
                f'<div class="alert-box" style="border-left-color:#fb923c">'
                f'🧬 <b>Synergy Effect:</b> {sw}</div>',
                unsafe_allow_html=True,
            )

    # ── Feature 1: Hazard Index + Feature 2: Mask + Exposure Context ──────────
    hi_col, mask_col, ctx_col = st.columns(3)
    with hi_col:
        hi_color = "#4ade80" if hazard_index <= 0.5 else "#fbbf24" if hazard_index <= 1.0 else "#fb923c" if hazard_index <= 2.0 else "#ef4444"
        st.markdown(f"""<div class="metric-card">
            <h3>⚗️ Hazard Index (WHO)</h3>
            <div class="value" style="font-size:2rem;color:{hi_color}">{hazard_index:.2f}</div>
            <div class="sub">{hazard_interp}</div>
        </div>""", unsafe_allow_html=True)

    with mask_col:
        if mask_rec:
            st.markdown(f"""<div class="metric-card">
                <h3>😷 Mask Advice</h3>
                <div class="sub" style="font-size:0.95rem">{mask_rec}</div>
            </div>""", unsafe_allow_html=True)

    with ctx_col:
        exp_ctx = health_data.get("exposure_context", {})
        if exp_ctx:
            act_labels = {"resting": "🛋️ Resting", "light": "🚶 Light", "moderate": "🚴 Moderate", "vigorous": "🏃 Vigorous"}
            env_labels = {"outdoor": "🌳 Outdoor", "indoor_no_filter": "🏠 Indoor", "indoor_basic": "❄️ Indoor (AC)", "indoor_hepa": "🌀 HEPA"}
            st.markdown(f"""<div class="metric-card">
                <h3>📋 Exposure Context</h3>
                <div class="sub"><b>Activity:</b> {act_labels.get(exp_ctx.get('activity_level','light'), exp_ctx.get('activity_level',''))}<br>
                <b>Environment:</b> {env_labels.get(exp_ctx.get('environment','outdoor'), exp_ctx.get('environment',''))}<br>
                <b>Duration:</b> {exp_ctx.get('exposure_hours',8)}h</div>
            </div>""", unsafe_allow_html=True)

    if exp_data.get("health_explanation"):
        st.markdown(f'<div class="info-box">{exp_data["health_explanation"]}</div>', unsafe_allow_html=True)

    # Focus persona deep dive
    persona_key = focus_persona.lower().replace(" ", "_")
    risk = risks.get(persona_key, next(iter(risks.values()), {})) if risks else {}

    if risk:
        score = risk.get("risk_score", 0)
        level = risk.get("risk_level", "?")
        colour = risk_colour(score)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"#### {focus_persona} Risk Profile")
            st.markdown(f"""
            **Risk Level:** <span style="color:{colour}"><b>{level}</b></span>  
            **Risk Score:** {score:.1f} / 10  
            **Outdoor Rec:** {risk.get('outdoor_recommendation','N/A')}
            """, unsafe_allow_html=True)

            st.markdown("**Symptoms to watch:**")
            for s in risk.get("symptoms", [])[:5]:
                st.markdown(f"  - {s}")

        with col2:
            st.markdown("**Short-term impact:**")
            st.markdown(risk.get("short_term_note", "N/A"))
            st.markdown("**Long-term impact:**")
            st.markdown(risk.get("long_term_note", "N/A"))
            st.markdown("**Preventive actions:**")
            for a in risk.get("preventive_actions", [])[:4]:
                st.markdown(f"  ✓ {a}")

    st.markdown("---")

    # All-persona comparison chart
    if risks:
        st.markdown("#### All Personas · Risk Score Comparison")
        rows = []
        for pk, pr in risks.items():
            rows.append({
                "Persona": pk.replace("_"," ").title(),
                "Risk Score": pr.get("risk_score", 0),
                "Risk Level": pr.get("risk_level", "?"),
            })
        df = pd.DataFrame(rows).sort_values("Risk Score", ascending=True)
        fig = px.bar(
            df, x="Risk Score", y="Persona", orientation="h",
            color="Risk Score",
            color_continuous_scale=["#4ade80","#fbbf24","#fb923c","#ef4444"],
            range_color=[0,10], height=340, text="Risk Score",
        )
        fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(14,17,23,1)",
            font_color="#8b949e", coloraxis_showscale=False,
            xaxis=dict(range=[0,11], gridcolor="#21262d"),
            yaxis=dict(gridcolor="rgba(0,0,0,0)"),
            margin=dict(l=0,r=40,t=10,b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Pollutant notes
    if pollutant_notes:
        st.markdown("#### Pollutant Health Notes")
        cols = st.columns(3)
        for i, note in enumerate(pollutant_notes):
            with cols[i % 3]:
                st.markdown(f"""<div class="metric-card">
                    <h3>{note.get('pollutant','').upper()}</h3>
                    <div class="value" style="font-size:1.1rem">{note.get('value','N/A')} {note.get('unit','')}</div>
                    <div class="sub">{note.get('health_note','')}</div>
                </div>""", unsafe_allow_html=True)

    # Danger zones
    if danger_zones:
        st.markdown("#### 🔴 Danger Zones")
        dz_rows = []
        for dz in danger_zones:
            dz_rows.append({
                "Station": dz.get("station_name","?"),
                "AQI": dz.get("aqi",0),
                "PM2.5": dz.get("pm25","?"),
                "Reason": dz.get("reason","?"),
            })
        st.dataframe(pd.DataFrame(dz_rows), use_container_width=True)


# ─── Batch Analysis Tab ───────────────────────────────────────────────────────
def render_batch(agents):
    st.markdown("### 📦 Batch Analysis")
    st.info("Upload a CSV and run a full pipeline analysis across all stations, personas, and pollutants.")

    df = st.session_state.uploaded_df
    if df is None:
        st.warning("Upload a CSV from the sidebar to begin batch analysis.")
        return

    st.markdown(f"**Loaded:** `{len(df)} rows × {len(df.columns)} columns`")
    st.dataframe(df.head(10), use_container_width=True)

    col_city, col_run = st.columns([2, 1])
    with col_city:
        city_override = st.text_input("City label for this data", st.session_state.selected_city)
    with col_run:
        st.markdown("<br>", unsafe_allow_html=True)
        run_batch = st.button("🚀 Run Full Batch Analysis", use_container_width=True)

    if run_batch:
        progress = st.progress(0, text="Starting pipeline…")
        status   = st.empty()

        progress.progress(0.05, text="Data Agent — ingesting…")
        data_out = agents["data"].run(city=city_override, uploaded_df=df)
        progress.progress(0.20, text="GIS Agent…")

        gis_out = agents["gis"].run(data_output=data_out.payload, city=city_override)
        progress.progress(0.45, text="Health Agent…")

        health_out = agents["health"].run(
            data_output=data_out.payload, persona=None, exposure_hours=8
        )
        progress.progress(0.65, text="Visualization…")

        viz_out = agents["visualization"].run(
            data_output=data_out.payload,
            gis_output=gis_out.payload,
            health_output=health_out.payload,
            city=city_override,
        )
        progress.progress(0.85, text="Explanation…")

        exp_out = agents["explanation"].run(
            data_output=data_out.payload,
            gis_output=gis_out.payload,
            health_output=health_out.payload,
            query=f"Full batch analysis for {city_override}",
            city=city_override,
        )
        progress.progress(1.0, text="Complete!")

        # Convert folium map to HTML string so it survives session_state reruns
        viz_data = viz_out.payload or {}
        fmap = viz_data.get("folium_map")
        if fmap and hasattr(fmap, "_repr_html_"):
            viz_data["folium_map"] = fmap._repr_html_()

        # Store results in session_state so they survive reruns
        st.session_state["batch_result"] = {
            "data_payload":  data_out.payload or {},
            "health_payload": health_out.payload or {},
            "gis_payload":   gis_out.payload or {},
            "exp_payload":   exp_out.payload or {},
            "viz_payload":   viz_data,
            "city":          city_override,
        }

    # ── Always render from session_state (survives reruns) ─────────────────────
    if "batch_result" in st.session_state:
        batch = st.session_state["batch_result"]
        exp_data    = batch["exp_payload"]
        health_data = batch["health_payload"]
        viz_data    = batch["viz_payload"]
        batch_city  = batch["city"]

        st.success("Batch analysis complete!")

        if exp_data.get("summary"):
            st.markdown("#### Executive Summary")
            st.markdown(exp_data["summary"])

        _render_health_detail(health_data, exp_data, "General Population")

        if viz_data.get("folium_map"):
            fmap_b = viz_data["folium_map"]
            st.markdown("#### AQI Map")
            if isinstance(fmap_b, str):
                st.components.v1.html(fmap_b, height=420, scrolling=True)
            elif hasattr(fmap_b, "_repr_html_"):
                st_folium(fmap_b, height=420, use_container_width=True)

        if viz_data.get("health_chart"):
            hc = _safe_fig(viz_data["health_chart"])
            if hc:
                st.plotly_chart(hc, use_container_width=True, key=f"batch_hchart_{time.time_ns()}")

        # Export
        st.markdown("#### Export Results")
        export = {
            "timestamp": datetime.utcnow().isoformat(),
            "city": batch_city,
            "data_summary": {k: v for k, v in batch["data_payload"].items() if k != "readings"},
            "health_summary": health_data,
            "gis_summary": batch["gis_payload"],
            "explanation": exp_data,
        }
        st.download_button(
            "📥 Download JSON Report",
            data=json.dumps(export, indent=2, default=str),
            file_name=f"aqi_report_{batch_city}_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
        )


# ─── System Info Tab ──────────────────────────────────────────────────────────
def render_system_info(agents):
    st.markdown("### ⚙️ System Information")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Agent Registry")
        agent_info = {
            "🧠 Reasoning Agent": "Query understanding, orchestration, LLM planning",
            "📡 Data Agent": "AQI ingestion, cleaning, storage, fallback chain",
            "🗺️ GIS Agent": "Spatial clustering, heatmaps, hotspot detection",
            "🏥 Health Agent": "Persona risk scoring, pollutant health effects",
            "📊 Visualization Agent": "Folium maps, Plotly charts, dashboards",
            "💬 Explanation Agent": "LLM narrative generation, recommendations",
        }
        for name, desc in agent_info.items():
            st.markdown(f"""<div class="metric-card">
                <h3>{name}</h3>
                <div class="sub" style="color:#8b949e;font-size:0.82rem">{desc}</div>
            </div>""", unsafe_allow_html=True)

    with col2:
        st.markdown("#### Environment")
        env_vars = {
            "GROQ_API_KEY": os.getenv("GROQ_API_KEY", ""),
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
            "WAQI_API_KEY": os.getenv("WAQI_API_KEY", ""),
            "LLM_PROVIDER": os.getenv("LLM_PROVIDER", "groq"),
            "DB_PATH": os.getenv("DB_PATH", "data/db/aqi.db"),
            "CHROMA_PATH": os.getenv("CHROMA_PATH", "data/chroma"),
        }
        for k, v in env_vars.items():
            masked = "✓ Set" if v and k.endswith("_KEY") else (v or "⚠ Not set")
            status = "🟢" if v else "🔴"
            st.markdown(f"{status} **{k}**: `{masked}`")

        st.markdown("#### Query History")
        if st.session_state.query_history:
            for q in st.session_state.query_history[-5:][::-1]:
                st.markdown(f"- [{q['time']}] **{q['city']}** · {q['query'][:60]}…")
        else:
            st.caption("No queries yet.")

        st.markdown("#### Database")
        try:
            from data.database import db
            stats = db.get_city_aqi_stats(st.session_state.selected_city)
            if stats:
                st.markdown(f"- **Readings:** {stats.get('reading_count',0)}")
                st.markdown(f"- **Avg AQI:** {stats.get('avg_aqi',0):.1f}")
                st.markdown(f"- **Max AQI:** {stats.get('max_aqi',0):.1f}")
        except Exception as e:
            st.caption(f"DB stats unavailable: {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    render_sidebar()

    # Header
    st.markdown("""
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
        <span style="font-size:2rem">🌫️</span>
        <div>
            <div style="font-size:1.5rem;font-weight:700;color:#f0f6fc;line-height:1.1">AQI Health Risk Intelligence</div>
            <div style="font-size:0.82rem;color:#6e7681">Multi-Agent AI System · India AQI Analysis Platform</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Load agents (cached)
    with st.spinner("Initializing agent system…"):
        try:
                if "agents" not in st.session_state:
                    st.session_state.agents = load_agents()

                agents = st.session_state.agents
        except Exception as e:
            st.error(f"Failed to initialize agents: {e}")
            st.exception(e)
            return

    # Tab navigation
    tabs = st.tabs(["📊 Dashboard", "🤖 Ask Agent", "📈 Trends", "🗺️ GIS Map", "🏥 Health", "📦 Batch", "⚙️ System"])

    with tabs[0]:
        render_dashboard(agents)
    with tabs[1]:
        render_ask_agent(agents)
    with tabs[2]:
        render_trends(agents)
    with tabs[3]:
        render_gis(agents)
    with tabs[4]:
        render_health(agents)
    with tabs[5]:
        render_batch(agents)
    with tabs[6]:
        render_system_info(agents)


if __name__ == "__main__":
    main()
