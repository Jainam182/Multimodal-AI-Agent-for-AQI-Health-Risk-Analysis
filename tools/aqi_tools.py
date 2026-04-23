"""
tools/aqi_tools.py
──────────────────
AQI calculation, pollutant normalization, sub-index computation,
and data preprocessing utilities used by the Data Agent.
"""

from __future__ import annotations
import math
from typing import Dict, Optional, Tuple
import pandas as pd
import numpy as np


# ─── India CPCB Sub-Index Breakpoints ─────────────────────────────────────────
# Format: (C_lo, C_hi, I_lo, I_hi) per pollutant

CPCB_BREAKPOINTS: Dict[str, list] = {
    "pm25": [
        (0, 30,   0,   50),
        (30, 60,  51,  100),
        (60, 90,  101, 200),
        (90, 120, 201, 300),
        (120, 250, 301, 400),
        (250, 500, 401, 500),
    ],
    "pm10": [
        (0, 50,    0,   50),
        (50, 100,  51,  100),
        (100, 250, 101, 200),
        (250, 350, 201, 300),
        (350, 430, 301, 400),
        (430, 600, 401, 500),
    ],
    "no2": [
        (0, 40,    0,   50),
        (40, 80,   51,  100),
        (80, 180,  101, 200),
        (180, 280, 201, 300),
        (280, 400, 301, 400),
        (400, 800, 401, 500),
    ],
    "so2": [
        (0, 40,    0,   50),
        (40, 80,   51,  100),
        (80, 380,  101, 200),
        (380, 800, 201, 300),
        (800, 1600, 301, 400),
        (1600, 2620, 401, 500),
    ],
    "co": [  # mg/m³
        (0, 1,    0,   50),
        (1, 2,    51,  100),
        (2, 10,   101, 200),
        (10, 17,  201, 300),
        (17, 34,  301, 400),
        (34, 50,  401, 500),
    ],
    "o3": [  # µg/m³
        (0, 50,    0,   50),
        (50, 100,  51,  100),
        (100, 168, 101, 200),
        (168, 208, 201, 300),
        (208, 748, 301, 400),
        (748, 1000, 401, 500),
    ],
    "nh3": [
        (0, 200,   0,   50),
        (200, 400, 51,  100),
        (400, 800, 101, 200),
        (800, 1200, 201, 300),
        (1200, 1800, 301, 400),
        (1800, 2400, 401, 500),
    ],
}


def compute_sub_index(pollutant: str, concentration: float) -> Optional[float]:
    """
    Compute CPCB sub-index for a single pollutant using linear interpolation.
    Returns None if concentration is outside defined breakpoints.
    """
    breakpoints = CPCB_BREAKPOINTS.get(pollutant.lower())
    if not breakpoints:
        return None

    for C_lo, C_hi, I_lo, I_hi in breakpoints:
        if C_lo <= concentration <= C_hi:
            sub_index = ((I_hi - I_lo) / (C_hi - C_lo)) * (concentration - C_lo) + I_lo
            return round(sub_index, 2)

    # Extrapolate beyond highest breakpoint
    if concentration > breakpoints[-1][1]:
        return 500.0
    return None


def compute_aqi_from_pollutants(pollutants: Dict[str, float]) -> Tuple[float, str]:
    """
    Compute composite AQI as the maximum sub-index across all available pollutants.
    Returns (aqi_value, dominant_pollutant_name).
    """
    sub_indices = {}
    for pollutant, value in pollutants.items():
        if value is not None and not math.isnan(value) and value >= 0:
            si = compute_sub_index(pollutant, value)
            if si is not None:
                sub_indices[pollutant] = si

    if not sub_indices:
        return 0.0, "unknown"

    dominant = max(sub_indices, key=sub_indices.get)
    return round(sub_indices[dominant], 1), dominant


# ─── Normalization & Cleaning ──────────────────────────────────────────────────

COLUMN_ALIASES = {
    # Handles varied naming from different data sources
    "pm2.5": "pm25", "pm_2.5": "pm25", "pm25_avg": "pm25",
    "pm_10": "pm10", "pm10_avg": "pm10",
    "nitrogen_dioxide": "no2", "no2_avg": "no2",
    "sulphur_dioxide": "so2", "sulfur_dioxide": "so2", "so2_avg": "so2",
    "carbon_monoxide": "co", "co_avg": "co",
    "ozone": "o3", "o3_avg": "o3",
    "ammonia": "nh3", "nh3_avg": "nh3",
    "air_quality_index": "aqi", "aqi_value": "aqi",
    "station": "station_name", "location": "station_name",
    "latitude": "lat", "longitude": "lon",
    "datetime": "timestamp", "date_time": "timestamp", "time": "timestamp",
}

POLLUTANT_COLS = ["pm25", "pm10", "no2", "so2", "co", "o3", "nh3", "aqi"]


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize a raw DataFrame from any source to the canonical schema.
    - Rename columns via aliases
    - Cast numeric columns
    - Handle missing values
    - Parse timestamps
    """
    df = df.copy()

    # Lowercase all columns
    df.columns = [c.lower().strip() for c in df.columns]

    # Apply aliases
    df.rename(columns=COLUMN_ALIASES, inplace=True)

    # Ensure required columns exist
    for col in POLLUTANT_COLS:
        if col not in df.columns:
            df[col] = np.nan

    # Cast to numeric
    for col in POLLUTANT_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clip negative values
    for col in POLLUTANT_COLS:
        df[col] = df[col].clip(lower=0)

    # Parse timestamp
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    elif "date" in df.columns and "hour" in df.columns:
        df["timestamp"] = pd.to_datetime(df["date"].astype(str) + " " + df["hour"].astype(str) + ":00", errors="coerce", utc=True)

    # Fill missing AQI by computing from pollutants
    missing_aqi_mask = df["aqi"].isna()
    if missing_aqi_mask.any():
        def _calc_aqi(row):
            polls = {c: row[c] for c in POLLUTANT_COLS[:-1] if not pd.isna(row.get(c))}
            if polls:
                aqi, _ = compute_aqi_from_pollutants(polls)
                return aqi
            return np.nan
        df.loc[missing_aqi_mask, "aqi"] = df[missing_aqi_mask].apply(_calc_aqi, axis=1)

    # Sort by timestamp
    if "timestamp" in df.columns:
        df.sort_values("timestamp", inplace=True)

    return df


def validate_data_quality(df: pd.DataFrame) -> Dict:
    """
    Compute data quality metrics for a processed DataFrame.
    Returns dict with completeness score, outlier flags, etc.
    """
    total = len(df)
    if total == 0:
        return {"score": 0.0, "issues": ["Empty dataset"]}

    issues = []
    completeness_scores = []

    for col in POLLUTANT_COLS:
        if col in df.columns:
            missing_pct = df[col].isna().mean()
            completeness_scores.append(1 - missing_pct)
            if missing_pct > 0.5:
                issues.append(f"{col}: {missing_pct:.0%} missing")

    # Check for outliers (IQR method)
    if "pm25" in df.columns and df["pm25"].notna().any():
        q1, q3 = df["pm25"].quantile(0.25), df["pm25"].quantile(0.75)
        iqr = q3 - q1
        outliers = ((df["pm25"] < q1 - 3 * iqr) | (df["pm25"] > q3 + 3 * iqr)).sum()
        if outliers > 0:
            issues.append(f"PM2.5: {outliers} outlier(s) detected")

    avg_completeness = float(np.mean(completeness_scores)) if completeness_scores else 0.0
    timestamp_ok = "timestamp" in df.columns and df["timestamp"].notna().mean() > 0.9

    return {
        "score": round(avg_completeness * (1.0 if timestamp_ok else 0.9), 3),
        "total_records": total,
        "completeness_per_pollutant": {
            col: round(1 - df[col].isna().mean(), 3)
            for col in POLLUTANT_COLS if col in df.columns
        },
        "issues": issues,
    }


def impute_missing_values(df: pd.DataFrame, method: str = "linear") -> pd.DataFrame:
    """
    Impute missing pollutant values using time-series interpolation.
    Falls back to forward-fill then backward-fill.
    """
    df = df.copy()
    for col in POLLUTANT_COLS:
        if col in df.columns:
            if method == "linear":
                df[col] = df[col].interpolate(method="linear", limit=6)
            df[col] = df[col].fillna(method="ffill").fillna(method="bfill")
    return df


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add engineered features useful for health and GIS analysis."""
    df = df.copy()

    # AQI category
    from config import get_aqi_category
    if "aqi" in df.columns:
        df["aqi_category"] = df["aqi"].apply(
            lambda x: get_aqi_category(x)["label"] if not pd.isna(x) else "Unknown"
        )
        df["aqi_color"] = df["aqi"].apply(
            lambda x: get_aqi_category(x)["color"] if not pd.isna(x) else "#aaaaaa"
        )

    # PM2.5 / PM10 ratio (indicator of source type)
    if "pm25" in df.columns and "pm10" in df.columns:
        df["pm_ratio"] = (df["pm25"] / df["pm10"].replace(0, np.nan)).round(3)

    # Rolling 8-hour O3 (for ozone AQI)
    if "o3" in df.columns and "timestamp" in df.columns:
        df = df.sort_values("timestamp")
        df["o3_8h"] = df["o3"].rolling(window=8, min_periods=1).mean().round(2)

    # Hour of day, day of week for temporal analysis
    if "timestamp" in df.columns:
        df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour
        df["day_of_week"] = pd.to_datetime(df["timestamp"]).dt.day_name()
        df["is_weekend"] = pd.to_datetime(df["timestamp"]).dt.weekday >= 5

    return df
