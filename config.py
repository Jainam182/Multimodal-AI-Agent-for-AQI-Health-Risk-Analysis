"""
config.py – Central configuration, constants, and environment loading.
All modules import from here; never scatter os.getenv() calls.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"

DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "aqi_store.db"))
CHROMA_PATH = os.getenv("CHROMA_PATH", str(DATA_DIR / "chroma_db"))

# ─── API Keys ─────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
WAQI_API_KEY = os.getenv("WAQI_API_KEY", "demo")   # 'demo' gives limited free access
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

# ─── LLM Config ───────────────────────────────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2048"))

# ─── App Defaults ─────────────────────────────────────────────────────────────
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Mumbai")
DEFAULT_PERSONA = os.getenv("DEFAULT_PERSONA", "general_population")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

ENABLE_SCRAPING_FALLBACK = os.getenv("ENABLE_SCRAPING_FALLBACK", "true").lower() == "true"
ENABLE_VECTOR_SEARCH = os.getenv("ENABLE_VECTOR_SEARCH", "true").lower() == "true"
ENABLE_REAL_TIME = os.getenv("ENABLE_REAL_TIME", "true").lower() == "true"

# ─── AQI Category Thresholds (India CPCB + US EPA hybrid) ─────────────────────
AQI_CATEGORIES = [
    {"range": (0, 50),   "label": "Good",                     "color": "#00e400", "hex": "#009966"},
    {"range": (51, 100), "label": "Satisfactory",             "color": "#ffff00", "hex": "#ffde33"},
    {"range": (101, 200),"label": "Moderately Polluted",      "color": "#ff7e00", "hex": "#ff9933"},
    {"range": (201, 300),"label": "Poor",                     "color": "#ff0000", "hex": "#cc0033"},
    {"range": (301, 400),"label": "Very Poor",                "color": "#8f3f97", "hex": "#660099"},
    {"range": (401, 500),"label": "Severe / Hazardous",       "color": "#7e0023", "hex": "#7e0023"},
]

def get_aqi_category(aqi: float) -> dict:
    """Returns the full category dict {range, label, color, hex}."""
    for cat in AQI_CATEGORIES:
        lo, hi = cat["range"]
        if lo <= aqi <= hi:
            return cat
    if aqi > 500:
        return AQI_CATEGORIES[-1]
    return AQI_CATEGORIES[0]

def get_aqi_label(aqi: float) -> str:
    """Returns just the label string e.g. 'Good', 'Poor'."""
    return get_aqi_category(aqi)["label"]

# ─── Pollutant WHO / India CPCB Safe Limits (µg/m³ or ppm) ──────────────────
POLLUTANT_LIMITS = {
    "pm25": {"who_24h": 15.0,  "india_24h": 60.0,  "unit": "µg/m³"},
    "pm10": {"who_24h": 45.0,  "india_24h": 100.0, "unit": "µg/m³"},
    "no2":  {"who_24h": 25.0,  "india_24h": 80.0,  "unit": "µg/m³"},
    "so2":  {"who_24h": 40.0,  "india_24h": 80.0,  "unit": "µg/m³"},
    "co":   {"who_24h": 4000.0,"india_24h": 2000.0, "unit": "µg/m³"},
    "o3":   {"who_8h":  100.0, "india_8h":  100.0,  "unit": "µg/m³"},
}

# ─── Persona Definitions ──────────────────────────────────────────────────────
PERSONAS = {
    "children":            {"label": "Children (< 12 yrs)",      "risk_multiplier": 1.5, "icon": "👶"},
    "elderly":             {"label": "Elderly (> 65 yrs)",        "risk_multiplier": 1.4, "icon": "👴"},
    "asthma_patient":      {"label": "Asthma Patients",           "risk_multiplier": 2.0, "icon": "🫁"},
    "copd_patient":        {"label": "COPD Patients",             "risk_multiplier": 2.2, "icon": "🫀"},
    "heart_patient":       {"label": "Heart/Cardiovascular",      "risk_multiplier": 1.8, "icon": "❤️"},
    "athlete":             {"label": "Athletes / Runners",        "risk_multiplier": 1.3, "icon": "🏃"},
    "outdoor_worker":      {"label": "Outdoor Workers",           "risk_multiplier": 1.6, "icon": "👷"},
    "general_population":  {"label": "General Population",        "risk_multiplier": 1.0, "icon": "👤"},
    "pregnant":            {"label": "Pregnant Women",            "risk_multiplier": 1.7, "icon": "🤰"},
    "respiratory_patient": {"label": "Respiratory Conditions",    "risk_multiplier": 1.9, "icon": "😮‍💨"},
}

# ─── Major Indian Cities with Coordinates ─────────────────────────────────────
INDIAN_CITIES = {
    "Mumbai":     {"lat": 19.0760, "lon": 72.8777, "stations": ["Bandra", "Kurla", "Andheri", "Colaba", "Worli", "Thane"]},
    "Delhi":      {"lat": 28.6139, "lon": 77.2090, "stations": ["Anand Vihar", "ITO", "Dwarka", "Rohini"]},
    "Pune":       {"lat": 18.5204, "lon": 73.8567, "stations": ["Shivajinagar", "Hadapsar", "Kothrud"]},
    "Bengaluru":  {"lat": 12.9716, "lon": 77.5946, "stations": ["Hebbal", "BTM Layout", "Jayanagar"]},
    "Chennai":    {"lat": 13.0827, "lon": 80.2707, "stations": ["Alandur", "Manali", "Velachery"]},
    "Hyderabad":  {"lat": 17.3850, "lon": 78.4867, "stations": ["Bollaram", "Jeedimetla", "Nacharam"]},
    "Kolkata":    {"lat": 22.5726, "lon": 88.3639, "stations": ["Ballygunge", "Jadavpur", "Victoria"]},
    "Ahmedabad":  {"lat": 23.0225, "lon": 72.5714, "stations": ["Maninagar", "Vatva", "Chandkheda"]},
    "Nagpur":     {"lat": 21.1458, "lon": 79.0882, "stations": ["Civil Lines", "Hingna"]},
    "Navi Mumbai":{"lat": 19.0330, "lon": 73.0297, "stations": ["Airoli", "Vashi", "Nerul"]},
}

# ─── WAQI Station IDs for Mumbai (from aqicn.org) ────────────────────────────
WAQI_MUMBAI_STATIONS = {
    "Bandra":       "@7021",
    "Kurla":        "@7022",
    "Andheri":      "@7023",
    "Colaba":       "@3119",
    "Worli":        "@7024",
    "Mazgaon":      "@7025",
    "Borivali":     "@7026",
    "Malad":        "@7027",
    "Thane":        "@7028",
    "Navi Mumbai":  "@7029",
}
