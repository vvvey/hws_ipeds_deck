"""Central configuration for the HWS IPEDS deck app."""
from __future__ import annotations

from pathlib import Path

# Repo root = the folder holding streamlit_app.py
REPO_ROOT = Path(__file__).resolve().parent
APP_DIR = REPO_ROOT

# Slim IPEDS extract shipped with the repo (zstd parquet, one file per table),
# and the DuckDB file that is built from it at runtime.
DATA_DIR = REPO_ROOT / "data"
PARQUET_DIR = DATA_DIR / "parquet"
DICTIONARIES_DIR = DATA_DIR / "dictionaries"
IPEDS_DB_PATH = DATA_DIR / "ipeds_deck.duckdb"

# Hobart and William Smith Colleges
HWS_UNITID = 191630

APP_TITLE = "HWS IPEDS Deck"
