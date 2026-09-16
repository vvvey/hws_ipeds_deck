"""Where New York's first-time students actually go, as one flow.

A funnel from the whole New York market down to a single college. The point is
proportion: HWS's 213 New Yorkers are 0.1% of the state's first-time cohort and
4.3% of the liberal arts colleges that cohort reaches. Both numbers matter, and
a table makes them look similar - a Sankey does not.

Structure. Every stage is a strict subset of the one before, and each split
carries an explicit residual ("Other private nonprofit", "Other peer colleges")
so the flows conserve; without those the diagram silently loses students.

    NY first-time students
      -> sector (5)
        -> private nonprofit 4-year splits into liberal arts + everything else
          -> liberal arts splits into the New York Six + the other peers
            -> the New York Six splits into its six colleges

The last two stages are what the slide is for: the consortium is 21% of the
liberal arts colleges New Yorkers reach, and HWS is a fifth of the consortium.

The ribbons at the bottom are thin on purpose. 213 out of 170,459 is one part in
800, and drawing it any other way would misstate the scale of what a single
college captures.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from config import HWS_UNITID
from core.data import query
from core.theme import (BRAND, NEUTRAL_MARK, SURFACE, TEXT_PRIMARY,
                        TEXT_SECONDARY)
from ._shared import NY6
from .slide_00_profile import (CARNEGIE_BASIC, CONTROL, PEER_YEAR,
                               SIZE_CATEGORY)

HOME_STATE_FIPS = 36        # New York, in the EF-C residence coding
HOME_STATE = "New York"

TITLE = "Where New York's students go"
SUBTITLE = (f"Every first-time degree-seeking undergraduate from {HOME_STATE}, "
            f"fall {PEER_YEAR}, followed from the whole market down to one "
            f"college.")

SOURCE = (
    f"Source: IPEDS Residence and Migration (EF-C), fall {PEER_YEAR}, "
    f"first-time degree/certificate-seeking undergraduates whose state of "
    f"residence is {HOME_STATE} (efres01). Sector and Carnegie classification "
    f"from the IPEDS Directory (HD)."
)

CAVEAT = (
    "First-time degree-seeking undergraduates only - transfers and continuing "
    "students are not in this survey, and IPEDS collects no residence data for "
    "graduate students at all. Residence is state of residence when the student "
    "was first admitted, not where they went to high school. EF-C collects full "
    "detail from every institution only in even years, so this is a complete "
    "year; the next one is 2026."
)

# Sector groupings, in the order they stack in the diagram. IPEDS sector codes:
# 1 public 4-yr, 2 private nonprofit 4-yr, 3/6/9 for-profit, 4 public 2-yr,
# 5/7/8 remaining nonprofit and public short-cycle.
# Declaration order is top-to-bottom order in the diagram. The spine is declared
# last so it sits at the bottom of its column, which puts the whole narrowing —
# liberal arts, the consortium, the six colleges — along the bottom edge instead
# of threading back through the middle of the other sectors' ribbons.
SECTORS = {
    "Public 4-year": (1,),
    "Public 2-year": (4,),
    "For-profit": (3, 6, 9),
    "Other 2-year & below": (5, 7, 8, 0, 99),
    "Private nonprofit 4-year": (2,),
}
SPINE = "Private nonprofit 4-year"   # the only sector that splits further

LIBERAL_ARTS = "Liberal arts colleges"
NY6_LABEL = "New York Six"
OTHER_PRIVATE = "Other private nonprofit 4-year"
OTHER_PEERS = "Other peer colleges"

HWS_COLOR = BRAND["green"]
NY6_COLOR = BRAND["orange"]
REST_COLOR = NEUTRAL_MARK
SPINE_COLOR = BRAND["purple"]


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


@st.cache_data(ttl=3600)
def _load():
    """One row per institution receiving home-state first-time students."""
    return query(
        """
        WITH peers AS (
            SELECT unitid FROM hd
            WHERE year = ? AND carnegie_basic = ? AND control = ?
              AND size_category = ?
        )
        SELECT h.institution_name AS college, h.state, h.sector,
               CASE WHEN p.unitid IS NOT NULL THEN TRUE ELSE FALSE END AS is_peer,
               CAST(e.efres01 AS BIGINT) AS students
        FROM ef_c e
        JOIN hd h ON h.unitid = e.unitid AND h.year = e.year
        LEFT JOIN peers p ON p.unitid = e.unitid
        WHERE e.year = ? AND e.efcstate = ? AND e.efres01 IS NOT NULL
        """,
        (PEER_YEAR, CARNEGIE_BASIC, CONTROL, SIZE_CATEGORY,
         PEER_YEAR, HOME_STATE_FIPS),
    )


_NY6_TOKENS = {
    HWS_UNITID: "hobart",
    190099: "colgate",
    191515: "hamilton",
    195526: "skidmore",
    195216: "lawrence",
    196866: "union",
}


def _is_ny6(name: str) -> bool:
    """Name match against the consortium.

    EF-C joins to `hd`, whose institution_name differs from the deck's display
    names ("Hobart William Smith Colleges" vs "Hobart & William Smith"), so the
    match is on a distinctive token rather than on equality. "lawrence" would
    also catch Sarah Lawrence, so St Lawrence is checked with its saint prefix.
    """
    n = name.lower()
    if "sarah lawrence" in n:
        return False
    return any(tok in n for tok in ("hobart", "colgate", "hamilton college",
                                    "skidmore", "st lawrence", "union college"))


def _flows():
    """(labels, colors, stages, sources, targets, values, totals) for the Sankey."""
    df = _load()
    total = int(df["students"].sum())

    sector_of = {code: name for name, codes in SECTORS.items() for code in codes}
    df["sector_name"] = df["sector"].map(
        lambda s: sector_of.get(int(s), "Other 2-year & below"))
    sector_totals = df.groupby("sector_name")["students"].sum()

    peers = df[df["is_peer"]].copy()
    peer_total = int(peers["students"].sum())
    ny6 = {c for c in peers["college"] if _is_ny6(c)}

    root = f"{HOME_STATE} first-time students"
    labels = [root]
    colors = [SPINE_COLOR]
    # Stage index per node. Without it Plotly places a node in the column after
    # its deepest source, so "Public 4-year" (a leaf) would drift right and stop
    # lining up with the sector it should sit beside.
    stages = [0]
    src, tgt, val = [], [], []

    def node(label, color, stage):
        labels.append(label)
        colors.append(color)
        stages.append(stage)
        return len(labels) - 1

    def link(a, b, v):
        src.append(a), tgt.append(b), val.append(float(v))

    # Stage 1: sector.
    for name in SECTORS:
        v = sector_totals.get(name, 0)
        if not v:
            continue
        i = node(name, SPINE_COLOR if name == SPINE else REST_COLOR, 1)
        link(0, i, v)
        if name != SPINE:
            continue
        # Stage 2: the spine splits into liberal arts and everything else.
        la = node(LIBERAL_ARTS, SPINE_COLOR, 2)
        other = node(OTHER_PRIVATE, REST_COLOR, 2)
        link(i, la, peer_total)
        link(i, other, v - peer_total)
        # Stage 3: the consortium against the rest of the peer set.
        consortium = peers[peers["college"].isin(ny6)]
        ny6_total = int(consortium["students"].sum())
        six = node(NY6_LABEL, NY6_COLOR, 3)
        link(la, six, ny6_total)
        rest = peer_total - ny6_total
        if rest > 0:
            link(la, node(OTHER_PEERS, REST_COLOR, 3), rest)
        # Stage 4: the six colleges individually, largest first. HWS keeps its
        # own color; the other five share the consortium orange, so the last
        # split reads as "one of these six" rather than six unrelated colleges.
        for _, row in consortium.sort_values("students", ascending=False).iterrows():
            college = row["college"]
            color = HWS_COLOR if "hobart" in college.lower() else NY6_COLOR
            link(six, node(college, color, 4), row["students"])

    return labels, colors, stages, src, tgt, val, total, peer_total


def build():
    labels, colors, stages, src, tgt, val, total, peer_total = _flows()

    # The count travels in the label, because a Sankey node is a rectangle with
    # no axis to read against - without the number, a thin ribbon is only
    # "small". Each node's value is what flows into it; the root has none.
    node_value = {0: total}
    for t, v in zip(tgt, val):
        node_value[t] = node_value.get(t, 0) + v
    text = [f"{lab}  {int(node_value.get(i, 0)):,}"
            for i, lab in enumerate(labels)]

    # Columns are pinned by stage so every sector stays on one vertical line;
    # left to Plotly, a leaf like "Public 4-year" drifts rightward and no longer
    # reads as a sibling of the sector that splits.
    #
    # Vertically each node is laid out inside its parent's band, the way an
    # icicle chart nests: the root owns 0..1, each child takes a slice of its
    # parent proportional to its value, in link order. Stacking each column
    # independently instead would put the spine at the bottom of one column and
    # its children at the top of the next, and every ribbon would sweep back
    # across the whole canvas to reach them.
    n_stages = max(stages)
    children = {}
    for a, b in zip(src, tgt):
        children.setdefault(a, []).append(b)

    band = {0: (0.0, 1.0)}
    queue = [0]
    while queue:
        i = queue.pop(0)
        lo, hi = band[i]
        span = hi - lo
        parent_value = node_value.get(i, 0) or 1
        offset = lo
        for child in children.get(i, []):
            share = node_value.get(child, 0) / parent_value
            band[child] = (offset, offset + span * share)
            offset += span * share
            queue.append(child)

    x = [0.0] * len(labels)
    y = [0.0] * len(labels)
    for i in range(len(labels)):
        lo, hi = band.get(i, (0.0, 1.0))
        # Plotly rejects an exact 0 or 1, so the range is squeezed slightly.
        x[i] = min(0.98, max(0.02, stages[i] / n_stages))
        y[i] = min(0.98, max(0.02, (lo + hi) / 2))

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            label=text, color=colors, x=x, y=y, pad=14, thickness=18,
            line=dict(color=SURFACE, width=0.5),
            hovertemplate="%{label}<br>%{value:,} students<extra></extra>",
        ),
        link=dict(
            source=src, target=tgt, value=val,
            color=[_rgba(colors[t], 0.34) for t in tgt],
            hovertemplate=("%{source.label} → %{target.label}"
                           "<br>%{value:,} students<extra></extra>"),
        ),
    ))
    fig.update_layout(
        height=820,
        font=dict(color=TEXT_PRIMARY, size=12),
        margin=dict(l=20, r=20, t=50, b=40),
        annotations=[dict(
            text=(f"{total:,} first-time students · {peer_total:,} reach a "
                  f"liberal arts college · {peer_total / total:.1%} of the market"),
            x=0, y=-0.06, xref="paper", yref="paper", xanchor="left",
            showarrow=False, font=dict(size=12, color=TEXT_SECONDARY),
        )],
    )
    return fig
