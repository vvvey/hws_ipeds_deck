"""HWS IPEDS deck — Streamlit entry point.

Run locally with:
    streamlit run streamlit_app.py

The DuckDB database is built from data/parquet/ on first launch (see
core/data.py); nothing needs to be downloaded.
"""
from __future__ import annotations

import streamlit as st

from config import APP_TITLE
from core import theme
from dashboards import deck

st.set_page_config(page_title=APP_TITLE, page_icon="🎓", layout="wide")
theme.register_template()

deck.render()
