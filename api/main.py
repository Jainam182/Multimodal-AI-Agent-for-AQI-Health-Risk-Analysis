"""
Optional FastAPI backend — exposes the multi-agent system as a REST API.
Run: uvicorn api.main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import pandas as pd
import io
import sys
import os

# Allow imports from parent dir when run as module
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

app = FastAPI(
    title="AQI Health Risk Intelligence API",
    description="Multi-Agent AI System for AQI and Health Risk Analysis",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Lazy-load agents once ──────────────────────────────────────────────────────
_agents = None

def get_agents():
    global _agents
    if _agents is None:
        from agents.reasoning_agent import ReasoningAgent
        from agents.data_agent import DataAgent
        from agents.gis_agent import GISAgent
        from agents.health_agent import HealthAgent
        from agents.visualization_agent import VisualizationAgent
        from agents.explanation_agent import ExplanationAgent
        _agents = {
            "reasoning": ReasoningAgent(),
            "data": DataAgent(),
            "gis": GISAgent(),
            "health": HealthAgent(),
            "visualization": VisualizationAgent(),
            "explanation": ExplanationAgent(),
        }
    return _agents


# ── Request / Response models ──────────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    query: str
    city: str = "Mumbai"
    persona: str = "General Population"
    exposure_hours: int = 8

class AQIResponse(BaseModel):
    city: str
    readings: list
    avg_aqi: float
    category: str
    station_count: int

class HealthResponse(BaseModel):
    city: str
    persona: str
    risk_score: float
    risk_level: str
    symptoms: list
    outdoor_recommendation: str
    preventive_actions: list
    alert_triggered: bool


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "AQI Intelligence API", "version": "1.0.0"}


# ── Full pipeline ──────────────────────────────────────────────────────────────
@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    """Run the full multi-agent pipeline for a natural language query."""
    agents = get_agents()
    try:
        result = agents["reasoning"].process_query(
            query=req.query,
            city=req.city,
            persona=req.persona,
        )
        # Strip non-serializable objects (Folium maps, Plotly figs)
        def sanitize(obj):
            if isinstance(obj, dict):
                return {k: sanitize(v) for k, v in obj.items()
                        if not hasattr(v, "_repr_html_")}
            if isinstance(obj, list):
                return [sanitize(i) for i in obj]
            return obj
        return JSONResponse(content=sanitize(result))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── AQI Data ───────────────────────────────────────────────────────────────────
@app.get("/api/aqi/{city}")
def get_aqi(city: str):
    """Get latest AQI readings for a city."""
    from schemas.agent_messages import AgentMessage, AgentName
    import uuid
    agents = get_agents()
    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        source_agent=AgentName.REASONING,
        target_agent=AgentName.DATA,
        payload={"city": city, "uploaded_df": None},
    )
    out = agents["data"].run(msg)
    payload = out.payload or {}
    readings = payload.get("readings", [])
    from config import get_aqi_category
    avg_aqi = sum(r.get("aqi", 0) for r in readings) / max(len(readings), 1)
    return {
        "city": city,
        "readings": readings,
        "avg_aqi": round(avg_aqi, 1),
        "category": get_aqi_category(int(avg_aqi)),
        "station_count": len(readings),
    }


# ── Health Risk ────────────────────────────────────────────────────────────────
@app.get("/api/health/{city}/{persona}")
def get_health_risk(city: str, persona: str, exposure_hours: int = 8):
    """Get health risk scores for a city and persona."""
    from schemas.agent_messages import AgentMessage, AgentName
    import uuid
    agents = get_agents()

    data_msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        source_agent=AgentName.REASONING,
        target_agent=AgentName.DATA,
        payload={"city": city, "uploaded_df": None},
    )
    data_out = agents["data"].run(data_msg)

    health_msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        source_agent=AgentName.REASONING,
        target_agent=AgentName.HEALTH,
        payload={"data_output": data_out.payload, "persona": persona, "exposure_hours": exposure_hours},
    )
    health_out = agents["health"].run(health_msg)
    h = health_out.payload or {}
    risks = h.get("persona_risks", {})
    persona_key = persona.lower().replace(" ", "_")
    risk = risks.get(persona_key, next(iter(risks.values()), {})) if risks else {}

    return {
        "city": city,
        "persona": persona,
        "risk_score": risk.get("risk_score", 0),
        "risk_level": risk.get("risk_level", "Unknown"),
        "symptoms": risk.get("symptoms", []),
        "outdoor_recommendation": risk.get("outdoor_recommendation", ""),
        "preventive_actions": risk.get("preventive_actions", []),
        "alert_triggered": h.get("alert_triggered", False),
        "alert_message": h.get("alert_message", ""),
    }


# ── CSV Upload ─────────────────────────────────────────────────────────────────
@app.post("/api/upload-csv")
async def upload_csv(file: UploadFile = File(...), city: str = "Custom"):
    """Upload a CSV file and run the data agent on it."""
    content = await file.read()
    try:
        df = pd.read_csv(io.StringIO(content.decode("utf-8")))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV parse error: {e}")

    from schemas.agent_messages import AgentMessage, AgentName
    import uuid
    agents = get_agents()
    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        source_agent=AgentName.REASONING,
        target_agent=AgentName.DATA,
        payload={"city": city, "uploaded_df": df},
    )
    out = agents["data"].run(msg)
    payload = out.payload or {}
    return {
        "rows_loaded": len(df),
        "columns": list(df.columns),
        "readings": len(payload.get("readings", [])),
        "city": city,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
