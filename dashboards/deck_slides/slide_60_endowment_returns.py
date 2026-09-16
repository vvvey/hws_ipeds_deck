"""Five-year endowment return, NY6 against the peer set.

The annual return rate is IPEDS Part H:

    r = f2h03b / (f2h01 + f2h03a)

net investment return over beginning-of-year value plus the year's new gifts.
Adding gifts to the denominator treats money that arrived during the year as
capital at risk, which is the conservative reading; dividing by f2h01 alone runs
about a quarter-point higher across this set.

The five years are then chain-linked, not averaged:

    annualized = [ (1+r1)(1+r2)(1+r3)(1+r4)(1+r5) ] ** (1/5) - 1

Averaging the annual rates overstates the result whenever they vary, because a
loss has to compound against a gain rather than cancel half of it. The gap is
not academic here: HWS averages 8.67% and compounds to 7.39%, the widest spread
in the consortium, because it had both the highest year (+39.9%) and the
steepest (-12.9%).

This is a dollar-weighted approximation, not a time-weighted return. IPEDS
reports annual totals, not cash-flow dates, so a college will differ from its
NACUBO-style published figure. It is comparable across colleges here because
every college is computed the same way.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import HWS_UNITID
from core.data import query
from core.theme import (BRAND, NEUTRAL_MARK_STRONG, SURFACE, TEXT_PRIMARY,
                        TEXT_SECONDARY)
from ._shared import NY6, fy
from .slide_00_profile import (CARNEGIE_BASIC, CONTROL, PEER_YEAR,
                               SIZE_CATEGORY)

FIRST_YEAR = 2020
LAST_YEAR = PEER_YEAR
N_YEARS = LAST_YEAR - FIRST_YEAR + 1

TITLE = "Five-year endowment return"
SUBTITLE = (f"Annualized net investment return, FY{fy(FIRST_YEAR)} to "
            f"FY{fy(LAST_YEAR)}, against the median of the national peer set.")

SOURCE = (
    f"Source: IPEDS Finance survey (F2, private nonprofit / FASB) Part H, "
    f"FY{fy(FIRST_YEAR)} to FY{fy(LAST_YEAR)}: annual return is net investment "
    f"return (f2h03b) over beginning-of-year value (f2h01) plus new gifts and "
    f"additions (f2h03a), chain-linked across the five years and annualized. "
    f"Peer filter from the IPEDS Directory (HD) {PEER_YEAR}."
)

CAVEAT = (
    "Dollar-weighted, not time-weighted: IPEDS reports annual totals rather "
    "than cash-flow dates, so these will not match a college's published "
    "NACUBO return exactly. Every college here is computed identically, so the "
    "comparison holds even where the absolute level is approximate. The peer "
    "median includes the six New York colleges."
)

HWS_COLOR = BRAND["green"]
NY6_COLOR = BRAND["orange"]
PEER_COLOR = NEUTRAL_MARK_STRONG   # dark neutral: a reference, not a competitor


def _load():
    """Per-college annual return rate, one row per college-year."""
    return query(
        """
        WITH peer_universe AS (
            SELECT unitid FROM hd
            WHERE year = ? AND carnegie_basic = ? AND control = ?
              AND size_category = ?
        )
        SELECT f.unitid, f.year,
               CAST(f.f2h03b AS DOUBLE)
                 / (CAST(f.f2h01 AS DOUBLE) + CAST(f.f2h03a AS DOUBLE))
                 AS r
        FROM f2 f
        JOIN peer_universe p ON p.unitid = f.unitid
        WHERE f.year BETWEEN ? AND ?
          -- A zero or negative base is not a rate. Nothing in this window trips
          -- it, but a bad denominator would otherwise compound into nonsense.
          AND CAST(f.f2h01 AS DOUBLE) + CAST(f.f2h03a AS DOUBLE) > 0
          AND f.f2h03b IS NOT NULL
        """,
        (PEER_YEAR, CARNEGIE_BASIC, CONTROL, SIZE_CATEGORY,
         FIRST_YEAR, LAST_YEAR),
    )


def _annualized():
    """Chain-linked annualized return per college, over the full window.

    Colleges missing a year are dropped rather than annualized over a shorter
    span: a four-year compound presented beside five-year ones would be a
    different measure wearing the same axis.
    """
    df = _load()
    complete = df.groupby("unitid")["r"].count().eq(N_YEARS)
    df = df[df["unitid"].isin(complete[complete].index)]
    growth = df.assign(f=1 + df["r"]).groupby("unitid")["f"].prod()
    return (growth ** (1 / N_YEARS) - 1) * 100


# The window's endpoints as calendar dates rather than fiscal-year labels: a
# balance is a moment, not a period. FY2019-20 opens in July 2019 and FY2023-24
# closes in June 2024, so both headers derive from the year constants and cannot
# drift when the window moves.
OPENING_COL = f"July {FIRST_YEAR - 1} Endowment"
CLOSING_COL = f"June {LAST_YEAR} Endowment"


def _leaderboard():
    """The whole peer set by five-year return, best first.

    Every college rather than a top slice: the table is the audit trail behind
    the bar chart, and a reader who wants to know where a particular college
    landed can sort or scroll to it. Rank is the position in this ordering, so
    it survives re-sorting the table on any other column.
    """
    ann = _annualized().sort_values(ascending=False)
    meta = query(
        """
        SELECT h.unitid, h.institution_name, h.state,
               CAST(f.f2h02 AS DOUBLE) AS endowment
        FROM hd h
        LEFT JOIN f2 f ON f.unitid = h.unitid AND f.year = h.year
        WHERE h.year = ?
        """,
        (PEER_YEAR,),
    ).set_index("unitid")

    # Five-year totals of the three Part H flows behind the return. Summed over
    # the same window the return is compounded over, so the dollar columns and
    # the percentage columns describe one period.
    #
    # f2h03c keeps its reported sign: it is money leaving the endowment, and a
    # negative reads as an outflow at a glance. The revenue breakdown slide
    # flips it because there it is stacked as a revenue contribution.
    flows = query(
        """
        SELECT unitid,
               -- Opening balance: f2h01 is the value at the START of a fiscal
               -- year, so the first year in the window carries the July figure
               -- the table's other columns are measured from.
               SUM(CASE WHEN year = ? THEN CAST(f2h01 AS DOUBLE) END)
                 AS opening,
               SUM(CAST(f2h03b AS DOUBLE)) AS investment_return,
               SUM(CAST(f2h03a AS DOUBLE)) AS new_gifts,
               SUM(CAST(f2h03c AS DOUBLE)) AS spending
        FROM f2
        WHERE year BETWEEN ? AND ?
        GROUP BY unitid
        """,
        (FIRST_YEAR, FIRST_YEAR, LAST_YEAR),
    ).set_index("unitid")

    rows = []
    for i, u in enumerate(ann.index):
        # Percentages are carried as 11.24, not 0.1124, and dollars as millions:
        # `column_config` formats a number, it does not rescale one, so the
        # column has to arrive in the units the format string claims.
        rows.append({
            "Rank": i + 1,
            "College": meta.at[u, "institution_name"],
            "State": meta.at[u, "state"],
            # Cumulative is derived from the annualized figure rather than
            # re-multiplied, so the two columns can never disagree by a rounding
            # step in front of an audience.
            # Key order is column order. It runs as the balance actually moves:
            # opening, what was added, what was earned, what was spent, closing
            # — so the row reads left to right as the five-year arithmetic.
            "5-yr annualized": ann[u],
            OPENING_COL: flows.at[u, "opening"] / 1e6,
            "New Endowment": flows.at[u, "new_gifts"] / 1e6,
            "Investment return": flows.at[u, "investment_return"] / 1e6,
            "Spending draw": flows.at[u, "spending"] / 1e6,
            CLOSING_COL: meta.at[u, "endowment"] / 1e6,
        })
    return pd.DataFrame(rows)


def build():
    ann = _annualized()
    peer_median = ann.median()

    # Ascending, so the strongest college lands at the top of a horizontal axis.
    ny6 = ann[ann.index.isin(NY6)].sort_values()
    names = [NY6[u] for u in ny6.index]
    colors = [HWS_COLOR if u == HWS_UNITID else NY6_COLOR for u in ny6.index]

    fig = go.Figure(go.Bar(
        x=ny6.values, y=names, orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"{v:.2f}%" for v in ny6.values],
        textposition="outside", textfont=dict(size=13, color=TEXT_PRIMARY),
        cliponaxis=False,   # keep the end labels from being trimmed at the edge
        showlegend=False,
        hovertemplate="<b>%{y}</b><br>5-year annualized: %{x:.2f}%<extra></extra>",
    ))

    # One reference line, not a bar: the peer figure is a backdrop for the six,
    # not a seventh college. The median carries it alone — the mean sat a
    # quarter-point away and needed its own dash pattern and label to be told
    # apart, which is a lot of ink for a distinction nobody reads off a slide.
    fig.add_vline(
        x=peer_median, line=dict(color=PEER_COLOR, width=2, dash="dot"),
        annotation_text=f"Peer median {peer_median:.2f}%",
        annotation_position="top",
        annotation_font=dict(size=12, color=PEER_COLOR),
    )

    fig.update_xaxes(
        title_text=f"Annualized return, FY{fy(FIRST_YEAR)} to FY{fy(LAST_YEAR)}",
        ticksuffix="%", rangemode="tozero",
        tickfont=dict(color=TEXT_PRIMARY, size=13),
        title=dict(font=dict(color=TEXT_PRIMARY)),
    )
    fig.update_yaxes(showgrid=False, ticklen=2, ticklabelstandoff=0,
                     tickfont=dict(color=TEXT_PRIMARY, size=14))
    fig.update_layout(
        height=440, bargap=0.35, hovermode="closest",
        plot_bgcolor=SURFACE,
        margin=dict(l=210, r=70, t=70, b=60),
    )
    # add_annotation, not `annotations=` in update_layout: the reference lines
    # above registered their labels as annotations too, and assigning the list
    # wholesale would drop them.
    fig.add_annotation(
        text=(f"Peer set: {len(ann)} colleges · "
              f"HWS ranks {int((ann > ann.loc[HWS_UNITID]).sum()) + 1} "
              f"of {len(ann)}"),
        x=1, y=-0.22, xref="paper", yref="paper",
        xanchor="right", showarrow=False,
        font=dict(size=12, color=TEXT_SECONDARY),
    )
    return fig


def render() -> None:
    """Chart then leaderboard. `render` rather than `build` because the table is
    a Streamlit element, not a figure."""
    st.plotly_chart(build(), use_container_width=True,
                    key="deck_endow_returns_fig")

    df = _leaderboard()
    st.subheader(f"All {len(df)} colleges in the peer set")
    st.dataframe(
        # Fixed height so the table scrolls in place instead of running the
        # slide to several screens; every column stays sortable, so a reader
        # can reorder by endowment or draw without leaving the slide.
        df, hide_index=True, use_container_width=True, height=460,
        column_config={
            "Rank": st.column_config.NumberColumn(width="small"),
            "State": st.column_config.TextColumn(width="small"),
            "5-yr annualized": st.column_config.NumberColumn(format="%.2f%%"),
            # `,` groups thousands (sprintf-js), so the billion-dollar rows read
            # "$3,550M" rather than "$3550M". The column stays numeric, which
            # keeps the dataframe's own column sorting meaningful.
            OPENING_COL: st.column_config.NumberColumn(
                help=f"Endowment assets at the start of FY{fy(FIRST_YEAR)} "
                     f"(f2h01)", format="$%,.0fM"),
            CLOSING_COL: st.column_config.NumberColumn(
                help=f"Endowment assets at the end of FY{fy(LAST_YEAR)} "
                     f"(f2h02)", format="$%,.0fM"),
            "Investment return": st.column_config.NumberColumn(
                help=f"Net investment return (f2h03b), summed "
                     f"FY{fy(FIRST_YEAR)} to FY{fy(LAST_YEAR)}",
                format="$%,.0fM"),
            "New Endowment": st.column_config.NumberColumn(
                help=f"New gifts and additions to the endowment (f2h03a), "
                     f"summed FY{fy(FIRST_YEAR)} to FY{fy(LAST_YEAR)}",
                format="$%,.0fM"),
            "Spending draw": st.column_config.NumberColumn(
                help=f"Spending distribution for current use (f2h03c), summed "
                     f"FY{fy(FIRST_YEAR)} to FY{fy(LAST_YEAR)}. Negative: "
                     f"money leaving the endowment.",
                format="$%,.0fM"),
        },
    )
    st.caption(
        "Rank is by five-year annualized return; every column is sortable. "
        "Dollar columns are five-year totals over the same window the return "
        "compounds across, and the spending draw keeps its reported negative "
        "sign as money leaving the endowment. Return is dollar-weighted, so a "
        "college with a large mid-year inflow can read higher than its "
        "published time-weighted figure — an effect that moves a small "
        "endowment much more than a large one."
    )
