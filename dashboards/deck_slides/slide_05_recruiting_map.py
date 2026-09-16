"""Where each peer college recruits - click a marker to switch schools.

Two layers on one `scope="usa"` map:
  * a state choropleth of where the selected college's first-year students came
    from, summed across ten years;
  * the same peer-college markers as slide 00, which double as the selector.

This slide defines `render()` rather than `build()` because the chart is an input
widget: `st.plotly_chart(on_select="rerun")` hands back the clicked point, and the
slide has to read that back to know which college to shade.
"""
from __future__ import annotations

import json

import plotly.graph_objects as go
import streamlit as st

from config import DICTIONARIES_DIR, HWS_UNITID
from core.data import query
from core.theme import (CATEGORICAL, GRID, NEUTRAL_MARK_STRONG, SEQUENTIAL,
                        SURFACE, TEXT_SECONDARY)
from ._shared import NY6
# The peer universe is defined once, on slide 00 - imported rather than copied so
# the two maps can never drift apart.
from .slide_00_profile import (CARNEGIE_BASIC, CONTROL, PEER_YEAR,
                               SIZE_CATEGORY, _peers)

SELECTED_KEY = "deck_recruit_unitid"

# ef_c has full coverage only in even years - every peer reports in 2016/18/20/22/24,
# but only ~75 of 139 in odd years. Summing a straight ten-year window would
# therefore credit odd-year reporters with extra cohorts. Even years only keeps
# every college on the same five-cohort footing.
YEARS = (2016, 2018, 2020, 2022, 2024)

# Aggregate rows in efcstate that are not states, and must be kept out of the map.
CODE_TOTAL = 99        # all first-time degree/certificate-seeking undergraduates
CODE_US_TOTAL = 58
CODE_FOREIGN = 90
NON_STATE_CODES = (CODE_TOTAL, CODE_US_TOTAL, CODE_FOREIGN, 57, 89, 98)

TITLE = "Every peer college recruits from a different map"
SUBTITLE = (f"First-year students by home state, summed over {YEARS[0]}-{YEARS[-1]} "
            "(even years). Click any marker to switch colleges.")
# TAKEAWAY = (
#     "HWS draws 970 of its 2,443 US-resident first-years from New York alone - 40% "
#     "- and 74% from just five Northeast states. Click a peer to see how narrow or "
#     "broad its own catchment is by comparison."
# )
SOURCE = (
    f"Source: IPEDS Residence & Migration (EF_C), {YEARS[0]}-{YEARS[-1]} even years; "
    f"IPEDS Directory (HD), {PEER_YEAR}. Peer filter: carnegie_basic = "
    f"{CARNEGIE_BASIC}, control = {CONTROL}, size_category = {SIZE_CATEGORY}."
)

SELECTED_COLOR = CATEGORICAL[2]   # HWS orange - reads against the green shading
PEER_COLOR = NEUTRAL_MARK_STRONG  # dark neutral: visible over shaded states

# The map and the top-states bar share a row (30/70), so they share a height.
MAP_HEIGHT = 620


@st.cache_data(ttl=3600)
def _state_lookup() -> dict[int, str]:
    """efcstate numeric code -> USPS abbreviation.

    Built by joining the two data dictionaries on state *name* (ef_c gives
    code -> name, hd gives USPS -> name) rather than hardcoding a FIPS table.
    """
    dic = DICTIONARIES_DIR
    efc = json.loads((dic / "ef_c.json").read_text())["variables"]["efcstate"]["codes"]
    hd = json.loads((dic / "hd.json").read_text())["variables"]["state"]["codes"]
    name_to_usps = {name: usps for usps, name in hd.items()}
    return {int(code): name_to_usps[name]
            for code, name in efc.items() if name in name_to_usps}


@st.cache_data(ttl=3600)
def _residence():
    """First-year counts by college and home-state code, summed over YEARS."""
    placeholders = ", ".join("?" for _ in YEARS)
    df = query(
        f"""
        WITH peers AS (
            SELECT unitid FROM hd
            WHERE year = ? AND carnegie_basic = ? AND control = ? AND size_category = ?
        )
        SELECT e.unitid,
               CAST(e.efcstate AS INTEGER) AS code,
               SUM(CAST(e.efres01 AS BIGINT)) AS students
        FROM ef_c e JOIN peers p ON e.unitid = p.unitid
        WHERE e.year IN ({placeholders})
        GROUP BY 1, 2
        """,
        (PEER_YEAR, CARNEGIE_BASIC, CONTROL, SIZE_CATEGORY, *YEARS),
    )
    df["usps"] = df["code"].map(_state_lookup())
    return df


TOP_N = 10


def _top_states_bar(states, us_total: int, height: int = MAP_HEIGHT):
    """Compact ranked bar of the biggest source states, labelled with counts.

    Height defaults to the map's so the two line up when they share a row; the
    narrow (30%) column leaves little room for the outside labels, hence the
    tight left margin and the wide right one.
    """
    top = states.nlargest(TOP_N, "students").sort_values("students")  # largest on top
    labels = [
        f"{r.students:,.0f}  ({r.students / us_total:.0%})" if us_total
        else f"{r.students:,.0f}"
        for r in top.itertuples()
    ]
    fig = go.Figure(go.Bar(
        x=top["students"], y=top["usps"], orientation="h",
        marker=dict(color=SEQUENTIAL[4], line=dict(width=2, color=SURFACE)),
        text=labels, textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{x:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        height=height/2, showlegend=False,
        margin=dict(l=36, r=36, t=10, b=10),
        xaxis=dict(visible=False,
                   range=[0, float(top["students"].max()) * 1.45]),
        yaxis=dict(tickfont=dict(size=14)),
        # Stretched to the map's height, five bars at the old 0.35 gap render as
        # heavy blocks; the wider gap keeps the marks thin.
        # bargap=0.62,
    )
    return fig


def _catchment(unitid: int):
    """Per-code totals for one college: (total_fn, state rows, US total, foreign)."""
    mine = _residence()
    mine = mine[mine["unitid"] == unitid]

    def total(code):
        row = mine[mine["code"] == code]["students"]
        return int(row.iloc[0]) if len(row) else 0

    states = mine[mine["usps"].notna()]
    return total, states, total(CODE_US_TOTAL), total(CODE_FOREIGN)


def factoids():
    """KPI tiles for whichever college is currently selected on the map."""
    unitid = _selected_unitid(_peers())
    total, states, us_total, foreign = _catchment(unitid)
    top = states.nlargest(TOP_N, "students")
    concentration = f"{top['students'].sum() / us_total:.0%}" if us_total else "-"
    return [
        ("First-years, all sources", f"{total(CODE_TOTAL):,}"),
        ("States represented", f"{len(states)}"),
        (f"Top {TOP_N} states", concentration,
         f"Share of US-resident first-years from the {TOP_N} largest states."),
        ("From abroad", f"{foreign:,}"),
    ]


def _selected_unitid(peers) -> int:
    ids = set(peers["unitid"])
    current = st.session_state.get(SELECTED_KEY, HWS_UNITID)
    return current if current in ids else (HWS_UNITID if HWS_UNITID in ids
                                           else int(peers["unitid"].iloc[0]))


def build(unitid: int | None = None):
    """Choropleth of one college's catchment, with peer markers on top."""
    peers = _peers()
    res = _residence()
    if unitid is None:
        unitid = _selected_unitid(peers)

    mine = res[res["unitid"] == unitid]
    states = mine[mine["usps"].notna()]

    fig = go.Figure()
    fig.add_trace(go.Choropleth(
        locations=states["usps"], z=states["students"],
        locationmode="USA-states",
        colorscale=[[i / (len(SEQUENTIAL) - 1), c] for i, c in enumerate(SEQUENTIAL)],
        marker_line_color=SURFACE, marker_line_width=0.6,
        colorbar=dict(title=dict(text="First-years", side="right"),
                      thickness=12, len=0.55, x=0.99, tickformat=","),
        hovertemplate="%{location}: %{z:,.0f}<extra></extra>",
        name="",
    ))

    # Markers double as the selector, so unitid rides along in customdata.
    for is_sel in (False, True):
        grp = peers[(peers["unitid"] == unitid) == is_sel]
        fig.add_trace(go.Scattergeo(
            lon=grp["longitude"], lat=grp["latitude"],
            mode="markers",
            name="Selected college" if is_sel else "Peer colleges (click to select)",
            customdata=grp[["unitid", "institution_name", "state"]],
            marker=dict(
                size=20 if is_sel else 7,
                color=SELECTED_COLOR if is_sel else PEER_COLOR,
                opacity=1 if is_sel else 0.75,
                line=dict(width=3 if is_sel else 1, color=SURFACE),
            ),
            hovertemplate="<b>%{customdata[1]}</b><br>%{customdata[2]}"
                          "<extra></extra>",
        ))

    fig.update_layout(
        height=MAP_HEIGHT,
        geo=dict(scope="usa", projection_type="albers usa",
                 showland=True, landcolor=SURFACE,
                 showlakes=True, lakecolor=SURFACE,
                 subunitcolor=GRID, subunitwidth=1,
                 countrycolor=GRID, coastlinecolor=GRID, bgcolor=SURFACE),
        legend=dict(orientation="h", yanchor="bottom", y=1.01,
                    xanchor="left", x=0, title_text=""),
        margin=dict(l=10, r=10, t=60, b=10),
        clickmode="event+select",
    )
    return fig


def render() -> None:
    peers = _peers().sort_values("institution_name")
    unitid = _selected_unitid(peers)
    name = peers.loc[peers["unitid"] == unitid, "institution_name"].iloc[0]
    _, states, us_total, _ = _catchment(unitid)

    # Ranked states beside the map, not under it: the bar is the answer to
    # "where from", the map is the shape of it.
    bar_col, map_col = st.columns([3, 7], gap="medium")

    with bar_col:
        if len(states):
            st.markdown(f"**Top {TOP_N} source states** - count (share of "
                        "US-resident first-years)")
            st.plotly_chart(_top_states_bar(states, us_total),
                            use_container_width=True, key="deck_recruit_top5")

    with map_col:
        event = st.plotly_chart(
            build(unitid), use_container_width=True, key="deck_recruit_map",
            on_select="rerun", selection_mode="points",
        )

    # Only marker traces carry customdata; a click on a shaded state has none, so
    # this ignores choropleth clicks instead of blowing up on them.
    for pt in (event.get("selection", {}) or {}).get("points", []):
        cd = pt.get("customdata")
        if cd and int(cd[0]) != unitid:
            st.session_state[SELECTED_KEY] = int(cd[0])
            st.rerun()

    # The KPI row is no longer drawn here — this slide declares factoids(), and
    # the deck driver renders them below the body like any other slide.
    st.caption(f"**{name}** · {YEARS[0]}-{YEARS[-1]}, even years only. "
               f"US-resident total {us_total:,}; state rows sum to "
               f"{int(states['students'].sum()):,} (the remainder is residence "
               "unknown or outlying areas).")
