"""
agents/gis_agent.py
────────────────────
GIS Agent: Spatial intelligence for AQI data.

Capabilities:
  - Spatial joins and coordinate mapping
  - DBSCAN clustering to identify hotspots and safe zones
  - Region-wise AQI comparison
  - Choropleth data generation
  - Spatial aggregation and statistics
  - Pollution corridor detection
  - Distance-based risk radius computation
"""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent
from config import get_aqi_category
from schemas.agent_messages import (
    AgentName,
    AQICategory,
    ClusterInfo,
    DataAgentOutput,
    GISAgentOutput,
    MessageStatus,
    RiskLevel,
)
from tools.geo_tools import haversine
from tools.health_tools import aqi_to_category, aqi_to_risk_level
from utils.logger import get_logger

logger = get_logger("GISAgent")


class GISAgent(BaseAgent):
    """Performs all spatial analysis on AQI station data."""

    agent_name = AgentName.GIS

    def _execute(
        self,
        message_id: str,
        data_output=None,          # dict payload from DataAgent OR DataAgentOutput
        station_dicts: Optional[List[Dict]] = None,
        city: str = "Mumbai",
        eps_km: float = 3.0,
        min_samples: int = 2,
        radius_km: Optional[float] = None,
        center_lat: Optional[float] = None,
        center_lon: Optional[float] = None,
        area_name: Optional[str] = None,
        **kwargs,
    ) -> GISAgentOutput:

        # ── Resolve input — accept dict or AgentMessage payload ───────────────
        readings = []
        if data_output is not None:
            if isinstance(data_output, dict):
                readings = data_output.get("readings", [])
                city = data_output.get("city", city)
            elif hasattr(data_output, "payload"):
                # Legacy AgentMessage object
                p = data_output.payload
                if isinstance(p, dict):
                    readings = p.get("readings", [])
                    city = p.get("city", city)

        stations_list = readings or station_dicts or []

        # ── Radius-based filtering ───────────────────────────────────────────
        center_lat_used = center_lat
        center_lon_used = center_lon

        if radius_km is not None and area_name and (center_lat is None or center_lon is None):
            # Try to geocode the area name; fall back to city coordinates from data
            from tools.geo_tools import geocode_city
            coords = geocode_city(area_name)
            if coords:
                center_lat_used, center_lon_used = coords
                logger.info(f"GISAgent: geocoded '{area_name}' -> ({center_lat_used}, {center_lon_used})")
            elif stations_list and (stations_list[0].get("lat") and stations_list[0].get("lon")):
                # Fall back to centroid of stations as center
                center_lat_used = sum(s.get("lat", 0) for s in stations_list) / len(stations_list)
                center_lon_used = sum(s.get("lon", 0) for s in stations_list) / len(stations_list)
                logger.info(f"GISAgent: using station centroid as center ({center_lat_used:.3f}, {center_lon_used:.3f})")

        if radius_km is not None and center_lat_used is not None and center_lon_used is not None:
            from tools.geo_tools import stations_within_radius
            filtered = stations_within_radius(
                stations_list, center_lat_used, center_lon_used, radius_km
            )
            logger.info(f"GISAgent: radius filter {radius_km}km from ({center_lat_used:.3f}, {center_lon_used:.3f}) -> {len(filtered)}/{len(stations_list)} stations")
            stations_list = filtered

        if not stations_list:
            logger.warning("GISAgent: No station data. Returning empty payload.")
            return GISAgentOutput(
                message_id=message_id,
                status=MessageStatus.PARTIAL,
                errors=["No station data available"],
                payload={"city": city, "clusters": [], "hotspot_stations": [],
                         "safe_stations": [], "spatial_summary": "", "heatmap_data": [],
                         "avg_aqi": 0},
            )

        logger.info(f"GISAgent: {len(stations_list)} stations, city={city}")

        df = pd.DataFrame(stations_list)
        for col in ["lat", "lon", "aqi"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        avg_aqi = float(df["aqi"].mean()) if not df.empty else 0.0
        max_row = df.loc[df["aqi"].idxmax()] if not df.empty else None
        min_row = df.loc[df["aqi"].idxmin()] if not df.empty else None

        hotspots, safe_zones = self._cluster_stations(df, eps_km, min_samples)
        heatmap_data = self._generate_heatmap_data(df)
        choropleth = self._generate_choropleth_data(df, city)
        spatial_summary = self._build_spatial_summary(df, city, hotspots, safe_zones, avg_aqi)

        # Hotspot stations = readings with AQI > 200
        hotspot_stations = [
            r for r in stations_list if (r.get("aqi") or 0) > 200
        ]

        # Convert ClusterInfo objects to dicts for JSON-safe payload
        def _cluster_list(clusters):
            out = []
            for c in clusters:
                if hasattr(c, "model_dump"):
                    d = c.model_dump()
                    # fix label/cluster_id naming
                    if "cluster_id" in d and "label" not in d:
                        d["label"] = d.pop("cluster_id")
                else:
                    d = dict(c) if hasattr(c, "keys") else vars(c)
                # derive worst_pollutant from stations in df
                stn_df = df[df["station_name"].isin(d.get("stations", []))]
                wp = "pm25"
                if not stn_df.empty:
                    poll_cols = ["pm25", "pm10", "no2", "so2", "o3"]
                    avgs = {p: stn_df[p].mean() for p in poll_cols if p in stn_df.columns}
                    if avgs:
                        wp = max(avgs, key=lambda k: avgs[k] or 0)
                d["worst_pollutant"] = wp
                out.append(d)
            return out

        return GISAgentOutput(
            message_id=message_id,
            status=MessageStatus.SUCCESS,
            payload={
                "city":            city,
                "clusters":        _cluster_list(hotspots + safe_zones),
                "hotspot_stations": hotspot_stations,
                "safe_stations":   [r for r in stations_list if (r.get("aqi") or 0) <= 150],
                "stations":        stations_list,  # filtered/radius-subset if applicable
                "avg_aqi":         round(avg_aqi, 1),
                "max_aqi_station": str(max_row["station_name"]) if max_row is not None else None,
                "min_aqi_station": str(min_row["station_name"]) if min_row is not None else None,
                "spatial_summary": spatial_summary,
                "heatmap_data":    heatmap_data,
                "choropleth_data": choropleth,
            },
        )

    # ─── DBSCAN Clustering ────────────────────────────────────────────────────

    def _cluster_stations(
        self,
        df: pd.DataFrame,
        eps_km: float,
        min_samples: int,
    ) -> Tuple[List[ClusterInfo], List[ClusterInfo]]:
        """
        Apply DBSCAN to find spatial clusters.
        Converts km radius to radians for haversine metric in sklearn.
        """
        if len(df) < min_samples:
            # Not enough stations; treat each as its own point
            hotspots, safe_zones = [], []
            for _, row in df.iterrows():
                aqi = row.get("aqi", 0)
                category = aqi_to_category(aqi)
                _, risk = aqi_to_risk_level(aqi)
                risk_level = self._risk_from_score(risk)
                info = ClusterInfo(
                    label=0,
                    centroid_lat=float(row["lat"]),
                    centroid_lon=float(row["lon"]),
                    station_count=1,
                    avg_aqi=round(aqi, 1),
                    aqi_category=category.value if hasattr(category, "value") else str(category),
                    risk_level=risk_level.value if hasattr(risk_level, "value") else str(risk_level),
                    stations=[str(row["station_name"])],
                )
                (hotspots if aqi > 150 else safe_zones).append(info)
            return hotspots, safe_zones

        try:
            from sklearn.cluster import DBSCAN

            coords_rad = np.radians(df[["lat", "lon"]].values)
            eps_rad = eps_km / 6371.0  # Earth radius in km

            db = DBSCAN(eps=eps_rad, min_samples=min_samples, metric="haversine")
            labels = db.fit_predict(coords_rad)
            df = df.copy()
            df["cluster"] = labels

            hotspots = []
            safe_zones = []

            for cluster_id in sorted(set(labels)):
                if cluster_id == -1:
                    continue  # Noise points

                cluster_df = df[df["cluster"] == cluster_id]
                avg_aqi = float(cluster_df["aqi"].mean())
                centroid_lat = float(cluster_df["lat"].mean())
                centroid_lon = float(cluster_df["lon"].mean())
                stations = list(cluster_df["station_name"].astype(str))

                category = aqi_to_category(avg_aqi)
                _, base_score = aqi_to_risk_level(avg_aqi)
                risk_level = self._risk_from_score(base_score)

                cluster_info = ClusterInfo(
                    label=int(cluster_id),
                    centroid_lat=centroid_lat,
                    centroid_lon=centroid_lon,
                    station_count=len(cluster_df),
                    avg_aqi=round(avg_aqi, 1),
                    aqi_category=category.value if hasattr(category, "value") else str(category),
                    risk_level=risk_level.value if hasattr(risk_level, "value") else str(risk_level),
                    stations=stations,
                )

                if avg_aqi > 150:
                    hotspots.append(cluster_info)
                else:
                    safe_zones.append(cluster_info)

            return (
                sorted(hotspots, key=lambda x: x.avg_aqi, reverse=True),
                sorted(safe_zones, key=lambda x: x.avg_aqi),
            )

        except ImportError:
            logger.warning("sklearn not available for DBSCAN. Using simple threshold clustering.")
            return self._simple_cluster(df)

    def _simple_cluster(self, df: pd.DataFrame) -> Tuple[List[ClusterInfo], List[ClusterInfo]]:
        """Fallback: split stations into hot/safe by AQI threshold."""
        hotspots, safe_zones = [], []
        for i, row in df.iterrows():
            aqi = row.get("aqi", 0)
            category = aqi_to_category(aqi)
            _, score = aqi_to_risk_level(aqi)
            info = ClusterInfo(
                label=int(i),
                centroid_lat=float(row["lat"]),
                centroid_lon=float(row["lon"]),
                station_count=1,
                avg_aqi=round(aqi, 1),
                aqi_category=category.value if hasattr(category, "value") else str(category),
                risk_level=self._risk_from_score(score).value,
                stations=[str(row["station_name"])],
            )
            (hotspots if aqi > 150 else safe_zones).append(info)
        return hotspots, safe_zones

    def _risk_from_score(self, score: float) -> RiskLevel:
        if score < 2:    return RiskLevel.MINIMAL
        if score < 4:    return RiskLevel.LOW
        if score < 6:    return RiskLevel.MODERATE
        if score < 7.5:  return RiskLevel.HIGH
        if score < 9:    return RiskLevel.VERY_HIGH
        return RiskLevel.CRITICAL

    # ─── Heatmap Data ─────────────────────────────────────────────────────────

    def _generate_heatmap_data(self, df: pd.DataFrame) -> List[Dict]:
        """
        Generate heatmap data as [[lat, lon, weight], ...].
        Weight is normalised AQI (0–1).
        """
        if df.empty:
            return []
        max_aqi = df["aqi"].max() if df["aqi"].max() > 0 else 1
        return [
            {
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "weight": round(float(row["aqi"]) / max_aqi, 3),
                "aqi": float(row["aqi"]),
                "station": str(row["station_name"]),
            }
            for _, row in df.iterrows()
        ]

    # ─── Choropleth Data ──────────────────────────────────────────────────────

    def _generate_choropleth_data(self, df: pd.DataFrame, city: str) -> Dict:
        """
        Generate AQI-by-zone data for choropleth mapping.
        Returns a simple dict {station → aqi} for Folium/Pydeck.
        """
        return {
            "station_aqi": {
                str(row["station_name"]): float(row["aqi"])
                for _, row in df.iterrows()
            },
            "city": city,
        }

    # ─── Region Comparison ────────────────────────────────────────────────────

    def compare_regions(self, stations_a: List[Dict], stations_b: List[Dict], label_a: str, label_b: str) -> Dict:
        """Compare AQI statistics between two sets of stations (regions)."""
        def stats(stations: List[Dict]) -> Dict:
            aqis = [s.get("aqi", 0) for s in stations if s.get("aqi")]
            return {
                "count": len(aqis),
                "mean": round(np.mean(aqis), 1) if aqis else 0,
                "max": max(aqis) if aqis else 0,
                "min": min(aqis) if aqis else 0,
                "p75": round(float(np.percentile(aqis, 75)), 1) if aqis else 0,
            }
        return {
            label_a: stats(stations_a),
            label_b: stats(stations_b),
            "comparison": f"{label_a} avg AQI {stats(stations_a)['mean']} vs {label_b} avg AQI {stats(stations_b)['mean']}",
        }

    # ─── Risk Radius ─────────────────────────────────────────────────────────

    def get_risk_radius_km(self, aqi: float, persona: str = "general_population") -> float:
        """
        Compute the approximate radius (km) around a hotspot that would affect
        a given persona, based on AQI severity.
        This is a heuristic for visualisation purposes.
        """
        from tools.health_tools import PERSONA_RULES
        multiplier = PERSONA_RULES.get(persona, {}).get("risk_multiplier", 1.0)
        if aqi <= 100:   base_radius = 0.5
        elif aqi <= 200: base_radius = 1.5
        elif aqi <= 300: base_radius = 3.0
        else:            base_radius = 5.0
        return round(base_radius * multiplier, 1)

    # ─── Spatial Summary Text ─────────────────────────────────────────────────

    def _build_spatial_summary(
        self,
        df: pd.DataFrame,
        city: str,
        hotspots: List[ClusterInfo],
        safe_zones: List[ClusterInfo],
        avg_aqi: float,
    ) -> str:
        n_stations = len(df)
        n_hotspots = len(hotspots)
        n_safe = len(safe_zones)

        cat = aqi_to_category(avg_aqi).value
        worst = hotspots[0].stations[0] if hotspots else "N/A"
        best = safe_zones[0].stations[0] if safe_zones else "N/A"

        summary = (
            f"{city} spatial analysis across {n_stations} monitoring stations: "
            f"City-wide average AQI = {avg_aqi:.1f} ({cat}). "
            f"{n_hotspots} pollution hotspot cluster(s) detected, "
            f"{n_safe} relatively clean zone(s) identified. "
            f"Worst area: {worst}. Best area: {best}."
        )
        return summary
