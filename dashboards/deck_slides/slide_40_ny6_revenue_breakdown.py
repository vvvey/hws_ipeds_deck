"""Revenue breakdown for the NY6, measured against the cost base.

Differs from the Finance page's revenue composition in two deliberate ways:

1. **The denominator is total expenses (f2b02), not total revenue.** A revenue
   share of revenue always sums to 100%, so it can only show mix. Dividing by
   expenses instead keeps a market-insensitive denominator, so the stack height
   itself is the answer to "does this revenue base cover what the college
   spends?" — the same framing as `slide_30_tuition_coverage`, widened from
   tuition alone to every source.
2. **Stacked areas over a continuous year axis**, so the eleven-year shape of
   each college's revenue base reads as one movement rather than eleven
   separate readings — the expense reference then tracks as a line against the
   top of the band.

The slide draws its own body (`render`) rather than returning a figure, because
the $ / % / per-student control is a Streamlit widget.
"""
from __future__ import annotations

import math

import pandas as pd

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from config import HWS_UNITID
from core.data import query
from core.theme import CATEGORICAL, SURFACE, TEXT_PRIMARY, TEXT_SECONDARY
from ._shared import NY6, fy
from .slide_00_profile import (CARNEGIE_BASIC, CONTROL, PEER_YEAR,
                               SIZE_CATEGORY)

# The window opens at the first year IPEDS collected the endowment draw
# (f2h03c, FY2019-20). Starting earlier would show a band that simply does not
# exist before 2020 and make the stack look like it grew when only the reporting
# changed.
FIRST_YEAR = 2020

TITLE = "NY6 - Where the money comes from"
SUBTITLE = ("Revenue by source for the New York Six, stacked against each college's total expense spaning from June 2019 to May 2024. Investment Return Designated for Operations only part of the total return from endowments investment.")

# Declared rather than left to the deck's default, which describes the *fall*
# enrollment pairing the other slides use. This slide takes its denominator from
# the 12-month instructional activity survey instead, and that file needs no
# year offset, so the shared caption would misstate how the years line up.
#
# Resolved through a module __getattr__ (PEP 562) rather than assigned as a
# constant, because the closing year is whatever the data currently reaches and
# only a query knows it. Hardcoding it would leave the caption quietly claiming
# the wrong survey year the first time IPEDS publishes another one. The deck
# reads SOURCE only after `render` has succeeded, so the frame is already cached
# by the time this runs.
def _source() -> str:
    df = _load()
    latest = fy(int(df["year"].max())) if not df.empty else "the latest year"
    return (
        f"Source: IPEDS Finance survey (F2, private nonprofit / FASB) and "
        f"12-month Instructional Activity survey (EF-IA), FY{fy(FIRST_YEAR)} to "
        f"FY{latest}. Both cover the same July-June fiscal year, so no year "
        f"offset is applied."
    )


def __getattr__(name: str):
    if name == "SOURCE":
        return _source()
    raise AttributeError(name)

# --- Revenue groups ---------------------------------------------------------
# Declaration order IS the stack order (bottom to top) and the color slot each
# group takes from CATEGORICAL. Student-priced revenue at the bottom, then the
# endowment draw, then solicited money, then the residual — so the stack reads
# from most to least operationally controllable.
#
# f2h03c is the endowment draw into operations (the audited statement's
# "investment return designated for current operations"); it is stored negative,
# so it is flipped below.
REVENUE_GROUPS = {
    "Net Tuition & Fees": ["f2d01"],
    "Sales and Services of Auxiliary Enterprises": ["f2d12", "f2d11"],
    "Investment Return Designated for Operations": ["f2h03c"],
    "Private Gifts & Grants (Restricted + Unrestricted)": ["f2d08"],
    "Government Grants & Appropriations": [
        "f2d02", "f2d03", "f2d04", "f2d05", "f2d06", "f2d07",
    ],
    # Educational sales & services (f2d11) sits here rather than with auxiliary:
    # the slide names auxiliary specifically, and at these colleges f2d11 is
    # either zero or ~1% of revenue.
    "Other Revenue": ["f2d09", "f2d13", "f2d14", "f2d15"],
}
COLOR = {name: CATEGORICAL[i] for i, name in enumerate(REVENUE_GROUPS)}
# Fill texture cycles over the bands the way Plotly Express's
# pattern_shape_sequence does — six groups over three shapes, so the repeat
# lands two slots apart and never puts the same texture on adjacent bands.
PATTERN_SHAPE_SEQUENCE = [".", "x", "+"]
PATTERN = {name: PATTERN_SHAPE_SEQUENCE[i % len(PATTERN_SHAPE_SEQUENCE)]
           for i, name in enumerate(REVENUE_GROUPS)}
SOURCE_COLS = sorted({c for cols in REVENUE_GROUPS.values() for c in cols})

FACET_COLS = 3
# Figure geometry. Height is chrome (top and bottom margin, title band) plus the
# rows themselves, so the row allowance is named rather than folded into a
# literal — changing it moves the whole grid coherently.
FACET_ROW_H = 290        # per-row allowance in the facet figure
FACET_CHROME = 150       # title band + legend room the rows do not use
FACET_MARGIN_T, FACET_MARGIN_B = 70, 90


def _facet_geometry(n_panels: int):
    """(rows, cols, vertical_spacing) for a facet grid of `n_panels`."""
    cols = max(1, min(FACET_COLS, n_panels))
    rows = math.ceil(n_panels / cols)
    # Row gap has to clear the upper row's tilted tick labels *and* the lower
    # row's facet title, so it runs wider than it did with flat labels.
    v_space = min(0.21, 0.9 / (rows - 1)) if rows > 1 else 0.15
    return rows, cols, v_space

# --- Views ------------------------------------------------------------------
# The unit the stack is measured in. Code branches on these keys; the glyph is
# only what the segmented control paints on the button, so a label change never
# touches the logic. Declaration order is the order of the control.
VIEW_DOLLARS = "dollars"
VIEW_PERCENT = "percent"
VIEW_PER_STUDENT = "per_student"
VIEW_LABELS = {
    VIEW_DOLLARS: "$",
    VIEW_PERCENT: "%",
    VIEW_PER_STUDENT: "🎓",
}


@st.cache_data(ttl=3600)
def _load_raw():
    """Raw IPEDS columns only — no group labels, so the cache survives a rename.

    Everything here is keyed by IPEDS variable name (f2d01, fteug, ...). The
    display names in REVENUE_GROUPS are applied in `_load` below, outside the
    cache: Streamlit keys `cache_data` on the function's own code, not on the
    module globals it reads, so a cached frame built under an older set of group
    labels would otherwise be handed back with stale column names and fail the
    lookup in `_apply_view`.
    """
    ids = ", ".join(str(u) for u in NY6)
    selects = "".join(f", CAST(f.{c} AS DOUBLE) AS {c}" for c in SOURCE_COLS)
    df = query(
        f"""
        SELECT f.unitid, f.year,
               CAST(f.f2b02 AS DOUBLE) AS expenses,
               -- Reported FTE (institution's own figure) preferred over the
               -- credit-hour estimate; graduate FTE is NULL rather than 0 at
               -- the colleges with no graduate program, so it is coalesced.
               COALESCE(CAST(a.fteug AS DOUBLE), CAST(a.efteug AS DOUBLE))
                 + COALESCE(CAST(a.ftegd AS DOUBLE), CAST(a.eftegd AS DOUBLE), 0)
                 AS fte{selects}
        FROM f2 f
        -- No year offset here, unlike the fall file. The 12-month instructional
        -- activity survey is labeled by the same fiscal-year END as the finance
        -- file (EFIA2024 = Jul 2023-Jun 2024 = F2324), so the enrollment and the
        -- dollars already cover the identical period.
        LEFT JOIN efia a
          ON f.unitid = a.unitid AND a.year = f.year
        WHERE f.unitid IN ({ids}) AND f.year >= ?
        ORDER BY f.year, f.unitid
        """,
        (FIRST_YEAR,),
    )
    return df.dropna(subset=["expenses"])


# --- Cohort aggregates ------------------------------------------------------
# The two roll-ups drawn under the facets. The peer universe is the deck's own,
# defined once in slide_00_profile and reused here the way slide_05 reuses it,
# so "peers" means the same 139 colleges everywhere in the deck. All six NY6
# members fall inside that universe, so they are excluded from the peer cohort —
# otherwise the consortium would be counted on both sides of the comparison.
#
# The peer cohort rides in the facet grid as a seventh panel, so the market the
# six colleges sit in is read in the same glance as the colleges themselves. The
# NY6 cohort total is still computed here — other slides import it — but is not
# drawn: a consortium total beside its own six members would repeat them.
COHORT_NY6 = "ny6"
COHORT_PEERS = "peers"
COHORT_LABELS = {
    COHORT_NY6: "New York Six (6 colleges)",
    COHORT_PEERS: "National peer set (133 colleges)",
}


@st.cache_data(ttl=3600)
def _load_cohorts_raw():
    """Per-year totals for each cohort, summed across institutions.

    Aggregated in SQL rather than in pandas because the peer cohort is 133
    colleges wide and only the yearly totals are ever drawn. Keyed by IPEDS
    variable name for the same reason as `_load_raw` — no display label enters
    the cache.
    """
    ny6_ids = ", ".join(str(u) for u in NY6)
    sums = "".join(f", SUM(CAST(f.{c} AS DOUBLE)) AS {c}" for c in SOURCE_COLS
                   if c != "f2h03c")
    df = query(
        f"""
        WITH peer_universe AS (
            SELECT unitid FROM hd
            WHERE year = ? AND carnegie_basic = ? AND control = ?
              AND size_category = ?
        ),
        cohorts AS (
            SELECT unitid, '{COHORT_NY6}' AS cohort FROM peer_universe
            WHERE unitid IN ({ny6_ids})
            UNION ALL
            SELECT unitid, '{COHORT_PEERS}' AS cohort FROM peer_universe
            WHERE unitid NOT IN ({ny6_ids})
        )
        SELECT c.cohort, f.year,
               COUNT(DISTINCT f.unitid) AS n_institutions,
               SUM(CAST(f.f2b02 AS DOUBLE)) AS expenses,
               -- ABS inside the SUM, not outside: the draw is stored negative
               -- per institution, and flipping the sign only after summing
               -- would be wrong the moment one college reported it positive.
               SUM(ABS(CAST(f.f2h03c AS DOUBLE))) AS f2h03c,
               SUM(COALESCE(CAST(a.fteug AS DOUBLE), CAST(a.efteug AS DOUBLE))
                   + COALESCE(CAST(a.ftegd AS DOUBLE),
                              CAST(a.eftegd AS DOUBLE), 0)) AS fte{sums}
        FROM f2 f
        JOIN cohorts c ON c.unitid = f.unitid
        LEFT JOIN efia a ON a.unitid = f.unitid AND a.year = f.year
        WHERE f.year >= ?
        GROUP BY c.cohort, f.year
        ORDER BY f.year
        """,
        (PEER_YEAR, CARNEGIE_BASIC, CONTROL, SIZE_CATEGORY, FIRST_YEAR),
    )
    return df.dropna(subset=["expenses"])


def _load_cohorts():
    """Cohort totals with the group columns applied (labels outside the cache)."""
    df = _load_cohorts_raw().copy()
    for group, members in REVENUE_GROUPS.items():
        df[group] = df[members].sum(axis=1, min_count=1).fillna(0)
    return df


def _load():
    """The cached frame, with institution names and the group columns applied."""
    df = _load_raw().copy()
    df["Institution"] = df["unitid"].map(NY6)
    # The draw is reported as a negative (money leaving the endowment); as a
    # revenue contribution it is positive. Pre-2020 years are simply unreported.
    df["f2h03c"] = df["f2h03c"].abs()
    for group, members in REVENUE_GROUPS.items():
        df[group] = df[members].sum(axis=1, min_count=1).fillna(0)
    return df


def _load_with_peers():
    """The six colleges plus the peer roll-up, in one facet-ready frame.

    The cohort is given an `Institution` of its display label so `_build` treats
    it as one more facet — no special case in the drawing code, and the peer
    panel inherits the colleges' stack order, colors and hover for free.
    """
    colleges = _load()
    peers = _load_cohorts()
    peers = peers[peers["cohort"] == COHORT_PEERS].copy()
    peers["Institution"] = COHORT_LABELS[COHORT_PEERS]
    shared = ["Institution", "year", "expenses", "fte", *REVENUE_GROUPS]
    return pd.concat([colleges[shared], peers[shared]], ignore_index=True)


def facet_order():
    """Facet order: the consortium in its usual order, then the market."""
    return [*NY6.values(), COHORT_LABELS[COHORT_PEERS]]


def factoids():
    """HWS in the latest fiscal year, every figure against total expenses."""
    df = _load()
    latest = int(df["year"].max())
    row = df[(df["year"] == latest) & (df["Institution"] == NY6[HWS_UNITID])]
    if row.empty:
        return []
    r = row.iloc[0]
    share = {g: r[g] / r["expenses"] for g in REVENUE_GROUPS}
    covered = sum(share.values())
    # Where the peer group sits, so the HWS numbers have something to lean on.
    peers = df[df["year"] == latest]
    peer_cov = (peers[list(REVENUE_GROUPS)].sum(axis=1) / peers["expenses"]).median()
    return [
        ("Revenue / expenses", f"{covered:.0%}",
         f"HWS operating revenue as a share of total expenses, {fy(latest)}. "
         f"NY6 median: {peer_cov:.0%}."),
        ("Tuition & fees", f"{share['Net Tuition & Fees']:.0%}",
         "Share of total expenses covered by net tuition & fees."),
        ("Endowment draw",
         f"{share['Investment Return Designated for Operations']:.0%}",
         "Spending distribution out of the endowment, as a share of expenses."),
        ("Gifts & grants", f"{share['Private Gifts & Grants (Restricted + Unrestricted)']:.0%}",
         "Private gifts, grants & contracts, as a share of expenses."),
    ]


# Ticks carry the full fiscal-year label (2024 -> "2023-24"). The five-year
# window leaves room for it; the abbreviated ‘YY form was only needed when the
# axis had to fit eleven years into a third of the page.



def _fmt_dollars(v: float) -> str:
    a = abs(v)
    if a >= 1e9:
        return f"${v / 1e9:.1f}B"
    if a >= 1e6:
        return f"${v / 1e6:.0f}M"
    if a >= 1e3:
        return f"${v / 1e3:.0f}K"
    return f"${v:,.0f}"


def _dollar_ticks(vmax: float, n: int = 4):
    """Evenly spaced round tick values from 0 to ~vmax, with $B/M/K labels."""
    if not vmax or vmax <= 0:
        return None, None
    raw = vmax / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if raw <= m * mag)
    vals, v = [], 0.0
    while v <= vmax * 1.0001:
        vals.append(v)
        v += step
    return vals, [_fmt_dollars(v) for v in vals]


# view token -> (scale factor column or None, y title, hover, reference label)
def _apply_view(df, view: str):
    """Scale every revenue group and the expense reference into the chosen unit.

    Returns (frame, y_title, hover_suffix, is_dollars). The percentage view
    divides by *total expenses*, not by the stack — so the bar top is coverage of
    the cost base and legitimately lands above or below 100%.
    """
    d = df.copy()
    if view == VIEW_PERCENT:
        denom = d["expenses"]
        for group in REVENUE_GROUPS:
            d[group] = d[group] / denom * 100
        d["Reference"] = 100.0
        return d, "% of total expenses", "%{y:.1f}%", False
    if view == VIEW_PER_STUDENT:
        d = d.dropna(subset=["fte"])
        d = d[d["fte"] > 0]
        for group in REVENUE_GROUPS:
            d[group] = d[group] / d["fte"]
        d["Reference"] = d["expenses"] / d["fte"]
        return d, "$ per FTE student", "$%{y:,.0f}", True
    for group in REVENUE_GROUPS:
        d[group] = d[group]
    d["Reference"] = d["expenses"]
    return d, "USD", "$%{y:,.0f}", True


def _build(df, view: str, names=None, own_dollar_axis=()):
    """Small multiples: one stacked-area facet per college, sharing one y-scale.

    `names` sets which institutions appear and in what order, so the same
    builder draws the consortium and any other selection of colleges. It
    defaults to the NY6 in consortium order.

    `own_dollar_axis` names facets that get their own y-axis in the \$ view
    instead of the shared one. That is for roll-up panels: a cohort total is two
    orders of magnitude larger than any single college, and on a shared dollar
    axis every college would flatten to a strip at the baseline. The ratio views
    are already size-normalized and always share one scale.
    """
    d, y_title, hover, is_dollars = _apply_view(df, view)
    present = set(d["Institution"])
    names = [n for n in (names or NY6.values()) if n in present]
    years = sorted(int(y) for y in d["year"].unique())

    rows, cols, v_space = _facet_geometry(len(names))
    # Column gap runs wide on purpose: each facet carries its own y tick values
    # now, and adjacent stacked areas that nearly touch read as one continuous
    # band across the page rather than as six separate colleges.
    h_space = min(0.12, 0.9 / (cols - 1)) if cols > 1 else 0.0

    fig = make_subplots(rows=rows, cols=cols, subplot_titles=names,
                        horizontal_spacing=h_space, vertical_spacing=v_space)

    panel_maxes = []
    for i, name in enumerate(names):
        row, col = i // cols + 1, i % cols + 1
        g = d[d["Institution"] == name].set_index("year").reindex(years)

        for group in REVENUE_GROUPS:
            fig.add_trace(
                go.Scatter(
                    x=years, y=g[group].values, name=group, legendgroup=group,
                    showlegend=(i == 0), mode="lines",
                    # No separator stroke: bands meet edge to edge, so the stack
                    # reads as one mass. Hue plus fill texture separates them.
                    line=dict(width=0),
                    fillcolor=COLOR[group],
                    # bgcolor must repeat the band color: Plotly defaults a
                    # pattern's background to *transparent*, not to fillcolor,
                    # so without it a patterned band renders as bare hatching on
                    # an empty panel. The hatch is the surface color at low
                    # opacity, so it reads as texture over the band rather than
                    # as a second color competing with the palette.
                    fillpattern=dict(shape=PATTERN[group], bgcolor=COLOR[group],
                                     fgcolor=SURFACE, fgopacity=0.35,
                                     size=7, solidity=0.25),
                    stackgroup=f"facet{i}",
                    hovertemplate=f"%{{fullData.name}}: {hover}<extra></extra>",
                ),
                row=row, col=col,
            )

        # The comparison the slide is built on: total expenses, drawn over the
        # stack so the gap between the band top and the reference is the
        # operating shortfall (or surplus) at a glance. Kept out of every
        # stackgroup so it reads as an absolute line, not another slab.
        ref = g["Reference"]
        # In the per-student view every band is a quotient, so the divisor
        # belongs in the readout — otherwise a number that moved because
        # enrollment shrank looks identical to one that moved because revenue
        # grew. It rides on the expense trace because that entry appears exactly
        # once in the x-unified box, where repeating it per band would be noise.
        ref_hover = f"<b>Total expenses: {hover}</b>"
        customdata = None
        if view == VIEW_PER_STUDENT:
            customdata = g["fte"].values
            ref_hover += "<br>FTE Enrollment: %{customdata:,.0f} 🎓"
        fig.add_trace(
            go.Scatter(
                x=years, y=ref.values, name="Total expenses (operation + nonoperation)", legendgroup="expenses",
                showlegend=(i == 0), mode="lines",
                line=dict(width=2, dash="dot", color=TEXT_SECONDARY),
                customdata=customdata,
                hovertemplate=f"{ref_hover}<extra></extra>",
            ),
            row=row, col=col,
        )
        stack_top = g[list(REVENUE_GROUPS)].sum(axis=1)
        panel_maxes.append(max(float(stack_top.max()), float(ref.max())))

        # Set inside the tuition band (the bottom slab): anchored at the middle
        # year, halfway up the band, in data coordinates so it sits within the
        # area in every view.
        if name == "Colgate":
            yr = years[len(years) // 2]
            fig.add_annotation(
                x=yr, y=float(g.loc[yr, "Net Tuition & Fees"]) / 2,
                text="Colgate inflated net tuition & fee<br>"
                     "with room and board revenue",
                showarrow=False, font=dict(size=11, color="white"),
                bgcolor="rgba(0,0,0,0.45)", borderpad=4,
                row=row, col=col,
            )

    # Axis ink is the primary text color here, not the template's secondary
    # gray: on a presented slide the tick values are read from a distance and
    # have to carry as much as the chart itself.
    ink = dict(color=TEXT_PRIMARY)
    fig.update_xaxes(showgrid=False, tickmode="array", tickvals=years,
                     ticktext=[fy(y) for y in years], tickangle=-45,
                     tickfont=dict(color=TEXT_PRIMARY, size=12),
                     title=dict(font=ink))
    if is_dollars:
        # The colleges share one dollar scale, so a taller band means more money
        # rather than a different axis; anything in `own_dollar_axis` is scaled
        # to itself. Per student the range is narrower than raw dollars, so four
        # intervals would leave the facets nearly gridless — eight gives a step
        # to measure a band against.
        own = {i for i, n in enumerate(names)
               if view == VIEW_DOLLARS and n in set(own_dollar_axis)}
        shared = [m for i, m in enumerate(panel_maxes) if i not in own]
        n_ticks = 8 if view == VIEW_PER_STUDENT else 4
        if shared:
            shared_max = max(shared)
            vals, text = _dollar_ticks(shared_max, n=n_ticks)
            for i in range(len(names)):
                if i not in own:
                    fig.update_yaxes(range=[0, shared_max * 1.05],
                                     tickmode="array", tickvals=vals,
                                     ticktext=text,
                                     row=i // cols + 1, col=i % cols + 1)
        for i in own:
            pmax = panel_maxes[i]
            vals, text = _dollar_ticks(pmax, n=n_ticks)
            fig.update_yaxes(range=[0, pmax * 1.05], tickmode="array",
                             tickvals=vals, ticktext=text,
                             row=i // cols + 1, col=i % cols + 1)
    else:
        # Quarter steps: 0/25/50/75/100 are the reference points the eye already
        # holds for a share, and the 100% line is where the expense reference
        # sits — a 20-step axis would leave that line between gridlines.
        top = max(125, math.ceil(max(panel_maxes) / 25) * 25)
        pct = list(range(0, int(top) + 1, 25))
        # Label text is written out rather than left to `ticksuffix`: with
        # tickmode="array" the suffix is not reliably applied to every facet's
        # axis, and every tick has to carry its unit on a presented slide.
        fig.update_yaxes(range=[0, top], tickmode="array", tickvals=pct,
                         ticktext=[f"{v}%" for v in pct])
    # The template draws outside ticks at the default 5px length, which pushes
    # the values a visible step off the plot edge. Shortening the tick marks and
    # zeroing the label standoff seats the numbers against the area chart.
    fig.update_yaxes(tickfont=dict(color=TEXT_PRIMARY, size=12),
                     ticklen=2, ticklabelstandoff=0,
                     title=dict(font=ink))
    for r in range(1, rows + 1):
        fig.update_yaxes(title_text=y_title, row=r, col=1)
    # Facet titles are annotations, so they take their color there rather than
    # from the axis settings above. The selector spares annotations that set
    # their own color (the Colgate in-band note).
    fig.update_annotations(font=dict(color=TEXT_PRIMARY),
                           selector=lambda a: a.font.color is None)

    fig.update_layout(
        height=rows * FACET_ROW_H + FACET_CHROME,
        hovermode="x unified",
        # Legend runs down the left gutter, vertically centered against the
        # grid. `traceorder="reversed"` makes the list read top-down in the same
        # order the bands stack top-down (expense line, then Other, ... down to
        # Tuition), which a horizontal strip could not show — and it frees the
        # band across the top for the facet titles.
        legend=dict(orientation="v", title_text="",
                    yref="container", yanchor="middle", y=0.5,
                    xref="container", xanchor="left", x=0.005,
                    traceorder="reversed"),
        # Left margin holds the legend (widest entry: "Government Grants &
        # Appropriations") plus the y-axis title and ticks. Bottom margin clears
        # the -45-degree tick labels, which stand ~35px tall rather than the
        # ~15px a horizontal label needs.
        margin=dict(l=250, r=30, t=FACET_MARGIN_T, b=FACET_MARGIN_B),
    )
    return fig


# One selection, however many controls draw it. Streamlit will not let two
# widgets share a key, so the chosen view lives under a key of its own and each
# control mirrors into it on change. VIEW_STATE is the single source of truth
# the charts read. Only one control is on the slide today; the indirection is
# what let a second one exist without the two drifting apart.
VIEW_STATE = "deck_rev_breakdown_view"
VIEW_WIDGET_KEYS = ("deck_rev_breakdown_view_top",)


def _sync_view(src_key: str) -> None:
    """Copy one control's pick into the shared state and any sibling control.

    Runs as an `on_change` callback, i.e. before the rerun instantiates either
    widget — the one window in which assigning to another widget's key is
    allowed. `or` guards the deselect case: segmented_control returns None when
    the active button is clicked again, and the slide has no "no view" state.
    """
    chosen = st.session_state.get(src_key) or st.session_state.get(VIEW_STATE) \
        or VIEW_DOLLARS
    st.session_state[VIEW_STATE] = chosen
    for key in VIEW_WIDGET_KEYS:
        if key != src_key:
            st.session_state[key] = chosen


def _view_control(key: str) -> str:
    """One segmented control bound to the shared view state.

    The widget carries the view *keys*; `format_func` is the only place the
    glyphs appear, so relabeling a button never reaches the branching below.
    `default` is passed only on the first run — once the key exists in session
    state, passing it as well makes Streamlit warn about a value set twice.
    """
    current = st.session_state.get(VIEW_STATE, VIEW_DOLLARS)
    kwargs = {} if key in st.session_state else {"default": current}
    st.segmented_control(
        "View - revenue breakdown",
        options=list(VIEW_LABELS),
        format_func=VIEW_LABELS.get,
        key=key,
        on_change=_sync_view,
        args=(key,),
        label_visibility="collapsed",
        **kwargs,
    )
    return st.session_state.get(VIEW_STATE, VIEW_DOLLARS)


def render() -> None:
    view = _view_control(VIEW_WIDGET_KEYS[0])

    df = _load_with_peers()
    if df.empty:
        st.warning("No F2 finance data found for the New York Six.")
        return

    # The peer panel is the only facet scaled to itself in the $ view; see
    # `_build` for why a shared dollar axis would flatten the six colleges.
    peer_label = COHORT_LABELS[COHORT_PEERS]
    st.plotly_chart(
        _build(df, view, names=facet_order(), own_dollar_axis=(peer_label,)),
        use_container_width=True, key="deck_rev_breakdown_fig")

    _render_lookup(view)


# --- Single-college lookup --------------------------------------------------
# The same chart, drawn for any one private nonprofit the viewer picks. It sits
# under the consortium grid so a question raised there ("how does this compare
# with X?") can be answered on the same slide without leaving the deck.
#
# The option list is every institution that files the FASB finance form (F2)
# in the window, not the whole directory: the stack is built from F2 columns,
# so a public (GASB, F1A) or for-profit (F3) college would only ever produce
# an empty panel.
LOOKUP_KEY = "deck_rev_breakdown_lookup"


@st.cache_data(ttl=3600)
def _lookup_options() -> pd.DataFrame:
    """unitid, label ("Name (ST)") for every F2 filer in the window."""
    return query(
        """
        SELECT h.unitid,
               h.institution_name || ' (' || h.state || ')' AS label
        FROM hd h
        WHERE h.unitid IN (
            SELECT DISTINCT unitid FROM f2
            WHERE year >= ? AND f2b02 IS NOT NULL
        )
        QUALIFY ROW_NUMBER() OVER (PARTITION BY h.unitid ORDER BY h.year DESC) = 1
        ORDER BY h.institution_name
        """,
        (FIRST_YEAR,),
    )


@st.cache_data(ttl=3600)
def _load_one_raw(unitid: int) -> pd.DataFrame:
    """Raw F2 + FTE rows for one institution; same shape as `_load_raw`."""
    selects = "".join(f", CAST(f.{c} AS DOUBLE) AS {c}" for c in SOURCE_COLS)
    df = query(
        f"""
        SELECT f.unitid, f.year,
               CAST(f.f2b02 AS DOUBLE) AS expenses,
               COALESCE(CAST(a.fteug AS DOUBLE), CAST(a.efteug AS DOUBLE))
                 + COALESCE(CAST(a.ftegd AS DOUBLE), CAST(a.eftegd AS DOUBLE), 0)
                 AS fte{selects}
        FROM f2 f
        LEFT JOIN efia a ON f.unitid = a.unitid AND a.year = f.year
        WHERE f.unitid = ? AND f.year >= ?
        ORDER BY f.year
        """,
        (int(unitid), FIRST_YEAR),
    )
    return df.dropna(subset=["expenses"])


def _load_one(unitid: int, label: str) -> pd.DataFrame:
    """One institution with group columns applied (labels outside the cache)."""
    df = _load_one_raw(unitid).copy()
    df["Institution"] = label
    df["f2h03c"] = df["f2h03c"].abs()
    for group, members in REVENUE_GROUPS.items():
        df[group] = df[members].sum(axis=1, min_count=1).fillna(0)
    return df


def _render_lookup(view: str) -> None:
    """Search box plus a one-panel version of the chart for the pick."""
    st.markdown("#### Look up any college")
    opts = _lookup_options()
    if opts.empty:
        st.info("No F2 filers found to search.")
        return
    labels = opts["label"].tolist()
    ids = dict(zip(labels, opts["unitid"]))
    # No default: the panel only appears once a college is chosen, so the
    # consortium grid above stays the slide's single subject until then.
    pick = st.selectbox(
        "Search a private nonprofit college by name",
        options=labels, index=None,
        placeholder="Type to search, e.g. Vassar, Skidmore, Hamilton ...",
        key=LOOKUP_KEY,
    )
    if not pick:
        return

    df = _load_one(int(ids[pick]), pick)
    if df.empty:
        st.info(f"{pick} has no F2 finance data from FY{fy(FIRST_YEAR)} on.")
        return
    if view == VIEW_PER_STUDENT and not (df["fte"].fillna(0) > 0).any():
        st.info(f"{pick} reports no FTE enrollment, so the per-student view "
                "is empty. Switch to $ or % above.")
        return

    st.plotly_chart(
        _build(df, view, names=[pick]),
        use_container_width=True, key="deck_rev_breakdown_lookup_fig")
