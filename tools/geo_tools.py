"""
tools/geo_tools.py
──────────────────
Geospatial utility functions: geocoding, coordinate validation,
distance calculations, bounding boxes, and spatial joins.
"""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple
import requests
from config import INDIAN_CITIES


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two lat/lon points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def geocode_city(city: str) -> Optional[Tuple[float, float]]:
    """
    Return (lat, lon) for a city name.
    First checks local INDIAN_CITIES dict; falls back to Nominatim.
    """
    # Local lookup first
    for name, data in INDIAN_CITIES.items():
        if city.lower() in name.lower() or name.lower() in city.lower():
            return data["lat"], data["lon"]

    # Nominatim fallback (no API key required)
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{city}, India", "format": "json", "limit": 1},
            headers={"User-Agent": "AQI-MultiAgent/1.0"},
            timeout=8,
        )
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception:
        pass

    return None


def get_bounding_box(lat: float, lon: float, radius_km: float) -> Dict[str, float]:
    """Return a bounding box [min_lat, min_lon, max_lat, max_lon] for a radius."""
    delta_lat = radius_km / 111.0
    delta_lon = radius_km / (111.0 * math.cos(math.radians(lat)))
    return {
        "min_lat": lat - delta_lat,
        "max_lat": lat + delta_lat,
        "min_lon": lon - delta_lon,
        "max_lon": lon + delta_lon,
    }


def validate_coordinates(lat: float, lon: float) -> bool:
    """Validate lat/lon are within India's approximate bounds."""
    return 6.0 <= lat <= 37.5 and 68.0 <= lon <= 97.5


def assign_mock_coordinates(station_name: str, city: str) -> Tuple[float, float]:
    """
    Generate deterministic mock coordinates for a station within a city.
    Used when real coordinates aren't available.
    """
    city_data = INDIAN_CITIES.get(city, {"lat": 19.0760, "lon": 72.8777})
    base_lat, base_lon = city_data["lat"], city_data["lon"]

    # Deterministic offset based on station name hash
    h = hash(station_name) % 10000
    lat_offset = (h % 100 - 50) * 0.005     # ±0.25 degrees
    lon_offset = (h // 100 % 100 - 50) * 0.005
    return round(base_lat + lat_offset, 6), round(base_lon + lon_offset, 6)


def stations_within_radius(
    stations: List[Dict],
    center_lat: float,
    center_lon: float,
    radius_km: float,
) -> List[Dict]:
    """Filter a list of station dicts to those within radius_km of center."""
    result = []
    for s in stations:
        d = haversine(center_lat, center_lon, s["lat"], s["lon"])
        if d <= radius_km:
            result.append({**s, "distance_km": round(d, 2)})
    return sorted(result, key=lambda x: x["distance_km"])
