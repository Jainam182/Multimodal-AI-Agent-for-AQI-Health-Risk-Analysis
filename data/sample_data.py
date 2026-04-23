"""
data/sample_data.py
────────────────────
Generates realistic mock AQI data for Mumbai and other cities.
Used when APIs are unavailable or for offline development.
Includes seasonal patterns, diurnal cycles, and station-specific variation.
"""

from __future__ import annotations
import random
import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from config import INDIAN_CITIES, WAQI_MUMBAI_STATIONS
from schemas.agent_messages import AQICategory, DataSource, LocationReading, PollutantReading
from tools.health_tools import aqi_to_category
from tools.geo_tools import assign_mock_coordinates


# ─── Mumbai Station Profiles ──────────────────────────────────────────────────
# Reflects known pollution patterns: industrial > traffic > residential

MUMBAI_STATION_PROFILES = {
    "Bandra":       {"base_aqi": 130, "pm25_base": 55,  "no2_base": 45, "type": "traffic"},
    "Kurla":        {"base_aqi": 155, "pm25_base": 68,  "no2_base": 52, "type": "traffic+industrial"},
    "Andheri":      {"base_aqi": 145, "pm25_base": 62,  "no2_base": 48, "type": "traffic"},
    "Colaba":       {"base_aqi": 100, "pm25_base": 38,  "no2_base": 30, "type": "coastal"},
    "Worli":        {"base_aqi": 120, "pm25_base": 48,  "no2_base": 38, "type": "mixed"},
    "Mazgaon":      {"base_aqi": 175, "pm25_base": 80,  "no2_base": 60, "type": "industrial"},
    "Borivali":     {"base_aqi": 110, "pm25_base": 42,  "no2_base": 35, "type": "suburban"},
    "Malad":        {"base_aqi": 125, "pm25_base": 50,  "no2_base": 40, "type": "residential"},
    "Thane":        {"base_aqi": 160, "pm25_base": 72,  "no2_base": 55, "type": "industrial"},
    "Navi Mumbai":  {"base_aqi": 140, "pm25_base": 58,  "no2_base": 44, "type": "mixed"},
}


def diurnal_factor(hour: int) -> float:
    """
    Return a multiplier based on hour of day.
    Peaks at rush hours (8AM, 6PM), lowest at 4AM.
    """
    # Rush hour peaks: 7-9 AM and 5-7 PM
    base = 0.7
    morning_peak = 0.4 * math.exp(-0.5 * ((hour - 8) / 1.5) ** 2)
    evening_peak = 0.45 * math.exp(-0.5 * ((hour - 18) / 1.5) ** 2)
    return base + morning_peak + evening_peak


def seasonal_factor(month: int) -> float:
    """
    Winter months (Nov-Feb) have worse AQI in Mumbai due to thermal inversions.
    Monsoon (Jun-Sep) has better AQI due to washout.
    """
    winter_boost = {11: 1.3, 12: 1.4, 1: 1.4, 2: 1.2}
    monsoon_clean = {6: 0.7, 7: 0.6, 8: 0.6, 9: 0.7}
    return winter_boost.get(month, monsoon_clean.get(month, 1.0))


def generate_pollutants(station: str, hour: int, month: int) -> Dict[str, float]:
    """Generate realistic correlated pollutant values for a station."""
    profile = MUMBAI_STATION_PROFILES.get(station, {"base_aqi": 120, "pm25_base": 50, "no2_base": 40, "type": "mixed"})

    d = diurnal_factor(hour)
    s = seasonal_factor(month)
    noise = lambda scale: random.gauss(0, scale)

    pm25_base = profile["pm25_base"]
    pm25 = max(5, pm25_base * d * s + noise(8))

    pm10 = max(10, pm25 * random.uniform(1.5, 2.2) + noise(10))
    no2  = max(5, profile["no2_base"] * d * s + noise(6))
    co   = max(0.1, 0.5 + (pm25 / 100) * 1.5 + noise(0.2))   # mg/m³
    so2  = max(2, 15 * s + noise(5)) if profile["type"] in ("industrial", "traffic+industrial") else max(1, 8 * s + noise(3))
    o3   = max(5, 40 - (pm25 / 5) + noise(8))   # O3 inversely related to NO2 in urban areas

    return {
        "pm25": round(pm25, 1),
        "pm10": round(pm10, 1),
        "no2":  round(no2, 1),
        "co":   round(co, 3),
        "so2":  round(so2, 1),
        "o3":   round(o3, 1),
    }


def generate_mock_current_data(city: str = "Mumbai") -> List[LocationReading]:
    """Generate current-moment mock readings for all stations in a city."""
    now = datetime.now(timezone.utc)
    stations = list(MUMBAI_STATION_PROFILES.keys()) if city == "Mumbai" else INDIAN_CITIES.get(city, {}).get("stations", [city])

    readings = []
    for station in stations:
        polls_dict = generate_pollutants(station, now.hour, now.month)

        from tools.aqi_tools import compute_aqi_from_pollutants
        aqi_val, _ = compute_aqi_from_pollutants(polls_dict)
        cat = aqi_to_category(aqi_val)

        lat, lon = assign_mock_coordinates(station, city)

        readings.append(LocationReading(
            station_name=station,
            city=city,
            lat=lat,
            lon=lon,
            timestamp=now,
            pollutants=PollutantReading(
                **polls_dict,
                aqi=aqi_val,
                aqi_category=cat,
            ),
            data_quality=0.85,
            source=DataSource.MOCK,
        ))

    return readings


def generate_mock_historical_data(
    city: str = "Mumbai",
    station: str = "Bandra",
    days: int = 30,
) -> List[Dict]:
    """
    Generate hourly historical AQI data for a station over N days.
    Returns list of dicts suitable for DataFrame construction.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    records = []
    current = start
    while current <= end:
        polls = generate_pollutants(station, current.hour, current.month)
        from tools.aqi_tools import compute_aqi_from_pollutants
        aqi_val, _ = compute_aqi_from_pollutants(polls)

        records.append({
            "timestamp": current,
            "station_name": station,
            "city": city,
            "aqi": round(aqi_val, 1),
            "aqi_category": aqi_to_category(aqi_val).value,
            **polls,
            "source": "mock_data",
            "data_quality": 0.85,
        })
        current += timedelta(hours=1)

    return records


def generate_multi_station_snapshot(city: str = "Mumbai") -> List[Dict]:
    """Current-moment snapshot across all stations, as list of dicts."""
    readings = generate_mock_current_data(city)
    return [
        {
            "station_name": r.station_name,
            "city": r.city,
            "lat": r.lat,
            "lon": r.lon,
            "aqi": r.pollutants.aqi,
            "pm25": r.pollutants.pm25,
            "pm10": r.pollutants.pm10,
            "no2": r.pollutants.no2,
            "co": r.pollutants.co,
            "so2": r.pollutants.so2,
            "o3": r.pollutants.o3,
            "aqi_category": r.pollutants.aqi_category.value,
            "timestamp": r.timestamp,
            "source": r.source.value,
        }
        for r in readings
    ]
