"""
settings.py — Environment and global configuration for the AI Daily Briefing system.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_ROOT = PROJECT_ROOT / "output"
DB_PATH = OUTPUT_ROOT / "briefing.db"
CACHE_DIR = OUTPUT_ROOT / ".cache"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

# ---------------------------------------------------------------------------
# Pipeline settings
# ---------------------------------------------------------------------------
INGEST_WINDOW_HOURS = int(os.environ.get("INGEST_WINDOW_HOURS", "48"))
MAX_ARTICLES_TO_CLASSIFY = int(os.environ.get("MAX_ARTICLES_TO_CLASSIFY", "60"))
TOP_ARTICLES_PER_AUDIENCE = int(os.environ.get("TOP_ARTICLES_PER_AUDIENCE", "12"))
MAX_CONCURRENT_LLM = int(os.environ.get("MAX_CONCURRENT_LLM", "5"))

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
HAIKU_MODEL = os.environ.get("HAIKU_MODEL", "claude-haiku-4-5")
SONNET_MODEL = os.environ.get("SONNET_MODEL", "claude-sonnet-4-6")
LLM_MAX_RETRIES = 3
LLM_RETRY_BACKOFF = 2.0

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
SERVER_HOST = os.environ.get("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "8000"))
