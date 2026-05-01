"""
schemas/agent_messages.py
──────────────────────────
All agents communicate via AgentMessage with payload: Dict[str, Any].
No nested Pydantic Payload sub-classes — plain dicts throughout.
"""

# ─── Imports ──────────────────────────────────────────────────────────────────
from __future__ import annotations
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─── Enums ────────────────────────────────────────────────────────────────────

class AgentName(str, Enum):
    USER          = "user"
    REASONING     = "reasoning_agent"
    DATA          = "data_agent"
    GIS           = "gis_agent"
    HEALTH        = "health_agent"
    VISUALIZATION = "visualization_agent"
    EXPLANATION   = "explanation_agent"

class AQICategory(str, Enum):
    GOOD         = "Good"
    SATISFACTORY = "Satisfactory"
    MODERATE     = "Moderately Polluted"
    POOR         = "Poor"
    VERY_POOR    = "Very Poor"
    SEVERE       = "Severe / Hazardous"
    UNKNOWN      = "Unknown"

class RiskLevel(str, Enum):
    MINIMAL   = "Minimal"
    LOW       = "Low"
    MODERATE  = "Moderate"
    HIGH      = "High"
    VERY_HIGH = "Very High"
    CRITICAL  = "Critical"

class DataSource(str, Enum):
    WAQI        = "waqi_api"
    OPENWEATHER = "openweather_api"
    CPCB        = "cpcb_india"
    SCRAPING    = "web_scraping"
    CSV_UPLOAD  = "csv_upload"
    MOCK        = "mock_data"

class MessageStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR   = "error"
    PENDING = "pending"


# ─── Base envelope ────────────────────────────────────────────────────────────

class AgentMessage(BaseModel):
    """Universal inter-agent envelope. payload is always a plain dict."""
    message_id:   str            = Field(default_factory=lambda: str(uuid.uuid4()))
    source_agent: AgentName      = AgentName.USER
    target_agent: Optional[AgentName] = None
    timestamp:    datetime       = Field(default_factory=datetime.utcnow)
    status:       MessageStatus  = MessageStatus.PENDING
    errors:       List[str]      = Field(default_factory=list)
    metadata:     Dict[str, Any] = Field(default_factory=dict)
    payload:      Dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


# ─── Typed output aliases (just set source_agent default) ─────────────────────

class DataAgentOutput(AgentMessage):
    source_agent: AgentName = AgentName.DATA

class GISAgentOutput(AgentMessage):
    source_agent: AgentName = AgentName.GIS

class HealthAgentOutput(AgentMessage):
    source_agent: AgentName = AgentName.HEALTH

class VisualizationAgentOutput(AgentMessage):
    source_agent: AgentName = AgentName.VISUALIZATION

class ExplanationAgentOutput(AgentMessage):
    source_agent: AgentName = AgentName.EXPLANATION


# ─── Internal data structures (used within agents) ────────────────────────────

class PollutantReading(BaseModel):
    model_config = {"validate_assignment": True}
    pm25: Optional[float] = None
    pm10: Optional[float] = None
    no2:  Optional[float] = None
    co:   Optional[float] = None
    so2:  Optional[float] = None
    o3:   Optional[float] = None
    nh3:  Optional[float] = None
    aqi:  Optional[float] = None
    aqi_category: AQICategory = AQICategory.UNKNOWN


class LocationReading(BaseModel):
    station_name: str
    city:         str
    lat:          float = 0.0
    lon:          float = 0.0
    timestamp:    Optional[datetime] = None
    pollutants:   PollutantReading   = Field(default_factory=PollutantReading)
    data_quality: float              = 1.0
    source:       DataSource         = DataSource.MOCK

    def to_dict(self) -> Dict[str, Any]:
        """Flat dict for payload["readings"] lists."""
        p = self.pollutants
        return {
            "station_name": self.station_name,
            "city":         self.city,
            "lat":          self.lat,
            "lon":          self.lon,
            "timestamp":    self.timestamp.isoformat() if self.timestamp else None,
            "aqi":          p.aqi or 0.0,
            "pm25":         p.pm25,
            "pm10":         p.pm10,
            "no2":          p.no2,
            "so2":          p.so2,
            "co":           p.co,
            "o3":           p.o3,
            "nh3":          p.nh3,
            "aqi_category": p.aqi_category.value if hasattr(p.aqi_category, "value") else str(p.aqi_category),
            "data_quality": self.data_quality,
            "source":       self.source.value,
        }


class ClusterInfo(BaseModel):
    label:         int
    centroid_lat:  float
    centroid_lon:  float
    station_count: int
    avg_aqi:       float
    aqi_category:  str
    risk_level:    str
    stations:      List[str]    = Field(default_factory=list)
    worst_pollutant: str        = ""

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


# ─── Planning schemas ──────────────────────────────────────────────────────────

class AnalysisStep(BaseModel):
    step_id:    int
    agent:      AgentName
    action:     str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[int]      = Field(default_factory=list)


class ReasoningPlan(BaseModel):
    query:           str
    intent:          str = "general_info"
    city:            str = "Mumbai"
    persona:         Optional[str] = None
    steps:           List[AnalysisStep] = Field(default_factory=list)
    requires_map:    bool = True
    requires_health: bool = True
    requires_trend:  bool = False


class SystemResponse(BaseModel):
    plan:           Optional[ReasoningPlan]           = None
    data_output:    Optional[DataAgentOutput]         = None
    gis_output:     Optional[GISAgentOutput]          = None
    health_output:  Optional[HealthAgentOutput]       = None
    viz_output:     Optional[VisualizationAgentOutput] = None
    explanation:    Dict[str, Any]                    = Field(default_factory=dict)
    visualizations: Dict[str, Any]                    = Field(default_factory=dict)
    summary:        str = ""
    alert_text:     str = ""
    total_duration_ms: float = 0.0

    model_config = {"arbitrary_types_allowed": True}


# ─── Stubs for backward-compat imports ────────────────────────────────────────
PersonaHealthRisk   = None   # replaced by plain dicts
PollutantHealthNote = None
