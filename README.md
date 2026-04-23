# 🌫️ Multi-Agent AQI Health Risk Intelligence System

A production-grade **Multi-Agent AI platform** for real-time and historical AQI analysis, geospatial pollution mapping, and persona-aware health risk scoring — built for Indian cities, with Mumbai as the primary target.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Streamlit UI (app.py)                    │
│   Dashboard │ Ask Agent │ Trends │ GIS Map │ Health │ Batch     │
└────────────────────────┬────────────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │   Reasoning Agent   │  ← LLM orchestrator
              │  (central planner)  │    (Groq / OpenAI)
              └──────┬──────────────┘
                     │ coordinates
         ┌───────────┼────────────────────────┐
         │           │                        │
   ┌─────▼────┐ ┌────▼─────┐ ┌──────────────▼──────┐
   │  Data    │ │   GIS    │ │    Health Agent      │
   │  Agent   │ │  Agent   │ │  (persona risk ×10)  │
   └─────┬────┘ └────┬─────┘ └──────────────┬───────┘
         │           │                       │
   ┌─────▼───────────▼───────────────────────▼───────┐
   │            Visualization Agent                   │
   │    Folium maps │ Plotly charts │ Heatmaps        │
   └────────────────────────┬────────────────────────┘
                            │
              ┌─────────────▼────────────┐
              │     Explanation Agent    │
              │  LLM narrative + RAG     │
              └──────────────────────────┘
```

### Agent Responsibilities

| Agent | Role |
|---|---|
| **Reasoning Agent** | Interprets NL queries, plans steps, orchestrates agents, uses LLM function-calling |
| **Data Agent** | WAQI → OpenWeather → scraping → CSV fallback; cleans, normalises, stores to SQLite + ChromaDB |
| **GIS Agent** | DBSCAN clustering, hotspot detection, heatmap data, region comparison |
| **Health Agent** | 10-persona risk scoring, pollutant health effects, AQI→symptom mapping |
| **Visualization Agent** | Folium maps, Plotly trend/health/heatmap charts |
| **Explanation Agent** | RAG-augmented LLM summaries, recommendations, alerts |

---

## Folder Structure

```
aqi_multiagent/
├── app.py                    # Streamlit UI (6 tabs)
├── config.py                 # AQI categories, personas, city coords
├── requirements.txt
├── .env.example
│
├── agents/
│   ├── base_agent.py         # Abstract base with timing + DB logging
│   ├── reasoning_agent.py    # Orchestrator, LLM planner
│   ├── data_agent.py         # Data ingestion + fallback chain
│   ├── gis_agent.py          # Spatial analysis + DBSCAN
│   ├── health_agent.py       # Persona risk engine
│   ├── visualization_agent.py# Map + chart generation
│   └── explanation_agent.py  # LLM narrative + RAG
│
├── schemas/
│   └── agent_messages.py     # Pydantic v2 schemas for all messages
│
├── tools/
│   ├── aqi_tools.py          # CPCB AQI calculation utilities
│   ├── geo_tools.py          # Haversine, geocoding, bounding boxes
│   └── health_tools.py       # Risk scoring, pollutant health effects
│
├── data/
│   ├── database.py           # SQLAlchemy SQLite layer
│   ├── vector_store.py       # ChromaDB + sentence-transformers
│   ├── sample_data.py        # Realistic Mumbai mock data generator
│   ├── db/                   # SQLite database files
│   └── chroma/               # ChromaDB persistence
│
├── utils/
│   ├── logger.py             # Loguru rotating logger
│   └── retry.py              # Tenacity retry decorators
│
└── logs/                     # Application logs
```

---

## Quick Start

### 1. Clone & Install

```bash
git clone <your-repo>
cd aqi_multiagent
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# LLM (at least one required for AI explanations)
GROQ_API_KEY=gsk_...           # https://console.groq.com
OPENAI_API_KEY=sk-...          # Optional fallback

# AQI Data APIs (optional — system works without them using mock data)
WAQI_API_KEY=your_waqi_key     # https://aqicn.org/api/
OPENWEATHER_API_KEY=...        # https://openweathermap.org/api

# Choose LLM provider
LLM_PROVIDER=groq              # or: openai

# Storage paths
DB_PATH=data/db/aqi.db
CHROMA_PATH=data/chroma
```

### 3. Launch

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`

---

## Features

### Dashboard Tab
- Live AQI metrics for selected city
- Interactive Folium station map
- Health risk panel for selected persona
- All-persona risk bar chart
- Station detail table with colour-coded AQI

### Ask Agent Tab
- Natural language queries to the full multi-agent pipeline
- Suggested quick-queries
- Chat history with structured responses (maps, charts, health data)
- Example queries:
  - *"Show AQI trends in Mumbai"*
  - *"Which areas are dangerous for asthma patients?"*
  - *"What is the best time to go outdoors for an elderly person?"*
  - *"Detect pollution hotspots"*

### Trends Tab
- Historical AQI time-series (7–90 days)
- Multi-pollutant overlay (PM2.5, PM10, NO₂, SO₂, CO, O₃)
- AQI category background bands
- Daily averages table
- Station-level filtering

### GIS Map Tab
- DBSCAN spatial clustering
- Heatmap overlay
- Hotspot identification
- Cluster summary with worst pollutant

### Health Analysis Tab
- 10-persona deep-dive:
  - Children, Elderly, Asthma, COPD, Heart, Athletes, Outdoor Workers, Pregnant Women, Diabetic Patients, General Population
- Risk score gauge (0–10)
- Symptom list, short/long-term impacts
- Preventive action checklist
- Outdoor activity recommendation
- Pollutant health notes
- Danger zone table

### Batch Analysis Tab
- Upload any CSV with AQI/pollutant columns
- Full pipeline run (all 5 agents)
- Progress bar with live step feedback
- Downloadable JSON report

---

## Data Sources & Fallback Chain

```
1. WAQI API (primary)          — aqicn.org/api/
2. OpenWeather Air Pollution   — openweathermap.org/api/air-pollution
3. Web scraping                — aqi.in, waqi.info
4. User CSV upload             — any standard AQI CSV
5. Mock data                   — realistic Mumbai profile (always available)
```

The system **never fails** — it gracefully degrades through the fallback chain.

---

## Agent Communication (JSON Schema)

All agents communicate via `AgentMessage`:

```json
{
  "message_id": "uuid",
  "source_agent": "REASONING",
  "target_agent": "HEALTH",
  "timestamp": "2024-01-01T00:00:00Z",
  "status": "success",
  "payload": {
    "data_output": { "readings": [...], "city": "Mumbai" },
    "persona": "asthma_patients",
    "exposure_hours": 8
  },
  "errors": []
}
```

### Example Health Output

```json
{
  "persona_risks": {
    "asthma_patients": {
      "risk_score": 7.8,
      "risk_level": "High",
      "symptoms": ["Wheezing", "Chest tightness", "Shortness of breath"],
      "outdoor_recommendation": "Avoid outdoor activity. Stay indoors with air purifier.",
      "preventive_actions": ["Use prescribed inhaler", "Wear N95 mask", "Avoid traffic zones"],
      "short_term_note": "Immediate bronchospasm risk with PM2.5 > 60 µg/m³",
      "long_term_note": "Chronic exposure accelerates lung function decline"
    }
  },
  "alert_triggered": true,
  "alert_message": "AQI 287 — Hazardous for sensitive groups",
  "pollutant_notes": [
    { "pollutant": "pm25", "value": 89.3, "unit": "µg/m³", "health_note": "5.9× WHO limit — high cardiovascular risk" }
  ]
}
```

---

## AQI Categories (India CPCB)

| Range | Category | Colour |
|---|---|---|
| 0–50 | Good | 🟢 |
| 51–100 | Satisfactory | 🟡 |
| 101–200 | Moderate | 🟠 |
| 201–300 | Poor | 🔴 |
| 301–400 | Very Poor | 🟣 |
| 401–500 | Severe | ⚫ |

---

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

```bash
docker build -t aqi-system .
docker run -p 8501:8501 --env-file .env aqi-system
```

### Streamlit Cloud

1. Push to GitHub
2. Connect at [share.streamlit.io](https://share.streamlit.io)
3. Set secrets from `.env.example` in the Streamlit Cloud secrets panel
4. Deploy

### Production Hardening

- **Rate limiting**: Add Redis-based rate limiting on API calls
- **Caching**: Cache WAQI responses for 15 minutes with `@st.cache_data(ttl=900)`
- **Auth**: Add `streamlit-authenticator` for multi-user support
- **Monitoring**: Integrate Loguru → ELK stack or Datadog
- **Scaling**: Replace SQLite with PostgreSQL for multi-user concurrent writes
- **Vector DB**: Replace ChromaDB with Pinecone or Weaviate for production scale
- **Async**: Move agent orchestration to FastAPI + Celery for background tasks

---

## Optional FastAPI Backend

```bash
# If you want a REST API layer:
uvicorn api.main:app --reload --port 8000
```

Endpoints:
- `POST /api/analyze` — full pipeline run
- `GET /api/aqi/{city}` — latest readings
- `GET /api/health/{city}/{persona}` — risk scores
- `GET /api/health` — system health check

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit, streamlit-folium |
| Agents | Python 3.11, custom agent framework |
| LLM | Groq (openai/gpt-oss-120b), OpenAI (gpt-4o-mini) |
| Geospatial | Folium, GeoPandas |
| Charts | Plotly |
| ML | scikit-learn (DBSCAN) |
| Storage | SQLite (SQLAlchemy), ChromaDB |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Data | pandas, NumPy |
| HTTP | aiohttp, requests, BeautifulSoup4 |
| Logging | Loguru |
| Retries | Tenacity |
| Validation | Pydantic v2 |

---

## Research & Portfolio Notes

This system demonstrates:
- **Multi-agent orchestration** with structured JSON communication
- **RAG pipeline** (ChromaDB + sentence-transformers + LLM)
- **Health domain expertise** encoded as deterministic rules (not hallucinated by LLM)
- **Geospatial ML** (DBSCAN clustering on pollution data)
- **Graceful degradation** through a 5-layer data fallback chain
- **Production patterns**: retry logic, structured logging, DB persistence, schema validation

Suitable as a **portfolio project** or foundation for a **startup-grade environmental health product**.

---

## License

MIT License — see `LICENSE` for details.
