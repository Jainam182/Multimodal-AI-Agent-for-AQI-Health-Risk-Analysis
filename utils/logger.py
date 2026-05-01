"""
utils/logger.py – Centralized logging configuration using loguru.
"""

# ─── Imports ──────────────────────────────────────────────────────────────────
import sys
from loguru import logger as _logger
from config import LOG_LEVEL

# ─── Sink configuration ───────────────────────────────────────────────────────
# Remove default handler so we control formatting/destinations explicitly.
_logger.remove()

# Console handler – coloured and structured
_logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> – <level>{message}</level>",
    level=LOG_LEVEL,
    colorize=True,
)

# File handler – full detail, rotated daily
_logger.add(
    "logs/aqi_system_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} – {message}",
    level="DEBUG",
    rotation="00:00",
    retention="7 days",
    compression="zip",
    enqueue=True,
)

logger = _logger


# ─── Public factory ───────────────────────────────────────────────────────────
def get_logger(name: str):
    """Return a bound logger with component name context."""
    return _logger.bind(name=name)
