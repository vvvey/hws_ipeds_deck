"""Data access layer: a DuckDB database built at runtime from the parquet extract.

The repo ships `data/parquet/<table>.parquet` (a slim cut of the IPEDS tables
the deck queries). On first use the tables are loaded into
`data/ipeds_deck.duckdb`; later sessions open that file read-only. If the
data folder is not writable (or the build is interrupted) the app falls back to
an in-memory database built from the same parquet files, so a viewer never
sees a missing-database error.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

from config import IPEDS_DB_PATH, PARQUET_DIR

# Full-time-series completions total (column renamed twice across years)
COMPLETIONS_TOTAL = "COALESCE(ctotalt, crace24, crace15 + crace16)"

MANIFEST = PARQUET_DIR / "manifest.json"


def _tables() -> list[str]:
    """Table names from the manifest, else every parquet file in the folder."""
    if MANIFEST.exists():
        return list(json.loads(MANIFEST.read_text()).keys())
    return sorted(p.stem for p in PARQUET_DIR.glob("*.parquet"))


def _load_tables(con: duckdb.DuckDBPyConnection) -> None:
    for name in _tables():
        path = PARQUET_DIR / f"{name}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"missing extract for table `{name}`: {path}")
        con.execute(
            f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_parquet(?)",
            [str(path)],
        )


def _is_complete(path: Path) -> bool:
    """A database counts as built only if every manifest table is present."""
    try:
        con = duckdb.connect(str(path), read_only=True)
        try:
            have = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        finally:
            con.close()
    except duckdb.Error:
        return False
    return set(_tables()) <= have


def build_database(path: Path = IPEDS_DB_PATH, *, force: bool = False) -> Path:
    """Build the DuckDB file from the parquet extract. Returns the path.

    The build goes to a temp file in the same folder and is renamed into place
    at the end, so a half-written database is never picked up by another
    session, and a crash mid-build leaves the previous file untouched.
    """
    path = Path(path)
    if path.exists() and not force and _is_complete(path):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".build-", suffix=".duckdb", dir=path.parent)
    os.close(fd)
    os.unlink(tmp)                     # DuckDB wants to create the file itself
    try:
        con = duckdb.connect(tmp)
        try:
            _load_tables(con)
        finally:
            con.close()
        os.replace(tmp, path)
    except BaseException:
        for leftover in (tmp, tmp + ".wal"):
            if os.path.exists(leftover):
                os.unlink(leftover)
        raise
    return path


@st.cache_resource(show_spinner="Building the IPEDS database…")
def get_connection() -> duckdb.DuckDBPyConnection:
    if not PARQUET_DIR.exists():
        st.error(
            f"IPEDS extract not found at `{PARQUET_DIR}`. "
            "The repo should ship `data/parquet/*.parquet`."
        )
        st.stop()
    try:
        build_database()
        return duckdb.connect(str(IPEDS_DB_PATH), read_only=True)
    except (OSError, duckdb.Error) as e:
        # Read-only or flaky disk: serve the same data from memory instead.
        st.toast(f"Using an in-memory database ({type(e).__name__}).", icon="ℹ️")
        con = duckdb.connect(":memory:")
        _load_tables(con)
        return con


@st.cache_data(ttl=3600, show_spinner="Querying IPEDS…")
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a parameterized SQL query against the IPEDS database."""
    con = get_connection()
    try:
        return con.execute(sql, params).df()
    except duckdb.Error as e:
        st.error(f"Query failed: {e}")
        st.stop()


@st.cache_data(ttl=3600)
def search_institutions(name_fragment: str) -> pd.DataFrame:
    """Find institutions by name (latest directory year per unitid)."""
    return query(
        """
        SELECT unitid, institution_name, state
        FROM hd
        QUALIFY ROW_NUMBER() OVER (PARTITION BY unitid ORDER BY year DESC) = 1
        AND institution_name ILIKE '%' || ? || '%'
        ORDER BY institution_name
        """,
        (name_fragment,),
    )
