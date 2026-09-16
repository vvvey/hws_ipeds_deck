"""Revenue breakdown for colleges that closed, in the decade before they did.

Same stacked bands, expense reference and three views as
`slide_40_ny6_revenue_breakdown`, pointed at institutions that no longer exist.
Everything about the encoding is imported from that slide rather than restated,
so a band renamed there is renamed here and the two charts can never drift into
using one color for different money.

The roster is the PrepScholar list of permanently closed colleges, matched to
IPEDS unitids by normalized name within state. Matches were reviewed by hand;
four listed colleges had no IPEDS record under any close name and are absent.

Two limits worth knowing before reading a trend here:

1. **The endowment draw band is empty before FY2019-20.** IPEDS did not collect
   f2h03c until then, so for a college that closed in 2016 the band simply does
   not exist. Its absence is a reporting fact, not a college that stopped
   drawing on its endowment.
2. **The last year on the chart is the last year filed**, which is usually the
   year before the doors closed and is often a partial or irregular filing. The
   final point is the weakest one on every one of these charts.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from core.data import query
from core.theme import BRAND, GRID, SURFACE, TEXT_PRIMARY, TEXT_SECONDARY
from ._shared import fy
from .slide_40_ny6_revenue_breakdown import (COLOR, PATTERN, REVENUE_GROUPS,
                                             SOURCE_COLS, VIEW_DOLLARS,
                                             VIEW_LABELS, VIEW_PER_STUDENT,
                                             _apply_view, _dollar_ticks,
                                             _fmt_dollars)

WINDOW = 10   # years of history to draw, ending at the last year filed

# Size floor: a college qualifies if total expenses cleared this in at least one
# year of its final decade. Measured inside the plotted window rather than over
# the college's whole history, so the threshold describes the institution the
# chart actually shows rather than one it used to be.
MIN_PEAK_EXPENSES = 0

TITLE = "What the books looked like on the way down"
SUBTITLE = ("Revenue by source against total expenses for colleges that have "
            "since closed, over their final decade of IPEDS filings.")

SOURCE = (
    "Source: IPEDS Finance survey (F2, private nonprofit / FASB); 12-month FTE "
    "enrollment from the Instructional Activity survey (EF-IA). Closure list "
    "and dates from PrepScholar's permanently closed colleges list, matched to "
    "IPEDS by name and state."
)

CAVEAT = (
    "The endowment draw band (f2h03c) does not exist before FY2019-20 because "
    "IPEDS did not collect it, so on a college that closed earlier its absence "
    "means nothing about that college. The final year plotted is the last one "
    "filed, often a partial year, and is the least reliable point on the "
    "chart. Closure years come from the source list and mark the announced "
    "closing, which can trail the last filing by a year or more."
)

# (unitid, IPEDS name, state, year closed) - see the module docstring on how
# this roster was built.
CLOSED = [
    (100937, "Birmingham-Southern College", "AL", 2024),
    (101073, "Concordia College", "AL", 2018),
    (101541, "Judson College", "AL", 2021),
    (102261, "Southeastern Bible College", "AL", 2017),
    (112446, "Coleman University", "CA", 2018),
    (115728, "Holy Names University", "CA", 2023),
    (118541, "Marymount California University", "CA", 2022),
    (118888, "Mills College", "CA", 2022),
    (122454, "San Francisco Art Institute", "CA", 2022),
    (488785, "University of Saint Katherine", "CA", 2024),
    (125897, "Woodbury University", "CA", 2024),
    (367839, "Colorado Heights University", "CO", 2017),
    (130448, "St Vincent's College", "CT", 2017),
    (432524, "Delaware College of Art and Design", "DE", 2024),
    (131098, "Wesley College", "DE", 2021),
    (367884, "Hodges University", "FL", 2024),
    (132879, "Johnson University Florida", "FL", 2024),
    (153621, "Iowa Wesleyan University", "IA", 2023),
    (146667, "Lincoln Christian University", "IL", 2024),
    (146676, "Lincoln College", "IL", 2022),
    (146825, "MacMurray College", "IL", 2020),
    (149763, "Oak Point University", "IL", 2024),
    (148335, "Robert Morris University Illinois", "IL", 2020),
    (148849, "Shimer College", "IL", 2017),
    (148876, "St. Augustine College", "IL", 2024),
    (150048, "Ancilla College", "IN", 2021),
    (152363, "Saint Josephs College", "IN", 2017),
    (157632, "Saint Catharine College", "KY", 2016),
    (164571, "Atlantic Union College", "MA", 2018),
    (164720, "Becker College", "MA", 2021),
    (165167, "Cambridge College", "MA", 2025),
    (165644, "Eastern Nazarene College", "MA", 2025),
    (165705, "Episcopal Divinity School", "MA", 2017),
    (166948, "Mount Ida College", "MA", 2018),
    (167251, "Newbury College", "MA", 2018),
    (167455, "Pine Manor College", "MA", 2020),
    (168290, "Wheelock College", "MA", 2018),
    (164085, "Maryland University of Integrative Health", "MD", 2024),
    (459417, "Compass College of Film and Media", "MI", 2023),
    (172440, "Finlandia University", "MI", 2023),
    (170842, "Marygrove College", "MI", 2019),
    (174206, "Crossroads College", "MN", 2017),
    (176770, "Cox College", "MO", 2025),
    (177418, "Fontbonne University", "MO", 2025),
    (179256, "Saint Louis Christian College", "MO", 2022),
    (198747, "John Wesley University", "NC", 2018),
    (181093, "Grace University", "NE", 2017),
    (181376, "Nebraska Christian College", "NE", 2020),
    (182917, "Magdalen College", "NH", 2024),
    (430810, "New Hampshire Institute of Art", "NH", 2019),
    (183822, "Bloomfield College", "NJ", 2023),
    (182458, "Sierra Nevada University", "NV", 2022),
    (194161, "Alliance University", "NY", 2023),
    (189848, "Cazenovia College", "NY", 2023),
    (190248, "Concordia College", "NY", 2021),
    (190770, "Dowling College", "NY", 2016),
    (192864, "Marymount Manhattan College", "NY", 2025),
    (192925, "Medaille University", "NY", 2023),
    (193645, "The College of New Rochelle", "NY", 2019),
    (195234, "The College of Saint Rose", "NY", 2024),
    (197230, "Wells College", "NY", 2024),
    (201371, "Bluffton University", "OH", 2025),
    (201751, "Chatfield College", "OH", 2023),
    (201858, "Cincinnati Christian University", "OH", 2019),
    (204468, "Notre Dame College", "OH", 2024),
    (206279, "Union Institute & University", "OH", 2024),
    (206330, "Urbana University", "OH", 2020),
    (207689, "St. Gregory's University", "OK", 2017),
    (208488, "Concordia University", "OR", 2020),
    (209108, "Marylhurst University", "OR", 2018),
    (209287, "Multnomah University", "OR", 2023),
    (209533, "Oregon College of Art and Craft", "OR", 2019),
    (209603, "Pacific Northwest College of Art", "OR", 2021),
    (211352, "Cabrini University", "PA", 2024),
    (211024, "Clarks Summit University", "PA", 2024),
    (442356, "Pennsylvania College of Health Sciences", "PA", 2024),
    (215415, "Pittsburgh Technical College", "PA", 2024),
    (214564, "Salus University", "PA", 2024),
    (215105, "University of the Arts", "PA", 2024),
    (215132, "University of the Sciences", "PA", 2022),
    (241100, "American University of Puerto Rico", "PR", 2023),
    (219295, "Presentation College", "SD", 2023),
    (220312, "Hiwassee College", "TN", 2019),
    (220701, "Martin Methodist College", "TN", 2021),
    (220808, "Memphis College of Art", "TN", 2017),
    (221254, "O'More College of Design", "TN", 2018),
    (465812, "Independence University", "UT", 2021),
    (230825, "Burlington College", "VT", 2016),
    (231077, "College of St Joseph", "VT", 2019),
    (230889, "Goddard College", "VT", 2024),
    (230898, "Green Mountain College", "VT", 2019),
    (230940, "Marlboro College", "VT", 2020),
    (231086, "Southern Vermont College", "VT", 2019),
    (235769, "Trinity Lutheran College", "WA", 2016),
    (238430, "Cardinal Stritch University", "WI", 2023),
    (239743, "Holy Family College", "WI", 2020),
    (237118, "Alderson Broaddus University", "WV", 2023),
    (237640, "Ohio Valley University", "WV", 2021),
]

NAME = {u: n for u, n, _, _ in CLOSED}
CLOSE_YEAR = {u: y for u, _, _, y in CLOSED}
LABEL = {u: f"{n} ({s}, closed {y})" for u, n, s, y in CLOSED}

STATE = {u: s for u, _, s, _ in CLOSED}

VIEW_STATE = "deck_closed_view"
PICK_STATE = "deck_closed_pick"
MIN_EXP_STATE = "deck_closed_min_exp"
STATES_STATE = "deck_closed_states"


@st.cache_data(ttl=3600)
def _peaks():
    """unitid -> peak total expenses inside the plotted window, biggest first.

    One query for the whole roster rather than a per-college check: the filters
    need every college's size before anything is drawn. No threshold is applied
    here — the floor is a widget now, so the cache holds the raw measure and
    survives a viewer moving the slider.
    """
    ids = ", ".join(str(u) for u, *_ in CLOSED)
    df = query(
        f"""
        WITH last AS (
            SELECT unitid, MAX(year) AS ly FROM f2
            WHERE unitid IN ({ids}) AND f2b02 IS NOT NULL
            GROUP BY unitid
        )
        SELECT f.unitid, MAX(CAST(f.f2b02 AS DOUBLE)) AS peak
        FROM f2 f
        JOIN last l ON l.unitid = f.unitid
        WHERE f.year > l.ly - ? AND f.f2b02 IS NOT NULL
        GROUP BY f.unitid
        ORDER BY peak DESC
        """,
        (WINDOW,),
    )
    return {int(u): float(p) for u, p in zip(df["unitid"], df["peak"])}


@st.cache_data(ttl=3600)
def _load_raw(unitid: int):
    """Raw IPEDS columns for one college. Labels are applied outside the cache.

    Cached per unitid rather than for the whole roster: a viewer looks at a
    handful of colleges in a session, and loading a hundred institutions to
    draw one is work nobody asked for.
    """
    selects = "".join(f", CAST(f.{c} AS DOUBLE) AS {c}" for c in SOURCE_COLS)
    return query(
        f"""
        SELECT f.year, CAST(f.f2b02 AS DOUBLE) AS expenses,
               CAST(f.f2h02 AS DOUBLE) AS endowment,
               COALESCE(CAST(a.fteug AS DOUBLE), CAST(a.efteug AS DOUBLE))
                 + COALESCE(CAST(a.ftegd AS DOUBLE), CAST(a.eftegd AS DOUBLE), 0)
                 AS fte{selects}
        FROM f2 f
        LEFT JOIN efia a ON a.unitid = f.unitid AND a.year = f.year
        WHERE f.unitid = ? AND f.f2b02 IS NOT NULL
        ORDER BY f.year
        """,
        (unitid,),
    )


def _load(unitid: int):
    """One college's final decade, with the group columns applied."""
    df = _load_raw(unitid).copy()
    if df.empty:
        return df
    # The window ends at the last year filed, not at the closure year: a
    # college that closed in 2024 may have stopped filing in 2022, and padding
    # the gap with empty years would draw a collapse that is really a silence.
    last = int(df["year"].max())
    df = df[df["year"] > last - WINDOW]
    df["f2h03c"] = df["f2h03c"].abs()
    for group, members in REVENUE_GROUPS.items():
        df[group] = df[members].sum(axis=1, min_count=1).fillna(0)
    df["Institution"] = NAME[unitid]
    return df


def _build(df, view: str, unitid: int):
    d, y_title, hover, is_dollars = _apply_view(df, view)
    if d.empty:
        return None
    years = sorted(int(y) for y in d["year"].unique())
    g = d.set_index("year").reindex(years)

    fig = go.Figure()
    for group in REVENUE_GROUPS:
        fig.add_trace(go.Scatter(
            x=years, y=g[group].values, name=group, mode="lines",
            line=dict(width=0), fillcolor=COLOR[group],
            fillpattern=dict(shape=PATTERN[group], bgcolor=COLOR[group],
                             fgcolor=SURFACE, fgopacity=0.35,
                             size=7, solidity=0.25),
            stackgroup="one",
            hovertemplate=f"%{{fullData.name}}: {hover}<extra></extra>",
        ))

    ref = g["Reference"]
    ref_hover = f"<b>Total expenses: {hover}</b>"
    customdata = None
    if view == VIEW_PER_STUDENT:
        customdata = g["fte"].values
        ref_hover += "<br>FTE enrollment: %{customdata:,.0f}"
    fig.add_trace(go.Scatter(
        x=years, y=ref.values, name="Total expenses", mode="lines",
        line=dict(width=2, dash="dot", color=TEXT_SECONDARY),
        customdata=customdata,
        hovertemplate=f"{ref_hover}<extra></extra>",
    ))

    # The announced closing, marked only when it falls inside the plotted
    # window. It usually does not: most of these colleges stopped filing before
    # they stopped operating, and drawing the line outside the data would
    # stretch the axis across years with nothing in them.
    closed = CLOSE_YEAR[unitid]
    if years[0] <= closed <= years[-1]:
        fig.add_vline(
            x=closed, line=dict(color=TEXT_PRIMARY, width=1.5, dash="dash"),
            annotation_text=f"closed {closed}", annotation_position="top left",
            annotation_font=dict(size=12, color=TEXT_PRIMARY),
        )

    panel_max = max(float(g[list(REVENUE_GROUPS)].sum(axis=1).max()),
                    float(ref.max()))
    ink = dict(color=TEXT_PRIMARY)
    fig.update_xaxes(showgrid=False, tickmode="array", tickvals=years,
                     ticktext=[fy(y) for y in years], tickangle=-45,
                     tickfont=dict(color=TEXT_PRIMARY, size=12),
                     title=dict(font=ink))
    if is_dollars:
        vals, text = _dollar_ticks(panel_max,
                                   n=8 if view == VIEW_PER_STUDENT else 4)
        fig.update_yaxes(range=[0, panel_max * 1.05], tickmode="array",
                         tickvals=vals, ticktext=text)
    else:
        top = max(125, int(panel_max // 25 + 1) * 25)
        pct = list(range(0, top + 1, 25))
        fig.update_yaxes(range=[0, top], tickmode="array", tickvals=pct,
                         ticktext=[f"{v}%" for v in pct])
    fig.update_yaxes(title_text=y_title, ticklen=2, ticklabelstandoff=0,
                     tickfont=dict(color=TEXT_PRIMARY, size=12),
                     title=dict(font=ink))
    fig.update_layout(
        height=520, hovermode="x unified",
        legend=dict(orientation="v", title_text="", yref="container",
                    yanchor="middle", y=0.5, xref="container",
                    xanchor="left", x=0.005, traceorder="reversed"),
        margin=dict(l=250, r=30, t=40, b=90),
    )
    return fig


def _build_series(df, col, unitid, *, title, color, dollars):
    """One measure over the same years as the chart above.

    Drawn as its own small figure rather than a second axis on the stack: an
    endowment balance and a revenue flow are different kinds of quantity, and
    sharing an axis would invite reading one against the other.
    """
    d = df.dropna(subset=[col])
    if d.empty or (d[col] == 0).all():
        return None
    years = [int(y) for y in d["year"]]
    fig = go.Figure(go.Scatter(
        x=years, y=d[col].values, mode="lines+markers",
        line=dict(color=color, width=3), marker=dict(size=7),
        hovertemplate=("%{x}: " + ("$%{y:,.0f}" if dollars else "%{y:,.0f} FTE")
                       + "<extra></extra>"),
    ))
    closed = CLOSE_YEAR[unitid]
    if years and years[0] <= closed <= years[-1]:
        fig.add_vline(x=closed, line=dict(color=TEXT_PRIMARY, width=1.5,
                                          dash="dash"))
    fig.update_xaxes(showgrid=False, tickmode="array", tickvals=years,
                     ticktext=[fy(y) for y in years], tickangle=-45,
                     tickfont=dict(color=TEXT_PRIMARY, size=11))
    if dollars:
        vals, text = _dollar_ticks(float(d[col].max()))
        fig.update_yaxes(tickmode="array", tickvals=vals, ticktext=text)
    fig.update_yaxes(rangemode="tozero", gridcolor=GRID,
                     tickfont=dict(color=TEXT_PRIMARY, size=11))
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color=TEXT_PRIMARY), x=0),
        height=300, hovermode="x unified", showlegend=False,
        margin=dict(l=70, r=20, t=40, b=70),
    )
    return fig


def render() -> None:
    peaks = _peaks()
    ceiling = int(-(-max(peaks.values()) // 1e6))   # round up to whole $M

    exp_col, state_col = st.columns([2, 3])
    with exp_col:
        floor_m = st.slider(
            "Minimum total expenses ($M, peak year)",
            min_value=0, max_value=ceiling,
            value=int(MIN_PEAK_EXPENSES / 1e6), step=5, key=MIN_EXP_STATE,
        )
    with state_col:
        # Only states that actually have a college with finance data, so the
        # list never offers a filter that can only return nothing.
        options = sorted({STATE[u] for u in peaks})
        states = st.multiselect(
            "State (all if none selected)", options=options, key=STATES_STATE,
        )

    # Ordered biggest-first by peak expenses, so the selector opens on the
    # largest closure rather than on whichever college sorts first by state.
    ids = [u for u in peaks
           if peaks[u] >= floor_m * 1e6 and (not states or STATE[u] in states)]
    if not ids:
        st.warning("No closed college matches these filters.")
        return
    # A stale pick from a wider filter is not in `options` any more, and
    # Streamlit raises rather than silently reselecting. Clearing it first lets
    # the selector fall back to the largest match.
    if st.session_state.get(PICK_STATE) not in ids:
        st.session_state.pop(PICK_STATE, None)
    unitid = st.selectbox(
        "College", options=ids, format_func=LABEL.get, key=PICK_STATE,
    )
    view = st.segmented_control(
        "View - closed college revenue",
        options=list(VIEW_LABELS), format_func=VIEW_LABELS.get,
        default=VIEW_DOLLARS, key=VIEW_STATE, label_visibility="collapsed",
    ) or VIEW_DOLLARS

    df = _load(unitid)
    if df.empty:
        st.warning(f"No F2 finance data found for {NAME[unitid]}.")
        return
    fig = _build(df, view, unitid)
    if fig is None:
        st.warning("No FTE enrollment reported, so there is no per-student view "
                   f"for {NAME[unitid]}.")
        return
    st.plotly_chart(fig, use_container_width=True, key="deck_closed_fig")

    # The two quantities the stack above cannot show: the balance the college
    # was drawing against, and the students it was charging. A revenue chart
    # falling can mean either, and these separate the two.
    left, right = st.columns(2)
    panels = [
        (left, "endowment", f"Endowment, end of year", BRAND["green"], True,
         "deck_closed_endow_fig",
         "No endowment reported (f2h02) in these years."),
        (right, "fte", "12-month FTE enrollment", BRAND["purple"], False,
         "deck_closed_fte_fig",
         "No 12-month FTE enrollment reported (EF-IA) in these years."),
    ]
    for column, col, title, color, dollars, key, empty_msg in panels:
        with column:
            sub = _build_series(df, col, unitid, title=title, color=color,
                                dollars=dollars)
            if sub is None:
                st.caption(f"**{title}** — {empty_msg}")
            else:
                st.plotly_chart(sub, use_container_width=True, key=key)

    first, last = int(df["year"].min()), int(df["year"].max())
    st.caption(
        f"{NAME[unitid]} filed finance data through FY{fy(last)} and closed in "
        f"{CLOSE_YEAR[unitid]}; the chart covers FY{fy(first)} to FY{fy(last)}. "
        f"The selector holds {len(ids)} of {len(CLOSED)} closed colleges under "
        f"the current filters"
        + (f" (peak expenses \\${floor_m:,}M+" if floor_m else " (no size floor")
        + (f", {', '.join(states)})." if states else ", all states).")
    )
