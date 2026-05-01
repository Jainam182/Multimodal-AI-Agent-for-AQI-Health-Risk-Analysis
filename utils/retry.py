"""
utils/retry.py – Retry decorator using tenacity for robust API calls.
"""

# ─── Imports ──────────────────────────────────────────────────────────────────
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log,
)
import logging
import requests

std_logger = logging.getLogger("tenacity")

# ─── Retry policies (one per call type, all use exponential backoff) ──────────
# Standard API retry: 3 attempts, exponential backoff 1–10s
api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((requests.RequestException, TimeoutError, ConnectionError)),
    before_sleep=before_sleep_log(std_logger, logging.WARNING),
    reraise=True,
)

# Aggressive retry for scraping
scrape_retry = retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=2, min=2, max=15),
    reraise=True,
)

# LLM retry
llm_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
