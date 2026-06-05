"""Central configuration. Reads from environment / .env file."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# --- Garmin ---
GARMIN_EMAIL = os.getenv("GARMIN_EMAIL", "")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD", "")
GARMIN_IS_CN = os.getenv("GARMIN_IS_CN", "false").lower() == "true"
# Directory where garth caches OAuth tokens so you don't log in every run.
GARMIN_TOKENSTORE = os.getenv("GARMIN_TOKENSTORE", str(BASE_DIR / ".garmin_tokens"))

# --- Storage ---
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "garmin.db"))
LOCAL_TIMEZONE = os.getenv("LOCAL_TIMEZONE", "Europe/Oslo")

# --- AI ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# Change to whatever model you have access to (e.g. claude-opus-4-8).
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# --- Personal baselines used by the analytics layer ---
SLEEP_NEED_HOURS = float(os.getenv("SLEEP_NEED_HOURS", "8.0"))
