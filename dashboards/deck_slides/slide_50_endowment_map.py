"""US map of the peer universe, sized by endowment.

Same geography as `slide_00_profile`, one variable added: marker area is the
end-of-year endowment. The map answers a different question than the profile
map does — not "where are the comparable colleges" but "where is the money among
them", which at this scale is the more useful reading, because the peer set is
defined by size and mission and says nothing about wealth.

Marker area rather than radius encodes the value (`sizemode="area"`). Endowments
here span nearly four hundred to one; on a radius scale the largest circle would
be twenty times the width of the smallest and swallow half of New England.
"""
from __future__ import annotations

import math

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from config import HWS_UNITID
from core.data import query
from core.theme import BRAND, GRID, NEUTRAL_MARK, SURFACE, TEXT_SECONDARY
from ._shared import NY6, fy
from .slide_00_profile import (CARNEGIE_BASIC, CONTROL, PEER_YEAR,
                               SIZE_CATEGORY, _peers)

TITLE = "Where the endowment money sits in the peer set"
SUBTITLE = ("139 private baccalaureate arts & sciences colleges, with "
            "each circle's area set by its end-of-year endowment end June 2024. Hover any "
            "circle for the institution and its value.")

SOURCE = (
    f"Source: IPEDS Finance FY{fy(PEER_YEAR)}; locations and "
    f"the peer filter from the IPEDS Directory (HD) {PEER_YEAR}."
)

CAVEAT = (
    "Endowment size is not endowment *available*: f2h02 is the market value of "
    "all endowment assets, most of it donor-restricted to a stated purpose. A "
    "college cannot spend the circle. What it can spend is the annual draw, "
    "which the revenue breakdown slide shows as its own band."
)

# HWS green and NY6 orange, both straight from the brand primaries; peers stay
# the recessive neutral so the two highlighted groups read first. This differs
# from slide_00, where HWS is purple — here green is the ask, and the peer gray
# is what the other 132 circles need to stay legible when they overlap.
HWS_COLOR = BRAND["green"]
NY6_COLOR = BRAND["orange"]
PEER_COLOR = NEUTRAL_MARK

# The largest endowment in the set draws at this diameter, in pixels; every
# other circle is scaled to it by area. Tuned so the biggest circle reads as one
# college rather than as a region, and the smallest is still clickable.
MAX_MARKER_PX = 54
MIN_MARKER_PX = 4

# --- Views ------------------------------------------------------------------
# Total endowment, or endowment per FTE student. Code branches on these keys and
# never on the glyph, so relabeling a button cannot reach the logic. The two
# views rank the set differently: total size is a proxy for institutional
# heft, per-student is what actually backs a given student's education.
VIEW_TOTAL = "total"
VIEW_PER_STUDENT = "per_student"
VIEW_LABELS = {VIEW_TOTAL: "$", VIEW_PER_STUDENT: "🎓"}
VIEW_STATE = "deck_endow_map_view"

# --- Trend selection --------------------------------------------------------
# Which colleges the trend panel below the map is showing. One multiselect is
# the only control; its key is the state.
TREND_SELECT_KEY = "deck_endow_trend_select"


def _load():
    """Peer universe with locations, end-of-year endowment and 12-month FTE."""
    df = _peers()
    endow = query(
        """
        SELECT f.unitid, CAST(f.f2h02 AS DOUBLE) AS endowment,
               -- Same FTE definition as the revenue breakdown slide: reported
               -- 12-month figures, credit-hour estimate as fallback, graduate
               -- coalesced to 0 where a college has no graduate program.
               COALESCE(CAST(a.fteug AS DOUBLE), CAST(a.efteug AS DOUBLE))
                 + COALESCE(CAST(a.ftegd AS DOUBLE), CAST(a.eftegd AS DOUBLE), 0)
                 AS fte
        FROM f2 f
        JOIN hd h ON h.unitid = f.unitid AND h.year = f.year
        LEFT JOIN efia a ON a.unitid = f.unitid AND a.year = f.year
        WHERE f.year = ? AND h.carnegie_basic = ? AND h.control = ?
          AND h.size_category = ?
        """,
        (PEER_YEAR, CARNEGIE_BASIC, CONTROL, SIZE_CATEGORY),
    )
    df = df.merge(endow, on="unitid", how="left")
    # A college with no reported endowment has nothing to size a circle by, and
    # a zero-area marker is a missing dot the reader cannot tell from an absent
    # college. Dropping it keeps the count in the footnote honest.
    df = df.dropna(subset=["endowment"])
    df["per_student"] = df["endowment"] / df["fte"].where(df["fte"] > 0)
    return df


@st.cache_data(ttl=3600)
def _load_trend():
    """End-of-year endowment (f2h02) for every peer, all years on record.

    The peer universe is fixed at PEER_YEAR — the same 139 colleges the map
    draws — but the trend runs over every year f2 holds for them, so the line
    starts wherever a college first reported (2003 for most of the set).
    """
    peers = _peers()
    ids = ", ".join(str(u) for u in peers["unitid"])
    df = query(
        f"""
        SELECT unitid, year, CAST(f2h02 AS DOUBLE) AS endowment
        FROM f2
        WHERE unitid IN ({ids}) AND f2h02 IS NOT NULL
        ORDER BY year
        """
    )
    return df.merge(peers[["unitid", "institution_name", "Group"]], on="unitid")


def _trend_fig(trend, names):
    """Endowment ending value over time for the chosen colleges.

    Line colors come from the app template's colorway (`core.theme.CATEGORICAL`)
    in selection order, so any mix of colleges stays distinguishable — with up
    to 139 possible picks, fixed per-college identity hues cannot exist. The
    peer median is the whole set's, drawn dashed in the recessive ink first, so
    it reads as context under the selected lines rather than a competitor.
    """
    median = trend.groupby("year")["endowment"].median()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=median.index, y=median.values, name="Peer median (139 colleges)",
        mode="lines", line=dict(width=2, dash="dot", color=TEXT_SECONDARY),
        hovertemplate="Peer median: %{y:$,.0f}<extra></extra>",
    ))
    ymax = float(median.max())
    for name in names:
        d = trend[trend["institution_name"] == name].sort_values("year")
        fig.add_trace(go.Scatter(
            x=d["year"], y=d["endowment"], name=name,
            mode="lines", line=dict(width=2.5),
            hovertemplate=f"<b>{name}</b>: %{{y:$,.0f}}<extra></extra>",
        ))
        ymax = max(ymax, float(d["endowment"].max()))

    years = sorted(int(y) for y in trend["year"].unique())
    tickvals, ticktext = _bar_ticks(ymax, _fmt)
    fig.update_xaxes(tickmode="array", tickvals=years,
                     ticktext=[fy(y) for y in years], tickangle=-45,
                     showgrid=False, tickfont=dict(size=11))
    fig.update_yaxes(title_text="Endowment, end of year",
                     tickmode="array", tickvals=tickvals, ticktext=ticktext,
                     tickfont=dict(size=11))
    fig.update_layout(
        height=340, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, title_text=""),
        margin=dict(l=70, r=10, t=30, b=70),
    )
    return fig


# view -> (value column, footnote/axis label, formatter)
def _measure(view: str):
    if view == VIEW_PER_STUDENT:
        return "per_student", "Endowment per FTE student", _fmt_per_student
    return "endowment", "Endowment", _fmt


def _fmt(v: float) -> str:
    return f"${v / 1e9:.2f}B" if v >= 1e9 else f"${v / 1e6:.0f}M"


def _fmt_per_student(v: float) -> str:
    return f"${v / 1e6:.2f}M" if v >= 1e6 else f"${v / 1e3:.0f}K"


def _trace(df, name, color, sizeref, ring, col, label):
    return go.Scattergeo(
        lon=df["longitude"], lat=df["latitude"],
        name=name, mode="markers",
        customdata=df[["institution_name", "state", col]],
        marker=dict(
            size=df[col], sizemode="area", sizeref=sizeref,
            sizemin=MIN_MARKER_PX, color=color, opacity=0.75,
            line=dict(width=ring, color=SURFACE),
        ),
        hovertemplate=("<b>%{customdata[0]}</b><br>%{customdata[1]}"
                       f"<br>{label}: %{{customdata[2]:$,.0f}}<extra></extra>"),
    )


def _rank_bars(df, col, label):
    """Every college as one bar, smallest at the bottom, largest at the top.

    The map shows where the money is; this shows how it is distributed, which a
    map cannot — in the total view the curve is flat across most of the set and
    then turns near vertical over the last fifteen colleges. One bar per college
    rather than a histogram so a named college can be found in it, and so the
    HWS and NY6 bars light up in the same colors they carry on the map.

    The sort is on whichever measure is in view, so switching to per-student
    reorders the whole column rather than leaving it ranked on totals.
    """
    d = df.sort_values(col)
    colors = [HWS_COLOR if g == "HWS" else NY6_COLOR if g == "NY6" else PEER_COLOR
              for g in d["Group"]]
    # 139 categories in a 30%-wide column leaves no room for 139 labels, so only
    # the highlighted colleges are named. The rest are deliberately anonymous:
    # the bar chart's job here is the shape of the distribution and where the
    # two highlighted groups fall inside it.
    named = d[d["Group"] != "Peer"]["institution_name"]
    bar = go.Bar(
        x=d[col], y=d["institution_name"], orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        showlegend=False,   # the map's traces already carry the color legend
        hovertemplate=f"<b>%{{y}}</b><br>{label}: %{{x:$,.0f}}<extra></extra>",
    )
    return bar, list(d["institution_name"]), list(named)


def _bar_ticks(vmax: float, fmt, n: int = 4):
    """Round ticks from 0 across the range, labeled by `fmt`.

    `n` is a target, not a guarantee: the step snaps up to a round 1/2/2.5/5
    multiple, so asking for four intervals yields three to four gridlines.
    """
    raw = vmax / n
    step = 10 ** math.floor(math.log10(raw))
    step = next(m * step for m in (1, 2, 2.5, 5, 10) if raw <= m * step)
    vals, v = [], 0.0
    while v <= vmax:
        vals.append(v)
        v += step
    return vals, [("$0" if v == 0 else fmt(v)) for v in vals]


def build(view: str = VIEW_TOTAL):
    df = _load()
    col, label, fmt = _measure(view)
    if view == VIEW_PER_STUDENT:
        # No FTE means no per-student figure; a circle sized on a missing
        # divisor would be a silent zero.
        df = df.dropna(subset=[col])
    # One sizeref for the whole figure, computed from the global maximum, or the
    # three traces would each scale to their own largest circle and HWS would
    # draw the same size as Amherst.
    sizeref = 2.0 * df[col].max() / (MAX_MARKER_PX ** 2)

    # Later traces paint on top: peers first, then NY6, then HWS, so the focus
    # school is never buried under a neighbour in the dense Northeast cluster.
    # Opacity matters as much as order here — unlike the profile map, these
    # circles are large enough to overlap heavily around Boston and Philadelphia.
    groups = [
        ("Peer colleges", "Peer", PEER_COLOR, 0.5),
        ("New York Six", "NY6", NY6_COLOR, 1.5),
        ("Hobart & William Smith", "HWS", HWS_COLOR, 2),
    ]
    # Ranked bars at 30%, map at 70%. Both in one figure rather than two
    # st.columns charts, so the deck's build() contract still holds and the two
    # panels can never drift out of vertical alignment.
    fig = make_subplots(
        rows=1, cols=2, column_widths=[0.3, 0.7], horizontal_spacing=0.06,
        specs=[[{"type": "xy"}, {"type": "scattergeo"}]],
    )
    bar, order, named = _rank_bars(df, col, label)
    fig.add_trace(bar, row=1, col=1)
    for name, key, color, ring in groups:
        fig.add_trace(
            _trace(df[df["Group"] == key], name, color, sizeref, ring, col, label),
            row=1, col=2,
        )

    fig.update_yaxes(
        categoryorder="array", categoryarray=order,
        tickmode="array", tickvals=named, ticktext=named,
        tickfont=dict(size=10, color=TEXT_SECONDARY),
        showgrid=False, ticklen=2, ticklabelstandoff=0, row=1, col=1,
    )
    tickvals, ticktext = _bar_ticks(float(df[col].max()), fmt)
    fig.update_xaxes(
        title_text=f"{label}, FY{fy(PEER_YEAR)}",
        tickmode="array", tickvals=tickvals, ticktext=ticktext,
        tickfont=dict(size=11, color=TEXT_SECONDARY),
        title=dict(font=dict(size=11, color=TEXT_SECONDARY)),
        row=1, col=1,
    )

    hws = df[df["unitid"] == HWS_UNITID]
    note = f"{len(df)} colleges · {df['state'].nunique()} states"
    if not hws.empty:
        value = float(hws[col].iloc[0])
        rank = int((df[col] > value).sum()) + 1
        note += (f"<br>HWS {fmt(value)} · rank {rank} of {len(df)}"
                 f"<br>Peer median {fmt(df[col].median())}")

    fig.update_layout(
        height=620,
        geo=dict(
            scope="usa", projection_type="albers usa",
            showland=True, landcolor=SURFACE,
            showlakes=True, lakecolor=SURFACE,
            subunitcolor=GRID, subunitwidth=1,      # state borders
            countrycolor=GRID, coastlinecolor=GRID,
            bgcolor=SURFACE,
        ),
        # Legend markers inherit the trace's sizeref, which would draw one
        # legend dot per group at whatever that group's first value happens to
        # be. A fixed size keeps the legend about color, which is all it encodes.
        legend=dict(orientation="h", yanchor="bottom", y=1.01,
                    xanchor="left", x=0, title_text="",
                    itemsizing="constant"),
        # One readout for the point under the cursor. The bars sit ~4px apart,
        # so a y-based mode would fire on whichever category the pointer lands
        # in rather than the bar actually aimed at.
        hovermode="closest",
        bargap=0.25,
        # Left margin holds the few named bars; the map needs almost none.
        margin=dict(l=150, r=10, t=60, b=10),
        annotations=[dict(
            text=note, x=0.99, y=0.02, xref="paper", yref="paper",
            xanchor="right", align="right", showarrow=False,
            font=dict(size=12, color=TEXT_SECONDARY),
        )],
    )
    return fig


def render() -> None:
    """Drawn as a body rather than returned as a figure: the view is a widget.

    The control carries the view *keys*; `format_func` is the only place the
    glyphs appear, so relabeling a button never reaches the branching above.
    """
    view = st.segmented_control(
        "View - endowment map",
        options=list(VIEW_LABELS),
        format_func=VIEW_LABELS.get,
        default=VIEW_TOTAL,
        key=VIEW_STATE,
        label_visibility="collapsed",
    ) or VIEW_TOTAL

    st.plotly_chart(build(view), use_container_width=True,
                    key="deck_endow_map_fig")

    # --- Endowment trend for the chosen colleges ----------------------------
    trend = _load_trend()
    names = sorted(trend["institution_name"].unique())

    hws_name = trend.loc[trend["Group"] == "HWS", "institution_name"]
    default = [hws_name.iloc[0]] if not hws_name.empty else names[:1]
    kwargs = {} if TREND_SELECT_KEY in st.session_state else {"default": default}
    picked = st.multiselect(
        "Colleges — endowment trend", names, key=TREND_SELECT_KEY, **kwargs,
    )
    st.plotly_chart(_trend_fig(trend, picked), use_container_width=True,
                    key="deck_endow_trend_fig")
    st.caption(
        "End-of-year endowment market value (IPEDS F2 `f2h02`), every year the "
        "college reported it — nominal dollars, not inflation-adjusted."
    )

    if view == VIEW_PER_STUDENT:
        st.caption(
            "Endowment divided by 12-month FTE enrollment (IPEDS EF-IA "
            "`fteug` + `ftegd`), the same divisor the revenue breakdown slide "
            "uses. This reorders the set: a large endowment spread over a "
            "larger student body backs each student with less."
        )
