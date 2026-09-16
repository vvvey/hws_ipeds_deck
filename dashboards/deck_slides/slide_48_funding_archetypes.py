"""Three ways to pay for a college, three colleges each.

The peer set contains institutions running on very different money. This slide
picks the extremes: the three most dependent on what students pay, the three
drawing hardest on endowment, and the three living most on gifts - ranked on the
latest filed year, then shown as full trends so a reader can see whether the
profile is a standing arrangement or a recent turn.

One row per archetype, so the grid reads down as "here is the same story three
times" and across as "here is how consistently it holds".

Bands, colors, patterns, view keys and the unit conversion are imported from
`slide_40_ny6_revenue_breakdown`; nothing about the stack is restated here.
"""
from __future__ import annotations

import math

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core.data import query
from core.theme import SURFACE, TEXT_PRIMARY, TEXT_SECONDARY
from ._shared import fy
from .slide_00_profile import (CARNEGIE_BASIC, CONTROL, PEER_YEAR,
                               SIZE_CATEGORY)
from .slide_40_ny6_revenue_breakdown import (COLOR, FIRST_YEAR, PATTERN,
                                             REVENUE_GROUPS, SOURCE_COLS,
                                             VIEW_DOLLARS, VIEW_LABELS,
                                             VIEW_PER_STUDENT, _apply_view,
                                             _dollar_ticks)

TITLE = "Three ways to fund a college"
SUBTITLE = ("The peer set's extremes: the colleges most dependent on student "
            "revenue, on the endowment draw, and on gifts, each measured "
            "against total expenses in the latest filed year.")

SOURCE = (
    "Source: IPEDS Finance survey (F2, private nonprofit / FASB) and 12-month "
    "Instructional Activity survey (EF-IA). Ranked within the national peer "
    "set (private not-for-profit baccalaureate arts & sciences colleges, "
    "1,000-4,999 students) from the IPEDS Directory (HD)."
)

CAVEAT = (
    "Ranking is on a single year, so a college can top a list on one unusual "
    "filing - a campaign gift, a one-time transfer - which is exactly why the "
    "trend is drawn behind it. Shares are of total expenses, not of revenue, "
    "so they do not sum to 100% and can exceed it: a gifts share above 100% "
    "means the year's gifts alone exceeded what the college spent."
)

TOP_N = 9
FACET_COLS = 3

# category key -> (row title, IPEDS columns summed, short label for the facet)
# Declared as IPEDS columns rather than REVENUE_GROUPS keys: those keys are
# display labels that have been renamed before, and a rename should not quietly
# redefine what "student revenue" means in a ranking.
ARCHETYPES = {
    "student": ("Student revenue", ["f2d01", "f2d12", "f2d11"], "tuition + auxiliary"),
    "endowment": ("Endowment spending", ["f2h03c"], "endowment draw"),
    "gifts": ("Private gifts", ["f2d08"], "gifts & grants"),
}

VIEW_STATE = "deck_archetypes_view"


@st.cache_data(ttl=3600)
def _load_raw():
    """Every peer college's revenue series. Labels applied outside the cache."""
    selects = "".join(f", CAST(f.{c} AS DOUBLE) AS {c}" for c in SOURCE_COLS)
    return query(
        f"""
        WITH peer_universe AS (
            SELECT unitid FROM hd
            WHERE year = ? AND carnegie_basic = ? AND control = ?
              AND size_category = ?
        )
        SELECT f.unitid, f.year, h.institution_name,
               CAST(f.f2b02 AS DOUBLE) AS expenses,
               COALESCE(CAST(a.fteug AS DOUBLE), CAST(a.efteug AS DOUBLE))
                 + COALESCE(CAST(a.ftegd AS DOUBLE), CAST(a.eftegd AS DOUBLE), 0)
                 AS fte{selects}
        FROM f2 f
        JOIN peer_universe p ON p.unitid = f.unitid
        LEFT JOIN efia a ON a.unitid = f.unitid AND a.year = f.year
        LEFT JOIN hd h ON h.unitid = f.unitid AND h.year = f.year
        WHERE f.year >= ? AND f.f2b02 > 0
        ORDER BY f.year
        """,
        (PEER_YEAR, CARNEGIE_BASIC, CONTROL, SIZE_CATEGORY, FIRST_YEAR),
    )


def _load():
    """Peer revenue with the group columns and Institution name applied."""
    df = _load_raw().copy()
    df["Institution"] = df["institution_name"]
    df["f2h03c"] = df["f2h03c"].abs()
    for group, members in REVENUE_GROUPS.items():
        df[group] = df[members].sum(axis=1, min_count=1).fillna(0)
    return df


def _picks(df):
    """Top `TOP_N` colleges per archetype in the latest year.

    Returns {archetype key: [(facet title, institution name)]} plus the year
    ranked on. Archetypes are ranked independently, so a college strong on two
    measures appears in both blocks - that is a finding about the college, not
    a duplicate to be removed.
    """
    latest = int(df["year"].max())
    year = df[df["year"] == latest]
    out = {}
    for key, (row_title, cols, short) in ARCHETYPES.items():
        # abs() because the endowment draw is stored negative at source; every
        # other column here is already positive.
        share = year[cols].abs().sum(axis=1) / year["expenses"] * 100
        picks = []
        for idx, pct in share.nlargest(TOP_N).items():
            name = year.at[idx, "Institution"]
            picks.append((f"{name}<br><sub>{pct:.0f}% of expenses "
                          f"({short})</sub>", name))
        out[key] = picks
    return out, latest


def _build(df, view: str, picks):
    """One archetype's block: `TOP_N` colleges on a FACET_COLS-wide grid."""
    titles = [t for t, _ in picks]
    names = [n for _, n in picks]

    d, y_title, hover, is_dollars = _apply_view(df, view)
    years = sorted(int(y) for y in d["year"].unique())
    cols = FACET_COLS
    rows = math.ceil(len(names) / cols)

    fig = make_subplots(rows=rows, cols=cols, subplot_titles=titles,
                        horizontal_spacing=0.09, vertical_spacing=0.16)

    panel_maxes = []
    for i, name in enumerate(names):
        row, col = i // cols + 1, i % cols + 1
        g = d[d["Institution"] == name].set_index("year").reindex(years)
        for group in REVENUE_GROUPS:
            fig.add_trace(
                go.Scatter(
                    x=years, y=g[group].values, name=group, legendgroup=group,
                    showlegend=(i == 0), mode="lines", line=dict(width=0),
                    fillcolor=COLOR[group],
                    fillpattern=dict(shape=PATTERN[group], bgcolor=COLOR[group],
                                     fgcolor=SURFACE, fgopacity=0.35,
                                     size=7, solidity=0.25),
                    stackgroup=f"panel{i}",
                    hovertemplate=f"%{{fullData.name}}: {hover}<extra></extra>",
                ),
                row=row, col=col,
            )

        ref = g["Reference"]
        ref_hover = f"<b>Total expenses: {hover}</b>"
        customdata = None
        if view == VIEW_PER_STUDENT:
            customdata = g["fte"].values
            ref_hover += "<br>FTE enrollment: %{customdata:,.0f}"
        fig.add_trace(
            go.Scatter(
                x=years, y=ref.values, name="Total expenses",
                legendgroup="expenses", showlegend=(i == 0), mode="lines",
                line=dict(width=2, dash="dot", color=TEXT_SECONDARY),
                customdata=customdata,
                hovertemplate=f"{ref_hover}<extra></extra>",
            ),
            row=row, col=col,
        )
        panel_maxes.append(max(float(g[list(REVENUE_GROUPS)].sum(axis=1).max()),
                               float(ref.max())))

    ink = dict(color=TEXT_PRIMARY)
    fig.update_xaxes(showgrid=False, tickmode="array", tickvals=years,
                     ticktext=[fy(y) for y in years], tickangle=-45,
                     tickfont=dict(color=TEXT_PRIMARY, size=11),
                     title=dict(font=ink))
    if view == VIEW_DOLLARS:
        # These nine range from small colleges to large ones, so raw dollars get
        # a per-panel scale; the point of the grid is each college's mix, not
        # which of them is biggest.
        for i, pmax in enumerate(panel_maxes):
            vals, text = _dollar_ticks(pmax)
            fig.update_yaxes(range=[0, pmax * 1.05], tickmode="array",
                             tickvals=vals, ticktext=text,
                             row=i // cols + 1, col=i % cols + 1)
    elif is_dollars:
        shared_max = max(panel_maxes)
        vals, text = _dollar_ticks(shared_max, n=8)
        fig.update_yaxes(range=[0, shared_max * 1.05], tickmode="array",
                         tickvals=vals, ticktext=text)
    else:
        top = max(125, math.ceil(max(panel_maxes) / 25) * 25)
        pct = list(range(0, int(top) + 1, 25))
        fig.update_yaxes(range=[0, top], tickmode="array", tickvals=pct,
                         ticktext=[f"{v}%" for v in pct])
    fig.update_yaxes(tickfont=dict(color=TEXT_PRIMARY, size=11),
                     ticklen=2, ticklabelstandoff=0, title=dict(font=ink))
    for r in range(1, rows + 1):
        fig.update_yaxes(title_text=y_title, row=r, col=1)
    # Facet titles are annotations, so their color is set here rather than on
    # the axes. Size is set too: the two-line title needs to stay under the
    # weight of the slide's own heading.
    fig.update_annotations(font=dict(color=TEXT_PRIMARY, size=13))
    fig.update_layout(
        height=rows * 300 + 150, hovermode="x unified",
        legend=dict(orientation="v", title_text="", yref="container",
                    yanchor="middle", y=0.5, xref="container",
                    xanchor="left", x=0.005, traceorder="reversed"),
        margin=dict(l=250, r=30, t=70, b=80),
    )
    return fig


def render() -> None:
    view = st.segmented_control(
        "View - funding archetypes",
        options=list(VIEW_LABELS), format_func=VIEW_LABELS.get,
        default=VIEW_DOLLARS, key=VIEW_STATE, label_visibility="collapsed",
    ) or VIEW_DOLLARS

    df = _load()
    if df.empty:
        st.warning("No F2 finance data found for the peer set.")
        return
    picks, latest = _picks(df)
    n_peers = df["unitid"].nunique()

    # One figure per archetype rather than a single 27-panel grid: nine columns
    # across would shrink each stack past reading, and three separate blocks let
    # a presenter stop at the end of one.
    for key, (row_title, cols, short) in ARCHETYPES.items():
        st.subheader(f"Top {TOP_N}: {row_title}")
        st.plotly_chart(_build(df, view, picks[key]),
                        use_container_width=True,
                        key=f"deck_archetypes_{key}_fig")
        st.caption(
            f"Ranked on {short} as a share of total expenses in FY{fy(latest)}, "
            f"within the {n_peers}-college peer set; each panel is that "
            f"college's full trend from FY{fy(FIRST_YEAR)}. IPEDS columns: "
            f"{', '.join(cols)} over f2b02. The dotted line is total expenses."
        )
