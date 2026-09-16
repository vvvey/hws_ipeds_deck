"""Small multiples of full-time enrollment: one line per college, plus the market.

Replaces an animated bar race. A race showed the ranking changing but not the
shape of any one college's decline, and the ranking is the less interesting
half: these six did not swap places so much as split into two groups that have
been moving apart for a decade. Seven static lines say that in one look, and a
presenter can point at one.

The seventh panel is the peer set summed. It is there to answer the obvious
objection - "everyone is shrinking" - which turns out to be only slightly true:
the market is off about 6% from 2013 while the steepest NY6 line is off 22%.

File name still says `race` so the slide keeps its 10-slot in the deck order;
the contents are no longer a race.
"""
from __future__ import annotations

import math

import plotly.graph_objects as go

from config import HWS_UNITID
from core.data import query
from core.theme import GRID, NEUTRAL_MARK_STRONG, TEXT_PRIMARY, TEXT_SECONDARY
from ._shared import COLOR, NY6
from .slide_00_profile import (CARNEGIE_BASIC, CONTROL, PEER_YEAR,
                               SIZE_CATEGORY)

FIRST_YEAR = 2013
FACET_COLS = 4
PEER_LABEL = "National peer set (133, summed)"

TITLE = "Enrollment is diverging across the NY6"
SUBTITLE = ("Fall full-time headcount (solid) with 12-month FTE (dotted), "
            "one panel per college, and the national peer set summed for "
            "reference. The college panels share a scale; the peer panel has "
            "its own.")

TAKEAWAY = (
    "The consortium has split in two. Hobart & William Smith (−21.6% since "
    "2013) and St. Lawrence (−19.5%) have lost a fifth of their students, "
    "while Colgate (+10.5%) and Hamilton (+6.6%) grew. The peer set is down "
    "about 6% over the same years, so the losses at the bottom of the group "
    "are specific to those colleges, not a market anyone was riding out."
)

CAVEAT = (
    "Two measures of the same students. Fall headcount (IPEDS EF, efalevel = "
    "21) is a census on one day; 12-month FTE (EF-IA) weights every student by "
    "course load across the whole year, so it runs lower wherever part-time "
    "study is common. The FTE line is plotted against the fall term it "
    "contains - EFIA2024 covers July 2023 to June 2024, so it sits at fall "
    "2023 - which is why it stops one year short of the headcount line. The "
    "peer panel sums 133 colleges and excludes the six shown individually."
)

SOURCE = (
    f"Source: IPEDS Fall Enrollment (EF), full-time total, and 12-month "
    f"Instructional Activity (EF-IA) FTE, fall {FIRST_YEAR} onward. Peer "
    f"filter from the IPEDS Directory (HD)."
)

PEER_COLOR = NEUTRAL_MARK_STRONG


def _load():
    """Fall headcount and 12-month FTE per college, plus the peer totals.

    Both measures are keyed to the *fall term*. The fall file already is, but
    the 12-month file is labeled by fiscal-year end - EFIA2024 covers July 2023
    to June 2024, whose fall term is fall 2023 - so its year is shifted back one
    to sit against the right point on the axis. Without the shift the FTE line
    would read a year early and appear to lead the headcount line.
    """
    ids = ", ".join(str(u) for u in NY6)
    return query(
        f"""
        WITH peer_universe AS (
            SELECT unitid FROM hd
            WHERE year = ? AND carnegie_basic = ? AND control = ?
              AND size_category = ?
        ),
        fall AS (
            SELECT CAST(e.unitid AS BIGINT) AS unitid, e.year,
                   CAST(e.eftotlt AS BIGINT) AS ft
            FROM ef_a e
            WHERE e.efalevel = 21 AND e.year >= ? AND e.unitid IN ({ids})
            UNION ALL
            -- The peer cohort as a single series: one row per year carrying the
            -- summed count, with a sentinel unitid so it travels in the same
            -- frame as the colleges instead of needing a second query.
            SELECT -1, e.year, SUM(CAST(e.eftotlt AS BIGINT))
            FROM ef_a e
            JOIN peer_universe p ON p.unitid = e.unitid
            WHERE e.efalevel = 21 AND e.year >= ? AND e.unitid NOT IN ({ids})
            GROUP BY e.year
        ),
        fte AS (
            SELECT CAST(a.unitid AS BIGINT) AS unitid, a.year - 1 AS year,
                   COALESCE(CAST(a.fteug AS DOUBLE), CAST(a.efteug AS DOUBLE))
                     + COALESCE(CAST(a.ftegd AS DOUBLE),
                                CAST(a.eftegd AS DOUBLE), 0) AS fte
            FROM efia a
            WHERE a.year > ? AND a.unitid IN ({ids})
            UNION ALL
            SELECT -1, a.year - 1,
                   SUM(COALESCE(CAST(a.fteug AS DOUBLE), CAST(a.efteug AS DOUBLE))
                       + COALESCE(CAST(a.ftegd AS DOUBLE),
                                  CAST(a.eftegd AS DOUBLE), 0))
            FROM efia a
            JOIN peer_universe p ON p.unitid = a.unitid
            WHERE a.year > ? AND a.unitid NOT IN ({ids})
            GROUP BY a.year
        )
        SELECT f.unitid, f.year, f.ft, t.fte
        FROM fall f
        LEFT JOIN fte t ON t.unitid = f.unitid AND t.year = f.year
        ORDER BY f.year
        """,
        (PEER_YEAR, CARNEGIE_BASIC, CONTROL, SIZE_CATEGORY,
         FIRST_YEAR, FIRST_YEAR, FIRST_YEAR, FIRST_YEAR),
    )


def build():
    df = _load()
    years = sorted(int(y) for y in df["year"].unique())
    panels = [(u, NY6[u]) for u in NY6] + [(-1, PEER_LABEL)]

    # Academic-year labels: fall 2014 opens the 2014-2015 year, so the axis
    # says what the term is called rather than which calendar year it starts in.
    labels = [f"{y}-{y + 1}" for y in years]

    rows = math.ceil(len(panels) / FACET_COLS)
    # Titles carry the total change over the window, because that is the number
    # the slide is about and reading it off a line is guesswork.
    titles = []
    for unitid, name in panels:
        s = df[df["unitid"] == unitid].set_index("year")["ft"]
        pct = (s.get(years[-1], float("nan")) / s.get(years[0], float("nan")) - 1) * 100
        titles.append(f"{name}<br><sub>{pct:+.1f}% since {years[0]}</sub>")

    from plotly.subplots import make_subplots
    fig = make_subplots(rows=rows, cols=FACET_COLS, subplot_titles=titles,
                        horizontal_spacing=0.06, vertical_spacing=0.20)

    colleges = df[df["unitid"] != -1]
    college_max = float(max(colleges["ft"].max(), colleges["fte"].max()))
    for i, (unitid, name) in enumerate(panels):
        row, col = i // FACET_COLS + 1, i % FACET_COLS + 1
        g = df[df["unitid"] == unitid].set_index("year").reindex(years)
        is_peer = unitid == -1
        color = PEER_COLOR if is_peer else COLOR[NY6[unitid]]
        # Two measures of the same students: the fall census in the college's
        # own color, the 12-month FTE dashed over it. FTE is drawn in the same
        # hue rather than a second color because it is not another series to
        # compare against - it is the same enrollment counted differently.
        for measure, label, dash, width in [
            ("ft", "Fall full-time", None, 3.5 if unitid == HWS_UNITID else 2.5),
            ("fte", "12-month FTE", "dot", 2),
        ]:
            fig.add_trace(
                go.Scatter(
                    x=labels, y=g[measure].values, name=label,
                    legendgroup=label, showlegend=(i == 0),
                    mode="lines+markers",
                    line=dict(color=color, width=width, dash=dash),
                    marker=dict(size=6 if measure == "ft" else 4),
                    opacity=1.0 if measure == "ft" else 0.75,
                    hovertemplate=f"{label}: %{{y:,.0f}}<extra></extra>",
                ),
                row=row, col=col,
            )
        # The college panels share one scale so the six are comparable at a
        # glance; the peer total is two orders of magnitude larger and would
        # flatten every one of them onto the axis.
        top = (float(max(g["ft"].max(), g["fte"].max())) * 1.08 if is_peer
               else college_max * 1.08)
        fig.update_yaxes(range=[0, top], row=row, col=col)

    # Every other label: twelve of these are nine characters wide and would
    # collide in a quarter-width facet.
    fig.update_xaxes(showgrid=False, tickmode="array", tickvals=labels[::2],
                     tickangle=-45,
                     tickfont=dict(color=TEXT_PRIMARY, size=11))
    fig.update_yaxes(gridcolor=GRID, tickformat=",",
                     ticklen=2, ticklabelstandoff=0,
                     tickfont=dict(color=TEXT_PRIMARY, size=11))
    fig.update_yaxes(title_text="Full-time students",
                     title=dict(font=dict(color=TEXT_PRIMARY)), row=1, col=1)
    fig.update_annotations(font=dict(color=TEXT_PRIMARY, size=13))
    fig.update_layout(
        height=rows * 290 + 150, hovermode="x unified",
        legend=dict(orientation="h", title_text="", yref="container",
                    yanchor="top", y=0.99, xref="container",
                    xanchor="left", x=0.01),
        margin=dict(l=80, r=30, t=110, b=70),
        annotations=list(fig.layout.annotations) + [dict(
            text=f"Academic years {labels[0]} to {labels[-1]}",
            x=1, y=-0.12, xref="paper", yref="paper", xanchor="right",
            showarrow=False, font=dict(size=12, color=TEXT_SECONDARY),
        )],
    )
    return fig
