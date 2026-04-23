"""
agents/data_agent.py
─────────────────────
Real-data AQI ingestion — aqi.in as primary source.

Source priority:
  1. aqi.in   – city table (80+ stations per city, real PM2.5/PM10/AQI)
                + city-level CO/NO2/SO2/O3 from the same page
                + individual station detail pages for selected stations
  2. WAQI bounds API – fallback if aqi.in unreachable
  3. Open-Meteo    – fallback at real station coordinates
  4. WAQI search   – last-resort
  5. OpenWeather   – if key set
  6. Web scraping  – iqair, waqi.web
  Returns empty payload with error if all fail.
"""

from __future__ import annotations
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

from agents.base_agent import BaseAgent
from config import (
    ENABLE_SCRAPING_FALLBACK,
    INDIAN_CITIES,
    OPENWEATHER_API_KEY,
    WAQI_API_KEY,
    get_aqi_category,
)
from data.database import db
from data.vector_store import vector_store
from schemas.agent_messages import (
    AgentName, DataAgentOutput, DataSource,
    LocationReading, MessageStatus, PollutantReading,
)
from tools.aqi_tools import (
    add_derived_features, impute_missing_values,
    normalize_dataframe, compute_aqi_from_pollutants,
)
from tools.geo_tools import assign_mock_coordinates, geocode_city, get_bounding_box
from utils.logger import get_logger
from utils.retry import api_retry

logger = get_logger("DataAgent")

# ─── aqi.in URL routing: city name → (state-slug, city-slug) ─────────────────

AQI_IN_ROUTES: Dict[str, Tuple[str, str]] = {
    "Mumbai":      ("maharashtra",  "mumbai"),
    "Delhi":       ("delhi",        "new-delhi"),
    "Pune":        ("maharashtra",  "pune"),
    "Bengaluru":   ("karnataka",    "bangalore"),
    "Bangalore":   ("karnataka",    "bangalore"),
    "Chennai":     ("tamil-nadu",   "chennai"),
    "Hyderabad":   ("telangana",    "hyderabad"),
    "Kolkata":     ("west-bengal",  "kolkata"),
    "Ahmedabad":   ("gujarat",      "ahmedabad"),
    "Nagpur":      ("maharashtra",  "nagpur"),
    "Navi Mumbai": ("maharashtra",  "navi-mumbai"),
    "Surat":       ("gujarat",      "surat"),
    "Lucknow":     ("uttar-pradesh","lucknow"),
    "Kanpur":      ("uttar-pradesh","kanpur"),
    "Jaipur":      ("rajasthan",    "jaipur"),
    "Patna":       ("bihar",        "patna"),
    "Bhopal":      ("madhya-pradesh","bhopal"),
    "Indore":      ("madhya-pradesh","indore"),
    "Agra":        ("uttar-pradesh","agra"),
    "Noida":       ("uttar-pradesh","noida"),
}

# ─── Unit conversion constants ────────────────────────────────────────────────
# aqi.in reports CO, NO2, SO2, O3 in ppb; we store in µg/m³
PPB_TO_UGM3 = {
    "co":  1.145,  # CO:  1 ppb = 1.145 µg/m³
    "no2": 1.88,   # NO2: 1 ppb = 1.88 µg/m³
    "so2": 2.62,   # SO2: 1 ppb = 2.62 µg/m³
    "o3":  1.96,   # O3:  1 ppb = 1.96 µg/m³
}

# ─── Real CPCB station coordinates (for coordinate enrichment) ────────────────
CITY_STATIONS: Dict[str, List[Dict]] = {
    "Mumbai": [
        {"name": "Bandra East",     "lat": 19.0596, "lon": 72.8538},
        {"name": "Andheri East",    "lat": 19.1197, "lon": 72.8697},
        {"name": "Colaba",          "lat": 18.9067, "lon": 72.8147},
        {"name": "Worli",           "lat": 19.0176, "lon": 72.8157},
        {"name": "Mazgaon",         "lat": 18.9667, "lon": 72.8450},
        {"name": "Borivali East",   "lat": 19.2288, "lon": 72.8566},
        {"name": "Malad",           "lat": 19.1863, "lon": 72.8484},
        {"name": "Kurla",           "lat": 19.0726, "lon": 72.8845},
        {"name": "Chembur",         "lat": 19.0626, "lon": 72.8993},
        {"name": "Juhu",            "lat": 19.1006, "lon": 72.8282},
        {"name": "Sion",            "lat": 19.0390, "lon": 72.8619},
        {"name": "Wadala East",     "lat": 19.0182, "lon": 72.8631},
        {"name": "Dahisar East",    "lat": 19.2500, "lon": 72.8700},
        {"name": "Kandivali East",  "lat": 19.2073, "lon": 72.8608},
        {"name": "Mulund West",     "lat": 19.1724, "lon": 72.9561},
    ],
    "Delhi": [
        {"name": "Anand Vihar",     "lat": 28.6469, "lon": 77.3159},
        {"name": "ITO",             "lat": 28.6289, "lon": 77.2429},
        {"name": "Dwarka Sec 8",    "lat": 28.5921, "lon": 77.0459},
        {"name": "Rohini",          "lat": 28.7279, "lon": 77.1178},
        {"name": "Okhla Phase 2",   "lat": 28.5355, "lon": 77.2720},
        {"name": "Punjabi Bagh",    "lat": 28.6664, "lon": 77.1313},
        {"name": "RK Puram",        "lat": 28.5672, "lon": 77.1721},
        {"name": "Wazirpur",        "lat": 28.6978, "lon": 77.1614},
        {"name": "Jahangirpuri",    "lat": 28.7368, "lon": 77.1646},
        {"name": "Mundka",          "lat": 28.6930, "lon": 77.0290},
    ],
    "Pune": [
        {"name": "Shivajinagar",    "lat": 18.5308, "lon": 73.8475},
        {"name": "Hadapsar",        "lat": 18.5089, "lon": 73.9260},
        {"name": "Kothrud",         "lat": 18.5074, "lon": 73.8077},
        {"name": "Pimpri",          "lat": 18.6186, "lon": 73.8006},
    ],
    "Bengaluru": [
        {"name": "Hebbal",          "lat": 13.0353, "lon": 77.5970},
        {"name": "BTM Layout",      "lat": 12.9165, "lon": 77.6101},
        {"name": "Silk Board",      "lat": 12.9177, "lon": 77.6229},
        {"name": "Peenya",          "lat": 13.0296, "lon": 77.5198},
    ],
    "Chennai": [
        {"name": "Alandur",         "lat": 13.0012, "lon": 80.2050},
        {"name": "Manali",          "lat": 13.1671, "lon": 80.2650},
        {"name": "Velachery",       "lat": 12.9815, "lon": 80.2180},
        {"name": "Aminjikarai",     "lat": 13.0732, "lon": 80.2310},
    ],
    "Hyderabad": [
        {"name": "Bollaram",        "lat": 17.4975, "lon": 78.3927},
        {"name": "Jeedimetla",      "lat": 17.4969, "lon": 78.4374},
        {"name": "Nacharam",        "lat": 17.4042, "lon": 78.5444},
        {"name": "Jubilee Hills",   "lat": 17.4265, "lon": 78.4080},
    ],
    "Kolkata": [
        {"name": "Ballygunge",      "lat": 22.5241, "lon": 88.3670},
        {"name": "Jadavpur",        "lat": 22.4975, "lon": 88.3713},
        {"name": "Bidhannagar",     "lat": 22.5697, "lon": 88.4296},
        {"name": "Ghusuri",         "lat": 22.5806, "lon": 88.3382},
    ],
    "Ahmedabad": [
        {"name": "Maninagar",       "lat": 22.9905, "lon": 72.6047},
        {"name": "Vatva",           "lat": 22.9513, "lon": 72.6431},
        {"name": "Chandkheda",      "lat": 23.1025, "lon": 72.5849},
    ],
}


class DataAgent(BaseAgent):
    agent_name = AgentName.DATA
    _session: Optional[requests.Session] = None
    _coord_cache: Dict[str, Tuple[float, float]] = {}

    def _http(self) -> requests.Session:
        if self._session is None:
            s = requests.Session()
            s.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            })
            self._session = s
        return self._session

    # ─── _execute ─────────────────────────────────────────────────────────────

    def _execute(
        self,
        message_id: str,
        city: str = "Mumbai",
        mode: str = "current",
        days: int = 7,
        uploaded_df=None,
        stations=None,
        **kwargs,
    ) -> DataAgentOutput:

        logger.info(f"DataAgent: city={city}, mode={mode}")
        sources_used: List[DataSource] = []
        locations:    List[LocationReading] = []

        # ── 0: CSV upload ─────────────────────────────────────────────────────
        if uploaded_df is not None and not uploaded_df.empty:
            locations, src = self._from_csv(uploaded_df, city)
            sources_used.append(src)
            logger.info(f"CSV: {len(locations)} readings")

        # ── 1: aqi.in PRIMARY SOURCE ──────────────────────────────────────────
        if not locations:
            try:
                locs = self._scrape_aqi_in_full(city)
                if locs:
                    locations = locs
                    sources_used.append(DataSource.SCRAPING)
                    logger.info(f"aqi.in: {len(locs)} stations for {city}")
            except Exception as e:
                logger.warning(f"aqi.in failed: {e}")

        # ── 2: WAQI bounding-box ──────────────────────────────────────────────
        if not locations:
            try:
                locs = self._fetch_waqi_bounds(city)
                if locs:
                    locations = locs
                    sources_used.append(DataSource.WAQI)
                    logger.info(f"WAQI bounds: {len(locs)} for {city}")
            except Exception as e:
                logger.warning(f"WAQI bounds failed: {e}")

        # ── 3: Open-Meteo at real station coordinates ─────────────────────────
        if not locations:
            try:
                locs = self._fetch_open_meteo_stations(city)
                if locs:
                    locations = locs
                    sources_used.append(DataSource.SCRAPING)
                    logger.info(f"Open-Meteo: {len(locs)} for {city}")
            except Exception as e:
                logger.warning(f"Open-Meteo failed: {e}")

        # ── 4: WAQI city search ───────────────────────────────────────────────
        if not locations:
            try:
                locs = self._fetch_waqi_city_search(city)
                if locs:
                    locations = locs
                    sources_used.append(DataSource.WAQI)
                    logger.info(f"WAQI search: {len(locs)} for {city}")
            except Exception as e:
                logger.debug(f"WAQI search failed: {e}")

        # ── 5: OpenWeather ────────────────────────────────────────────────────
        if not locations and OPENWEATHER_API_KEY:
            try:
                locs = self._fetch_openweather(city)
                if locs:
                    locations = locs
                    sources_used.append(DataSource.OPENWEATHER)
            except Exception as e:
                logger.debug(f"OpenWeather failed: {e}")

        # ── 6: IQAir scraper ─────────────────────────────────────────────────
        if not locations and ENABLE_SCRAPING_FALLBACK:
            try:
                locs = self._scrape_iqair(city)
                if locs:
                    locations = locs
                    sources_used.append(DataSource.SCRAPING)
            except Exception as e:
                logger.debug(f"IQAir failed: {e}")

        # ── No data ───────────────────────────────────────────────────────────
        if not locations:
            msg = (
                f"Could not fetch AQI data for {city}. "
                "Check internet connection. No synthetic data used."
            )
            logger.error(msg)
            return DataAgentOutput(
                message_id=message_id,
                status=MessageStatus.ERROR,
                errors=[msg],
                payload={"city": city, "readings": [], "total_records": 0,
                         "sources_used": [], "data_quality_avg": 0, "error": msg},
            )

        # ── POLLUTANT ENRICHMENT ──────────────────────────────────────────────
        # Ensure every reading has real pollutant concentrations, not just AQI.
        # Sources like WAQI bounds/search only return AQI; we enrich them with
        # the WAQI feed API or Open-Meteo so that Hazard Index, synergy, and
        # MPRS can actually function.
        locations = self._enrich_readings_with_pollutants(locations, city)

        self._persist_readings(locations)
        self._index_summaries(locations, city)

        total = len(locations)
        avg_q = sum(r.data_quality for r in locations) / total
        return DataAgentOutput(
            message_id=message_id,
            source_agent=AgentName.DATA,
            status=MessageStatus.SUCCESS,
            payload={
                "city":             city,
                "readings":         [loc.to_dict() for loc in locations],
                "total_records":    total,
                "sources_used":     [s.value for s in sources_used],
                "data_quality_avg": round(avg_q, 3),
            },
        )

    # =========================================================================
    # SOURCE 1 — aqi.in  (PRIMARY)
    # =========================================================================

    def _scrape_aqi_in_full(self, city: str) -> List[LocationReading]:
        """
        Full aqi.in scraper:
          1. Fetch city dashboard page
          2. Parse the locations table → up to 30 stations with AQI, PM2.5, PM10
          3. Parse the city-level pollutant section → CO, NO2, SO2, O3
          4. Enrich top 5 stations with individual station pages for full pollutants
          5. Geocode station names for accurate map positions
        """
        from bs4 import BeautifulSoup

        route = self._get_aqi_in_route(city)
        if not route:
            logger.debug(f"No aqi.in route for city: {city}")
            return []

        state_slug, city_slug = route
        city_url = f"https://www.aqi.in/in/dashboard/india/{state_slug}/{city_slug}"

        resp = self._http().get(city_url, timeout=18)
        if resp.status_code != 200:
            logger.warning(f"aqi.in {city_url} returned {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")

        # ── Parse city-level pollutants from "Major Air Pollutants" section ──
        city_polls = self._parse_city_pollutants(soup)
        logger.debug(f"aqi.in city polls for {city}: {city_polls}")

        # ── Parse the locations table ─────────────────────────────────────────
        stations_raw = self._parse_locations_table(soup)
        logger.info(f"aqi.in: parsed {len(stations_raw)} station rows for {city}")

        if not stations_raw:
            return []

        # ── Build LocationReadings ─────────────────────────────────────────────
        now = datetime.now(timezone.utc)
        readings: List[LocationReading] = []
        enriched_count = 0

        for i, stn in enumerate(stations_raw[:30]):  # max 30 stations
            station_name = stn["name"]
            aqi_us   = stn.get("aqi")
            pm25_raw = stn.get("pm25")
            pm10_raw = stn.get("pm10")

            if not aqi_us:
                continue

            # Compute CPCB AQI from PM2.5/PM10 (more accurate for India)
            polls_for_aqi = {}
            if pm25_raw:
                polls_for_aqi["pm25"] = pm25_raw
            if pm10_raw:
                polls_for_aqi["pm10"] = pm10_raw

            if polls_for_aqi:
                cpcb_aqi, _ = compute_aqi_from_pollutants(polls_for_aqi)
            else:
                # Fall back to US AQI (close enough)
                cpcb_aqi = aqi_us

            if not cpcb_aqi or cpcb_aqi <= 0:
                continue

            # Get coordinates
            lat, lon = self._geocode_station(station_name, city, stn.get("slug", ""))

            # Use city-level CO/NO2/SO2/O3 (same for all stations in the city)
            pollutants = PollutantReading(
                pm25=pm25_raw,
                pm10=pm10_raw,
                no2=city_polls.get("no2"),
                so2=city_polls.get("so2"),
                co=city_polls.get("co"),
                o3=city_polls.get("o3"),
                aqi=round(cpcb_aqi, 1),
                aqi_category=get_aqi_category(cpcb_aqi)["label"],
            )

            # For first 5 stations, try to enrich with individual station page
            if enriched_count < 5 and stn.get("slug"):
                try:
                    enriched = self._fetch_station_detail_page(
                        state_slug, city_slug, stn["slug"],
                        station_name, city, lat, lon, now
                    )
                    if enriched:
                        readings.append(enriched)
                        enriched_count += 1
                        time.sleep(0.3)  # polite delay
                        continue
                except Exception:
                    pass  # fall through to table data

            readings.append(LocationReading(
                station_name=station_name,
                city=city,
                lat=lat, lon=lon,
                timestamp=now,
                pollutants=pollutants,
                data_quality=0.88,
                source=DataSource.SCRAPING,
            ))

        return readings

    def _parse_city_pollutants(self, soup) -> Dict[str, Optional[float]]:
        """
        Parse the 'Major Air Pollutants' section on the city page.
        Returns dict with keys: pm25, pm10, co, so2, no2, o3 in µg/m³.
        aqi.in shows CO/NO2/SO2/O3 in ppb — convert to µg/m³.
        """
        polls = {"pm25": None, "pm10": None, "co": None, "so2": None, "no2": None, "o3": None}

        # Look for the pollutant card section
        # Pattern: element containing "PM2.5" near a numeric value
        pollutant_map = {
            "pm2.5":          "pm25",
            "pm₂.₅":          "pm25",
            "pm10":           "pm10",
            "pm₁₀":           "pm10",
            "carbon monoxide": "co",
            "(co)":           "co",
            "sulfur dioxide":  "so2",
            "sulphur dioxide": "so2",
            "(so2)":          "so2",
            "(so₂)":          "so2",
            "nitrogen dioxide":"no2",
            "(no2)":          "no2",
            "(no₂)":          "no2",
            "ozone":          "o3",
            "(o3)":           "o3",
            "(o₃)":           "o3",
        }

        # Try to find pollutant cards / links with data
        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "").lower()
            text = a_tag.get_text(" ", strip=True).lower()

            # Identify pollutant from href or text
            poll_key = None
            for keyword, key in pollutant_map.items():
                if keyword in href or keyword in text:
                    poll_key = key
                    break

            if not poll_key:
                continue

            # Find the numeric value near this element
            full_text = a_tag.get_text(" ", strip=True)
            nums = re.findall(r"(\d+\.?\d*)\s*(?:µg/m³|ppb|ppm|mg/m³)?", full_text)

            if nums:
                val = float(nums[-1])  # last number is usually the measurement
                if val > 0:
                    # Convert ppb → µg/m³ if CO/NO2/SO2/O3
                    if poll_key in PPB_TO_UGM3 and "µg" not in full_text.lower():
                        val = round(val * PPB_TO_UGM3[poll_key], 2)
                    polls[poll_key] = val

        # Also try a text scan of the whole page for city-level readings
        # aqi.in city page shows "PM2.5 : 44 µg/m³" in the AQI widget
        page_text = soup.get_text(" ")
        for pattern, key, is_ppb in [
            (r"PM2\.5\s*[:：]\s*(\d+\.?\d*)\s*µg",  "pm25",  False),
            (r"pm10\s*[:：]\s*(\d+\.?\d*)\s*µg",     "pm10",  False),
            (r"CO\)\s*(\d+\.?\d*)\s*ppb",             "co",    True),
            (r"SO2\)\s*(\d+\.?\d*)\s*ppb",            "so2",   True),
            (r"SO₂\)\s*(\d+\.?\d*)\s*ppb",            "so2",   True),
            (r"NO2\)\s*(\d+\.?\d*)\s*ppb",            "no2",   True),
            (r"NO₂\)\s*(\d+\.?\d*)\s*ppb",            "no2",   True),
            (r"O3\)\s*(\d+\.?\d*)\s*ppb",             "o3",    True),
            (r"O₃\)\s*(\d+\.?\d*)\s*ppb",             "o3",    True),
        ]:
            if polls[key] is None:
                m = re.search(pattern, page_text, re.IGNORECASE)
                if m:
                    val = float(m.group(1))
                    if is_ppb:
                        val = round(val * PPB_TO_UGM3.get(key, 1.0), 2)
                    polls[key] = val

        return polls

    def _parse_locations_table(self, soup) -> List[Dict]:
        """
        Parse the locations table from the aqi.in city page.
        Table header: Location | Status | AQI (US) | PM2.5 | PM10 | Temp | Humi
        Returns list of dicts.
        """
        stations = []

        # Find the table — look for table with 'Location' header
        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            if not headers:
                # Try first row as header
                first_row = table.find("tr")
                if first_row:
                    headers = [td.get_text(strip=True).lower() for td in first_row.find_all(["th","td"])]

            if not any("location" in h or "aqi" in h for h in headers):
                continue

            # Identify column indices
            col_idx = {}
            for i, h in enumerate(headers):
                if "location" in h:
                    col_idx["name"] = i
                elif "aqi" in h:
                    col_idx["aqi"] = i
                elif "pm2" in h or "pm2.5" in h:
                    col_idx["pm25"] = i
                elif "pm10" in h:
                    col_idx["pm10"] = i
                elif "status" in h:
                    col_idx["status"] = i
                elif "temp" in h:
                    col_idx["temp"] = i
                elif "hum" in h:
                    col_idx["humi"] = i

            if "name" not in col_idx or "aqi" not in col_idx:
                continue

            # Parse rows
            for row in table.find_all("tr")[1:]:  # skip header row
                cells = row.find_all(["td", "th"])
                if len(cells) < max(col_idx.values()) + 1:
                    continue
                try:
                    # Station name from link text
                    name_cell = cells[col_idx["name"]]
                    link = name_cell.find("a")
                    station_name = (link.get_text(strip=True) if link
                                    else name_cell.get_text(strip=True))
                    if not station_name:
                        continue

                    # Station slug from href
                    slug = ""
                    if link and link.get("href"):
                        slug = link["href"].rstrip("/").split("/")[-1]

                    # Numeric values
                    def _num(idx_key):
                        if idx_key not in col_idx:
                            return None
                        txt = cells[col_idx[idx_key]].get_text(strip=True)
                        nums = re.findall(r"\d+\.?\d*", txt)
                        return float(nums[0]) if nums else None

                    aqi  = _num("aqi")
                    pm25 = _num("pm25")
                    pm10 = _num("pm10")
                    temp = _num("temp")
                    humi = _num("humi")

                    if not aqi or aqi <= 0:
                        continue

                    stations.append({
                        "name": station_name,
                        "slug": slug,
                        "aqi":  aqi,
                        "pm25": pm25,
                        "pm10": pm10,
                        "temp": temp,
                        "humi": humi,
                        "status": (cells[col_idx["status"]].get_text(strip=True)
                                   if "status" in col_idx else ""),
                    })
                except (IndexError, ValueError, TypeError):
                    continue

            if stations:
                break  # found the right table

        return stations

    def _fetch_station_detail_page(
        self,
        state_slug: str, city_slug: str, station_slug: str,
        station_name: str, city: str,
        lat: float, lon: float, ts: datetime,
    ) -> Optional[LocationReading]:
        """
        Fetch individual station page for full pollutant breakdown.
        URL: /in/dashboard/india/{state}/{city}/{station}
        """
        from bs4 import BeautifulSoup

        url = f"https://www.aqi.in/in/dashboard/india/{state_slug}/{city_slug}/{station_slug}"
        resp = self._http().get(url, timeout=12)
        if resp.status_code != 200:
            return None

        soup  = BeautifulSoup(resp.text, "lxml")
        text  = soup.get_text(" ")

        def _extract(patterns, is_ppb=False):
            for pat in patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    val = float(m.group(1))
                    if is_ppb:
                        val = round(val * PPB_TO_UGM3.get(
                            pat.split("(")[0].strip().lower(), 1.0), 2)
                    return val
            return None

        # AQI from widget
        aqi_m = re.search(r"(\d{2,3})\s*AQI", text)
        aqi   = float(aqi_m.group(1)) if aqi_m else None

        pm25 = _extract([r"PM2\.5.*?(\d+\.?\d*)\s*µg", r"PM₂\.₅.*?(\d+\.?\d*)\s*µg",
                         r"Particulate Matter\(PM.*?\)\s*(\d+\.?\d*)\s*µg"])
        pm10 = _extract([r"PM10.*?(\d+\.?\d*)\s*µg",   r"PM₁₀.*?(\d+\.?\d*)\s*µg"])
        co   = _extract([r"\(CO\)\s*(\d+\.?\d*)\s*ppb"], is_ppb=True)
        no2  = _extract([r"\(NO2\)\s*(\d+\.?\d*)\s*ppb",
                          r"\(NO₂\)\s*(\d+\.?\d*)\s*ppb"], is_ppb=True)
        so2  = _extract([r"\(SO2\)\s*(\d+\.?\d*)\s*ppb",
                          r"\(SO₂\)\s*(\d+\.?\d*)\s*ppb"], is_ppb=True)
        o3   = _extract([r"\(O3\)\s*(\d+\.?\d*)\s*ppb",
                          r"\(O₃\)\s*(\d+\.?\d*)\s*ppb"], is_ppb=True)

        # Re-compute CPCB AQI
        polls = {k: v for k, v in {"pm25": pm25, "pm10": pm10, "no2": no2, "so2": so2, "o3": o3}.items() if v}
        if polls:
            cpcb, _ = compute_aqi_from_pollutants(polls)
            if cpcb and cpcb > 0:
                aqi = cpcb

        if not aqi:
            return None

        return LocationReading(
            station_name=station_name,
            city=city,
            lat=lat, lon=lon,
            timestamp=ts,
            pollutants=PollutantReading(
                pm25=pm25, pm10=pm10, no2=no2, so2=so2, co=co, o3=o3,
                aqi=round(aqi, 1),
                aqi_category=get_aqi_category(aqi)["label"],
            ),
            data_quality=0.93,
            source=DataSource.SCRAPING,
        )

    # ─── Coordinate resolution ────────────────────────────────────────────────

    def _get_aqi_in_route(self, city: str) -> Optional[Tuple[str, str]]:
        """Return (state_slug, city_slug) for aqi.in URL construction."""
        if city in AQI_IN_ROUTES:
            return AQI_IN_ROUTES[city]
        # Try case-insensitive match
        city_lower = city.lower()
        for k, v in AQI_IN_ROUTES.items():
            if k.lower() == city_lower:
                return v
        return None

    def _geocode_station(self, station_name: str, city: str, slug: str = "") -> Tuple[float, float]:
        """
        Resolve coordinates for a station:
        1. Check CITY_STATIONS known list (exact name match)
        2. Check coordinate cache
        3. Nominatim geocoding with station + city query
        4. Fall back to assign_mock_coordinates
        """
        # 1. Known stations
        for stn in CITY_STATIONS.get(city, []):
            if stn["name"].lower() == station_name.lower():
                return stn["lat"], stn["lon"]

        # 2. Cache hit
        cache_key = f"{station_name}|{city}"
        if cache_key in self._coord_cache:
            return self._coord_cache[cache_key]

        # 3. Nominatim — only for well-formed station names
        if len(station_name) > 4 and station_name.replace(" ", "").isalpha():
            try:
                resp = requests.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": f"{station_name}, {city}, India",
                            "format": "json", "limit": 1},
                    headers={"User-Agent": "AQIHealthSystem/2.0"},
                    timeout=5,
                )
                results = resp.json()
                if results:
                    lat = float(results[0]["lat"])
                    lon = float(results[0]["lon"])
                    self._coord_cache[cache_key] = (lat, lon)
                    return lat, lon
            except Exception:
                pass

        # 4. Deterministic offset from city centre
        lat, lon = assign_mock_coordinates(station_name, city)
        self._coord_cache[cache_key] = (lat, lon)
        return lat, lon

    # =========================================================================
    # SOURCE 2 — WAQI bounding-box
    # =========================================================================

    def _fetch_waqi_bounds(self, city: str) -> List[LocationReading]:
        coords = geocode_city(city)
        if not coords:
            return []
        lat, lon = coords
        bb    = get_bounding_box(lat, lon, radius_km=25)
        token = WAQI_API_KEY or "demo"

        url = (
            f"https://api.waqi.info/map/bounds/"
            f"?latlng={bb['min_lat']:.4f},{bb['min_lon']:.4f},"
            f"{bb['max_lat']:.4f},{bb['max_lon']:.4f}&token={token}"
        )
        resp = self._http().get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "ok":
            return []

        readings = []
        for item in data.get("data", []):
            r = self._waqi_map_item(item, city)
            if r:
                readings.append(r)
        return readings

    def _waqi_map_item(self, item: Dict, city: str) -> Optional[LocationReading]:
        """Convert a WAQI bounds/map API item to LocationReading.
        WAQI provides AQI directly — we use it as-is (matches website).
        Pollutant concentrations are added later by Open-Meteo enrichment."""
        try:
            aqi_raw = item.get("aqi")
            if not aqi_raw or aqi_raw == "-":
                return None
            aqi = float(aqi_raw)
            if aqi <= 0:
                return None
            name = (item.get("station", {}).get("name") or "Unknown").strip()
            lat  = float(item.get("lat", 0))
            lon  = float(item.get("lon", 0))

            return LocationReading(
                station_name=name, city=city, lat=lat, lon=lon,
                timestamp=datetime.now(timezone.utc),
                pollutants=PollutantReading(
                    aqi=round(aqi, 1),
                    aqi_category=get_aqi_category(aqi)["label"],
                ),
                data_quality=0.75, source=DataSource.WAQI,
            )
        except Exception:
            return None

    def _fetch_waqi_station_feed(self, station_uid) -> Optional[Dict[str, float]]:
        """
        Fetch individual station pollutant data from WAQI feed API.
        Returns dict of pollutant concentrations in µg/m³.
        """
        token = WAQI_API_KEY or "demo"
        try:
            url = f"https://api.waqi.info/feed/@{station_uid}/?token={token}"
            resp = self._http().get(url, timeout=10)
            data = resp.json()
            if data.get("status") != "ok":
                return None

            iaqi = data.get("data", {}).get("iaqi", {})
            result = {}
            for key, poll_name in [("pm25", "pm25"), ("pm10", "pm10"),
                                    ("no2", "no2"), ("so2", "so2"),
                                    ("co", "co"), ("o3", "o3")]:
                val = iaqi.get(key, {}).get("v")
                if val is not None:
                    result[poll_name] = round(float(val), 2)

            return result if result else None
        except Exception:
            return None

    # =========================================================================
    # SOURCE 3 — Open-Meteo at real station coordinates
    # =========================================================================

    def _fetch_open_meteo_stations(self, city: str) -> List[LocationReading]:
        coords = geocode_city(city)
        if not coords:
            return []
        city_lat, city_lon = coords
        stations = CITY_STATIONS.get(city, self._grid_stations(city, city_lat, city_lon))
        readings = []
        for stn in stations:
            try:
                r = self._open_meteo_single(stn["name"], city, stn["lat"], stn["lon"])
                if r:
                    readings.append(r)
            except Exception:
                pass
        return readings

    def _open_meteo_single(self, name, city, lat, lon):
        url = (
            "https://air-quality-api.open-meteo.com/v1/air-quality"
            f"?latitude={lat:.4f}&longitude={lon:.4f}"
            "&hourly=pm2_5,pm10,nitrogen_dioxide,ozone,sulphur_dioxide,carbon_monoxide"
            "&timezone=Asia/Kolkata&forecast_days=1&past_days=0"
        )
        resp = self._http().get(url, timeout=12)
        resp.raise_for_status()
        hourly = resp.json().get("hourly", {})
        times  = hourly.get("time", [])
        pm25s  = hourly.get("pm2_5", [])
        if not times:
            return None
        best = next((i for i in range(len(times)-1,-1,-1) if i < len(pm25s) and pm25s[i] is not None), None)
        if best is None:
            return None
        def _s(k):
            s = hourly.get(k, [])
            try:
                v = s[best] if best < len(s) else None
                return round(float(v), 2) if v is not None else None
            except (TypeError, ValueError):
                return None
        pm25 = _s("pm2_5"); pm10 = _s("pm10"); no2 = _s("nitrogen_dioxide")
        o3   = _s("ozone"); so2  = _s("sulphur_dioxide"); co_raw = _s("carbon_monoxide")
        co   = round(co_raw/1000, 4) if co_raw else None
        polls = {k: v for k, v in {"pm25":pm25,"pm10":pm10,"no2":no2,"so2":so2,"o3":o3}.items() if v}
        if not polls:
            return None
        aqi, _ = compute_aqi_from_pollutants(polls)
        if not aqi or aqi <= 0:
            return None
        try:
            ts = datetime.fromisoformat(times[best])
        except Exception:
            ts = datetime.now(timezone.utc)
        return LocationReading(
            station_name=name, city=city, lat=lat, lon=lon, timestamp=ts,
            pollutants=PollutantReading(pm25=pm25, pm10=pm10, no2=no2, o3=o3, so2=so2, co=co,
                aqi=round(aqi,1), aqi_category=get_aqi_category(aqi)["label"]),
            data_quality=0.88, source=DataSource.SCRAPING,
        )

    def _grid_stations(self, city, lat, lon):
        step = 0.018
        return [{"name": f"{city} {d}", "lat": round(lat+dlat, 6), "lon": round(lon+dlon, 6)}
                for d, dlat, dlon in [("N",0,-step),("S",0,step),("E",step,0),("W",-step,0),("Centre",0,0)]]

    def _fetch_open_meteo_historical(self, city: str, days: int = 30) -> List[Dict]:
        coords = geocode_city(city)
        if not coords:
            return []
        lat, lon = coords
        end   = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        url   = (
            "https://air-quality-api.open-meteo.com/v1/air-quality"
            f"?latitude={lat:.4f}&longitude={lon:.4f}"
            "&hourly=pm2_5,pm10,nitrogen_dioxide,ozone,sulphur_dioxide,carbon_monoxide"
            f"&start_date={start}&end_date={end}&timezone=Asia/Kolkata"
        )
        resp   = self._http().get(url, timeout=20)
        resp.raise_for_status()
        hourly = resp.json().get("hourly", {})
        times  = hourly.get("time", [])
        if not times:
            return []
        records = []
        def _sv(series, i):
            try:
                v = series[i] if i < len(series) else None
                return round(float(v), 2) if v is not None else None
            except (TypeError, ValueError):
                return None
        pm25s = hourly.get("pm2_5",[]); pm10s = hourly.get("pm10",[]); no2s = hourly.get("nitrogen_dioxide",[])
        o3s   = hourly.get("ozone",[]); so2s  = hourly.get("sulphur_dioxide",[]); cos = hourly.get("carbon_monoxide",[])
        for i, t in enumerate(times):
            pm25 = _sv(pm25s,i); pm10 = _sv(pm10s,i); no2 = _sv(no2s,i)
            o3   = _sv(o3s,i);   so2  = _sv(so2s,i);  co_raw = _sv(cos,i)
            co   = round(co_raw/1000, 4) if co_raw else None
            polls = {k: v for k,v in {"pm25":pm25,"pm10":pm10,"no2":no2,"so2":so2,"o3":o3}.items() if v}
            aqi, _ = compute_aqi_from_pollutants(polls) if polls else (None, None)
            if not aqi:
                continue
            try:
                ts = datetime.fromisoformat(t)
            except Exception:
                continue
            records.append({"timestamp": ts, "station_name": city, "city": city,
                             "aqi": round(aqi,1), "aqi_category": get_aqi_category(aqi)["label"],
                             "pm25": pm25, "pm10": pm10, "no2": no2, "so2": so2, "o3": o3, "co": co,
                             "source": "open_meteo", "data_quality": 0.88})
        return records

    # =========================================================================
    # SOURCE 4 — WAQI city search
    # =========================================================================

    def _fetch_waqi_city_search(self, city: str) -> List[LocationReading]:
        """WAQI search API — returns station AQI values (matches website).
        Pollutant concentrations are added later by Open-Meteo enrichment."""
        token = WAQI_API_KEY or "demo"
        resp  = self._http().get(
            f"https://api.waqi.info/search/?token={token}&keyword={city}", timeout=10)
        data  = resp.json()
        if data.get("status") != "ok":
            return []
        readings = []
        for item in data.get("data", [])[:8]:
            try:
                aqi_raw = item.get("aqi")
                if not aqi_raw or str(aqi_raw) == "-":
                    continue
                aqi = float(aqi_raw)
                if aqi <= 0:
                    continue
                stn = item.get("station", {})
                geo = stn.get("geo", [0, 0])
                readings.append(LocationReading(
                    station_name=stn.get("name", "Unknown"), city=city,
                    lat=float(geo[0]), lon=float(geo[1]),
                    timestamp=datetime.now(timezone.utc),
                    pollutants=PollutantReading(
                        aqi=round(aqi, 1),
                        aqi_category=get_aqi_category(aqi)["label"],
                    ),
                    data_quality=0.70, source=DataSource.WAQI,
                ))
            except Exception:
                continue
        return readings

    # =========================================================================
    # SOURCE 5 — OpenWeather
    # =========================================================================

    @api_retry
    def _fetch_openweather(self, city: str) -> List[LocationReading]:
        coords = geocode_city(city)
        if not coords:
            return []
        lat, lon = coords
        resp = self._http().get(
            f"http://api.openweathermap.org/data/2.5/air_pollution"
            f"?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}", timeout=10)
        data = resp.json()
        if "list" not in data or not data["list"]:
            return []
        item = data["list"][0]; comp = item.get("components", {})
        polls = {k: v for k,v in {"pm25": comp.get("pm2_5"), "pm10": comp.get("pm10"),
                                   "no2": comp.get("no2"), "so2": comp.get("so2"),
                                   "o3": comp.get("o3")}.items() if v}
        aqi, _ = compute_aqi_from_pollutants(polls)
        return [LocationReading(
            station_name=f"{city} (OpenWeather)", city=city, lat=lat, lon=lon,
            timestamp=datetime.fromtimestamp(item.get("dt",0), tz=timezone.utc),
            pollutants=PollutantReading(
                pm25=comp.get("pm2_5"), pm10=comp.get("pm10"),
                no2=comp.get("no2"), co=comp.get("co"), so2=comp.get("so2"), o3=comp.get("o3"),
                aqi=aqi, aqi_category=get_aqi_category(aqi or 0)["label"]),
            data_quality=0.85, source=DataSource.OPENWEATHER,
        )]

    # =========================================================================
    # SOURCE 6 — IQAir scraper
    # =========================================================================

    def _scrape_iqair(self, city: str) -> List[LocationReading]:
        try:
            from bs4 import BeautifulSoup
            slug = city.lower().replace(" ", "-")
            resp = self._http().get(f"https://www.iqair.com/india/{slug}", timeout=12)
            soup = BeautifulSoup(resp.text, "lxml")
            for sel in [".aqi-value", ".aqi__value", "[class*='aqi-value']"]:
                el = soup.select_one(sel)
                if el:
                    nums = re.findall(r"\d+", el.get_text())
                    if nums:
                        us_aqi = float(nums[0])
                        cpcb   = min(us_aqi * 1.05, 500)
                        c      = geocode_city(city)
                        lat, lon = c if c else (0, 0)
                        return [LocationReading(
                            station_name=f"{city} (IQAir)", city=city, lat=lat, lon=lon,
                            timestamp=datetime.now(timezone.utc),
                            pollutants=PollutantReading(aqi=round(cpcb,1),
                                aqi_category=get_aqi_category(cpcb)["label"]),
                            data_quality=0.70, source=DataSource.SCRAPING,
                        )]
        except Exception:
            pass
        return []

    # =========================================================================
    # CSV upload
    # =========================================================================

    def _from_csv(self, df, city):
        df = normalize_dataframe(df)
        df = impute_missing_values(df)
        df = add_derived_features(df)
        readings = []
        for _, row in df.iterrows():
            station = row.get("station_name", city)
            lat = float(row.get("lat", 0)) or assign_mock_coordinates(station, city)[0]
            lon = float(row.get("lon", 0)) or assign_mock_coordinates(station, city)[1]
            ts  = row.get("timestamp", datetime.now(timezone.utc))
            if pd.isna(ts):
                ts = datetime.now(timezone.utc)
            aqi = float(row.get("aqi") or 0)
            readings.append(LocationReading(
                station_name=str(station), city=city, lat=lat, lon=lon,
                timestamp=ts if hasattr(ts, "tzinfo") else datetime.now(timezone.utc),
                pollutants=PollutantReading(
                    pm25=row.get("pm25"), pm10=row.get("pm10"),
                    no2=row.get("no2"),  co=row.get("co"),
                    so2=row.get("so2"),  o3=row.get("o3"),
                    aqi=aqi or None,
                    aqi_category=get_aqi_category(aqi)["label"] if aqi else "Unknown",
                ),
                data_quality=0.95, source=DataSource.CSV_UPLOAD,
            ))
        return readings, DataSource.CSV_UPLOAD

    # =========================================================================
    # POLLUTANT ENRICHMENT — fill missing concentrations from Open-Meteo
    # =========================================================================

    def _enrich_readings_with_pollutants(
        self, locations: List[LocationReading], city: str
    ) -> List[LocationReading]:
        """
        Add real pollutant concentrations from Open-Meteo to every reading.

        WAQI provides AQI values (which match the website) but its iaqi values
        are AQI sub-indices, NOT concentrations. We therefore ALWAYS fetch
        concentrations from Open-Meteo (which gives real µg/m³ values) and
        keep the original WAQI AQI unchanged.
        """
        enriched = []
        open_meteo_cache: Dict[str, Dict] = {}  # "lat,lon" → pollutants

        # Fetch city-level pollutants once (all nearby stations share)
        city_coords = geocode_city(city)
        city_om: Dict = {}
        if city_coords:
            cache_key = f"{round(city_coords[0], 2)},{round(city_coords[1], 2)}"
            try:
                city_om = self._fetch_open_meteo_pollutants(city_coords[0], city_coords[1]) or {}
                open_meteo_cache[cache_key] = city_om
                logger.info(f"Open-Meteo city pollutants for {city}: {city_om}")
            except Exception as e:
                logger.warning(f"Open-Meteo city fetch failed for {city}: {e}")

        for loc in locations:
            p = loc.pollutants

            # Check if this reading already has real concentrations
            # (e.g. from Open-Meteo direct source or OpenWeather)
            has_real_concentrations = (
                loc.source in (DataSource.SCRAPING, DataSource.OPENWEATHER)
                and any([p.pm25, p.pm10, p.no2, p.so2, p.o3, p.co])
            )

            if has_real_concentrations:
                enriched.append(loc)
                continue

            # Use station-specific Open-Meteo if coordinates differ from city
            cache_key = f"{round(loc.lat, 2)},{round(loc.lon, 2)}"
            if cache_key not in open_meteo_cache:
                try:
                    om_data = self._fetch_open_meteo_pollutants(loc.lat, loc.lon)
                    open_meteo_cache[cache_key] = om_data or {}
                except Exception:
                    open_meteo_cache[cache_key] = city_om  # fall back to city-level

            om = open_meteo_cache[cache_key] or city_om

            if om:
                loc = LocationReading(
                    station_name=loc.station_name, city=loc.city,
                    lat=loc.lat, lon=loc.lon, timestamp=loc.timestamp,
                    pollutants=PollutantReading(
                        pm25=om.get("pm25"), pm10=om.get("pm10"),
                        no2=om.get("no2"), so2=om.get("so2"),
                        co=om.get("co"), o3=om.get("o3"),
                        aqi=p.aqi,   # <-- KEEP original WAQI AQI (matches website)
                        aqi_category=p.aqi_category,
                    ),
                    data_quality=0.82,
                    source=loc.source,
                )

            enriched.append(loc)

        n_enriched = sum(1 for loc in enriched
                         if any([loc.pollutants.pm25, loc.pollutants.pm10,
                                 loc.pollutants.no2, loc.pollutants.so2]))
        logger.info(f"Pollutant enrichment: {n_enriched}/{len(enriched)} readings now have concentrations")

        return enriched

    def _fetch_open_meteo_pollutants(self, lat: float, lon: float) -> Optional[Dict[str, float]]:
        """
        Fetch current pollutant concentrations from Open-Meteo Air Quality API.
        Returns dict with pm25, pm10, no2, so2, o3, co in µg/m³.
        """
        url = (
            "https://air-quality-api.open-meteo.com/v1/air-quality"
            f"?latitude={lat:.4f}&longitude={lon:.4f}"
            "&hourly=pm2_5,pm10,nitrogen_dioxide,ozone,sulphur_dioxide,carbon_monoxide"
            "&timezone=Asia/Kolkata&forecast_days=1&past_days=0"
        )
        resp = self._http().get(url, timeout=10)
        resp.raise_for_status()
        hourly = resp.json().get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            return None

        # Get the most recent non-null reading
        pm25s = hourly.get("pm2_5", [])
        best = next((i for i in range(len(times)-1, -1, -1)
                      if i < len(pm25s) and pm25s[i] is not None), None)
        if best is None:
            return None

        def _safe(series, idx):
            try:
                v = series[idx] if idx < len(series) else None
                return round(float(v), 2) if v is not None else None
            except (TypeError, ValueError):
                return None

        co_raw = _safe(hourly.get("carbon_monoxide", []), best)
        return {
            "pm25": _safe(pm25s, best),
            "pm10": _safe(hourly.get("pm10", []), best),
            "no2":  _safe(hourly.get("nitrogen_dioxide", []), best),
            "so2":  _safe(hourly.get("sulphur_dioxide", []), best),
            "o3":   _safe(hourly.get("ozone", []), best),
            "co":   round(co_raw / 1000, 4) if co_raw else None,  # Open-Meteo gives µg/m³, convert to mg/m³
        }

    # =========================================================================
    # Persistence
    # =========================================================================

    def _persist_readings(self, locations):
        records = []
        for r in locations:
            p  = r.pollutants
            ts = r.timestamp
            if ts and ts.tzinfo:
                ts = ts.replace(tzinfo=None)
            records.append({
                "station_name": r.station_name, "city": r.city,
                "timestamp": ts or datetime.utcnow(),
                "pm25": p.pm25, "pm10": p.pm10, "no2": p.no2,
                "co": p.co, "so2": p.so2, "o3": p.o3, "nh3": p.nh3,
                "aqi": p.aqi,
                "aqi_category": p.aqi_category.value if hasattr(p.aqi_category,"value") else str(p.aqi_category),
                "source": r.source.value, "data_quality": r.data_quality,
            })
        try:
            db.save_readings(records)
            if locations:
                db.upsert_station(locations[0].station_name, locations[0].city,
                                  locations[0].lat, locations[0].lon, locations[0].source.value)
        except Exception as e:
            logger.warning(f"DB persist: {e}")

    def _index_summaries(self, locations, city):
        for r in locations[:6]:
            p = r.pollutants
            cat = p.aqi_category.value if hasattr(p.aqi_category,"value") else str(p.aqi_category)
            summary = (
                f"{r.station_name} in {city}: AQI {p.aqi:.0f} ({cat}). "
                + (f"PM2.5={p.pm25:.1f}µg/m³ " if p.pm25 else "")
                + (f"NO2={p.no2:.1f}µg/m³" if p.no2 else "")
            )
            try:
                vector_store.add_aqi_summary(
                    city=city, station=r.station_name,
                    aqi=p.aqi or 0, summary=summary,
                    timestamp=r.timestamp.isoformat() if r.timestamp else "",
                )
            except Exception:
                pass
