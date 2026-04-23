"""
data/database.py
─────────────────
SQLAlchemy-based SQLite database manager.
Schema: stations, aqi_readings, health_reports, agent_logs.
"""

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column, DateTime, Float, Integer, JSON, String, Text,
    create_engine, event, text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import DB_PATH
from utils.logger import get_logger

logger = get_logger("database")

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)

# Enable WAL mode for concurrent reads
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


# ─── ORM Models ───────────────────────────────────────────────────────────────

class StationModel(Base):
    __tablename__ = "stations"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    station_name = Column(String(100), nullable=False)
    city         = Column(String(100), nullable=False, index=True)
    lat          = Column(Float, nullable=False)
    lon          = Column(Float, nullable=False)
    source       = Column(String(50))
    created_at   = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Station {self.station_name} ({self.city})>"


class AQIReadingModel(Base):
    __tablename__ = "aqi_readings"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    station_name = Column(String(100), nullable=False, index=True)
    city         = Column(String(100), nullable=False, index=True)
    timestamp    = Column(DateTime, nullable=False, index=True)
    pm25         = Column(Float)
    pm10         = Column(Float)
    no2          = Column(Float)
    co           = Column(Float)
    so2          = Column(Float)
    o3           = Column(Float)
    nh3          = Column(Float)
    aqi          = Column(Float, index=True)
    aqi_category = Column(String(50))
    source       = Column(String(50))
    data_quality = Column(Float, default=1.0)
    raw_payload  = Column(JSON)   # stores original API response


class HealthReportModel(Base):
    __tablename__ = "health_reports"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    city         = Column(String(100), nullable=False)
    station_name = Column(String(100))
    persona      = Column(String(50), nullable=False)
    aqi          = Column(Float)
    risk_level   = Column(String(30))
    risk_score   = Column(Float)
    report_json  = Column(JSON)
    created_at   = Column(DateTime, default=datetime.utcnow, index=True)


class AgentLogModel(Base):
    __tablename__ = "agent_logs"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    message_id   = Column(String(36), unique=True)
    source_agent = Column(String(50))
    target_agent = Column(String(50))
    status       = Column(String(20))
    payload_json = Column(JSON)
    duration_ms  = Column(Float)
    created_at   = Column(DateTime, default=datetime.utcnow)


# Create all tables
Base.metadata.create_all(engine)


# ─── Database Manager ──────────────────────────────────────────────────────────

class DatabaseManager:
    """CRUD interface for all AQI system tables."""

    def get_session(self) -> Session:
        return SessionLocal()

    # ── Stations ──────────────────────────────────────────────────────────────

    def upsert_station(self, station_name: str, city: str, lat: float, lon: float, source: str = "unknown"):
        with self.get_session() as session:
            existing = session.query(StationModel).filter_by(station_name=station_name, city=city).first()
            if not existing:
                session.add(StationModel(station_name=station_name, city=city, lat=lat, lon=lon, source=source))
                session.commit()

    def get_stations(self, city: Optional[str] = None) -> List[Dict]:
        with self.get_session() as session:
            q = session.query(StationModel)
            if city:
                q = q.filter(StationModel.city == city)
            return [{"station_name": s.station_name, "city": s.city, "lat": s.lat, "lon": s.lon} for s in q.all()]

    # ── AQI Readings ──────────────────────────────────────────────────────────

    def save_readings(self, readings: List[Dict]):
        """Bulk insert AQI readings, skip existing (same station + timestamp)."""
        with self.get_session() as session:
            for r in readings:
                existing = session.query(AQIReadingModel).filter_by(
                    station_name=r.get("station_name"),
                    timestamp=r.get("timestamp"),
                ).first()
                if not existing:
                    session.add(AQIReadingModel(**r))
            session.commit()
        logger.debug(f"Saved {len(readings)} readings to DB")

    def get_latest_readings(self, city: str, limit: int = 50) -> List[Dict]:
        with self.get_session() as session:
            rows = (
                session.query(AQIReadingModel)
                .filter(AQIReadingModel.city == city)
                .order_by(AQIReadingModel.timestamp.desc())
                .limit(limit)
                .all()
            )
            return [self._reading_to_dict(r) for r in rows]

    def get_historical_readings(
        self,
        city: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        station: Optional[str] = None,
        # alternate kwarg names used by app.py
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        limit: int = 5000,
    ) -> List[Dict]:
        # Accept either naming convention
        t_start = start or start_dt
        t_end   = end   or end_dt
        with self.get_session() as session:
            q = session.query(AQIReadingModel).filter(
                AQIReadingModel.city == city,
            )
            if t_start:
                q = q.filter(AQIReadingModel.timestamp >= t_start)
            if t_end:
                q = q.filter(AQIReadingModel.timestamp <= t_end)
            if station:
                q = q.filter(AQIReadingModel.station_name == station)
            q = q.order_by(AQIReadingModel.timestamp).limit(limit)
            return [self._reading_to_dict(r) for r in q.all()]

    def get_city_aqi_stats(self, city: str) -> Dict:
        with self.get_session() as session:
            result = session.execute(text(
                """SELECT
                    AVG(aqi) as avg_aqi,
                    MAX(aqi) as max_aqi,
                    MIN(aqi) as min_aqi,
                    COUNT(*) as total_readings,
                    MAX(timestamp) as last_updated
                FROM aqi_readings
                WHERE city = :city
                """
            ), {"city": city}).fetchone()
            if result:
                return {
                    "avg_aqi": round(result[0] or 0, 1),
                    "max_aqi": result[1],
                    "min_aqi": result[2],
                    "total_readings": result[3],
                    "last_updated": str(result[4]),
                }
            return {}

    def _reading_to_dict(self, r: AQIReadingModel) -> Dict:
        return {
            "station_name": r.station_name,
            "city": r.city,
            "timestamp": r.timestamp,
            "pm25": r.pm25,
            "pm10": r.pm10,
            "no2": r.no2,
            "co": r.co,
            "so2": r.so2,
            "o3": r.o3,
            "nh3": r.nh3,
            "aqi": r.aqi,
            "aqi_category": r.aqi_category,
            "source": r.source,
            "data_quality": r.data_quality,
        }

    # ── Health Reports ────────────────────────────────────────────────────────

    def save_health_report(self, city: str, persona: str, aqi: float,
                            risk_level: str, risk_score: float,
                            report: Dict, station: Optional[str] = None):
        with self.get_session() as session:
            session.add(HealthReportModel(
                city=city, station_name=station, persona=persona,
                aqi=aqi, risk_level=risk_level, risk_score=risk_score,
                report_json=report,
            ))
            session.commit()

    # ── Agent Logs ────────────────────────────────────────────────────────────

    def log_agent_message(self, message_id: str, source: str, target: str,
                           status: str, payload: Dict, duration_ms: float = 0.0):
        with self.get_session() as session:
            session.add(AgentLogModel(
                message_id=message_id, source_agent=source, target_agent=target,
                status=status, payload_json=payload, duration_ms=duration_ms,
            ))
            session.commit()


# Singleton
db = DatabaseManager()
