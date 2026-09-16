# HWS IPEDS Deck

A self-contained Streamlit presentation deck about Hobart and William Smith
Colleges and its peer set, built on IPEDS data. Nine slides, one file each,
stepped with Prev / Next or the slide picker.

The repo ships its own data: a slim extract of the five IPEDS tables the deck
reads (`hd`, `ef_a`, `ef_c`, `efia`, `f2`, only the columns the slides use) as
zstd-compressed parquet under `data/parquet/`. The DuckDB database is built from
those files the first time the app starts, so nothing is downloaded and no
build step is required before deploying.

## Run locally

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

First launch builds `data/ipeds_deck.duckdb` (about 25 MB, ~2 s) and later
launches reuse it. The file is git-ignored. To pre-build or rebuild by hand:

```bash
python build_db.py            # build if missing or incomplete
python build_db.py --force    # rebuild from scratch
```

If the `data/` folder is not writable the app builds the same tables in memory
instead and keeps running.

## Deploy on Streamlit Community Cloud

1. Push this folder to a GitHub repository.
2. On https://share.streamlit.io choose **New app**, pick the repo and branch,
   and set the main file path to `streamlit_app.py`.
3. Deploy. Dependencies come from `requirements.txt`; the theme and font
   serving come from `.streamlit/config.toml`.

## Layout

| Path | Role |
|------|------|
| `streamlit_app.py` | Entry point: page config, Plotly template, renders the deck. |
| `config.py` | Paths (`PARQUET_DIR`, `IPEDS_DB_PATH`, `DICTIONARIES_DIR`) and `HWS_UNITID`. |
| `core/data.py` | Builds the DuckDB from parquet at runtime; `query(sql, params)` with caching. |
| `core/theme.py` | HWS brand palette and the Plotly template. |
| `dashboards/deck.py` | Deck driver: discovers slides, Prev/Next, error isolation. |
| `dashboards/deck_slides/` | One `slide_NN_name.py` per slide; `_shared.py` holds the contract and helpers. |
| `data/parquet/` | The IPEDS extract plus `manifest.json` (tables, columns, row counts). |
| `data/dictionaries/` | `hd.json` and `ef_c.json` code labels (state lookup for the recruiting map). |
| `static/` | Cera Pro / Cera Stencil Pro `.woff2` faces served via `server.enableStaticServing`. |
| `.streamlit/config.toml` | Brand theme, chart palettes, and the `[[theme.fontFaces]]` blocks. |

## Adding a slide

Drop `slide_<NN>_<name>.py` into `dashboards/deck_slides/` declaring `TITLE`
and either `build()` (returns a Plotly figure) or `render()` (draws its own
body). Optional: `SUBTITLE`, `TAKEAWAY`, `CAVEAT`, `SOURCE`. Slides are
discovered automatically and ordered by filename.

If a new slide needs a column or table that is not in `data/parquet/`, add it to
the extract from the full IPEDS database and update `manifest.json`.

## Refreshing the data

The extract was cut from the full `ipeds.duckdb` built by the `ipeds-database`
tool in the parent project. To refresh, re-export each table listed in
`data/parquet/manifest.json` with the same columns to parquet, then run
`python build_db.py --force`.

## Fonts

The `.woff2` files were converted from the desktop Cera Pro license. Serving
them makes them downloadable by every viewer of a public app. Confirm the HWS
Cera license covers web embedding before deploying publicly, or remove the
`[[theme.fontFaces]]` blocks and the `static/` folder to fall back to Helvetica.
