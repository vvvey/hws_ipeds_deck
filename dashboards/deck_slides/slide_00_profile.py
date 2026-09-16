"""US map of the peer universe — where HWS sits among comparable colleges.

Technique: `go.Scattergeo` with `scope="usa"`. Three traces rather than one
colored trace, so each group gets its own legend entry, its own marker size, and
a controlled z-order — peers are drawn first and HWS last, so the focus school is
never hidden under a neighbour in a dense cluster like New England.
"""
from __future__ import annotations

import math

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from config import HWS_UNITID
from core.data import query
from core.theme import (BRAND, CATEGORICAL, GRID, NEUTRAL_MARK, SEQUENTIAL,
                        SURFACE, TEXT_SECONDARY)
from ._shared import NY6

# The peer universe: Baccalaureate Colleges: Arts & Sciences Focus (2021 Basic),
# private not-for-profit, 1,000-4,999 students.
#
# carnegie_basic is the 2021 vintage and the only Basic column populated for year
# 2024 — c15basic/c18basic are NULL there, and c21basic is documented in the
# dictionary but absent from the database.
PEER_YEAR = 2024
CARNEGIE_BASIC = 21   # Baccalaureate Colleges: Arts & Sciences Focus
CONTROL = 2           # Private not-for-profit
SIZE_CATEGORY = 2     # 1,000 - 4,999 students

TITLE = "HWS sits inside a national peer set of 139 colleges"
SUBTITLE = ("Private not-for-profit baccalaureate colleges with an arts & sciences "
            "focus and 1,000-4,999 students. Hover any dot for the institution; "
            "the shaded ring is 370 miles from Geneva, NY.")

SOURCE = (
    f"Source: IPEDS Directory (HD) 2025"
)

HWS_COLOR = BRAND["purple"]
NY6_COLOR = CATEGORICAL[2]      # HWS orange
PEER_COLOR = NEUTRAL_MARK       # muted green-gray: present but recessive

# Circle of influence around HWS.
RADIUS_MILES = 370
EARTH_RADIUS_MILES = 3958.7613
RADIUS_COLOR = SEQUENTIAL[0]    # lightest HWS purple tint


def _rgba(hex_color: str, alpha: float) -> str:
    """Hex -> rgba() so a theme color can carry transparency."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _geodesic_circle(lat, lon, miles, points=181):
    """Lon/lat ring of constant great-circle distance from a center.

    Not a plain lat/lon circle: a degree of longitude is ~0.73 of a degree of
    latitude at this latitude, so a naive circle would be visibly squashed. This
    walks true bearings 0-360 and returns where each lands, which the Albers
    projection then renders with the correct shape.
    """
    lat1, lon1 = math.radians(lat), math.radians(lon)
    d = miles / EARTH_RADIUS_MILES          # angular distance in radians
    lons, lats = [], []
    for i in range(points):
        brng = 2 * math.pi * i / (points - 1)
        lat2 = math.asin(math.sin(lat1) * math.cos(d)
                         + math.cos(lat1) * math.sin(d) * math.cos(brng))
        lon2 = lon1 + math.atan2(
            math.sin(brng) * math.sin(d) * math.cos(lat1),
            math.cos(d) - math.sin(lat1) * math.sin(lat2),
        )
        lats.append(math.degrees(lat2))
        lons.append(math.degrees(lon2))
    return lons, lats


@st.cache_data(ttl=3600)
def _peers():
    """The filtered peer universe, tagged HWS / NY6 / Peer."""
    df = query(
        """
        SELECT unitid, institution_name, state, longitude, latitude
        FROM hd
        WHERE year = ?
          AND carnegie_basic = ?
          AND control = ?
          AND size_category = ?
          AND longitude IS NOT NULL
          AND latitude IS NOT NULL
        ORDER BY institution_name
        """,
        (PEER_YEAR, CARNEGIE_BASIC, CONTROL, SIZE_CATEGORY),
    )
    ny6_ids = set(NY6) - {HWS_UNITID}
    df["Group"] = "Peer"
    df.loc[df["unitid"].isin(ny6_ids), "Group"] = "NY6"
    df.loc[df["unitid"] == HWS_UNITID, "Group"] = "HWS"

    # Great-circle distance from HWS, so the caption counts what the ring encloses
    # rather than repeating a hardcoded number that would drift if the filter changes.
    hws = df[df["unitid"] == HWS_UNITID].iloc[0]
    lat1, lon1 = np.radians(hws["latitude"]), np.radians(hws["longitude"])
    lat2, lon2 = np.radians(df["latitude"].values), np.radians(df["longitude"].values)
    df["miles"] = 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    ))
    return df


def _trace(df, name, color, size, ring):
    return go.Scattergeo(
        lon=df["longitude"], lat=df["latitude"],
        name=name, mode="markers",
        customdata=df[["institution_name", "state"]],
        marker=dict(size=size, color=color, opacity=0.9,
                    line=dict(width=ring, color=SURFACE)),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>",
    )


def build():
    df = _peers()
    hws = df[df["Group"] == "HWS"].iloc[0]

    # Order matters: later traces paint on top. The radius goes first so it sits
    # under every marker, then peers, then NY6, then HWS — so the focus school is
    # never buried under a neighbour in the dense Northeast cluster.
    ring_lon, ring_lat = _geodesic_circle(
        hws["latitude"], hws["longitude"], RADIUS_MILES
    )
    fig = go.Figure([go.Scattergeo(
        lon=ring_lon, lat=ring_lat,
        name=f"{RADIUS_MILES}-mile radius", mode="lines",
        fill="toself", fillcolor=_rgba(RADIUS_COLOR, 0.28),
        line=dict(width=1.5, color=RADIUS_COLOR),
        hoverinfo="skip",   # never steal a hover from a college marker
    )])

    within = df[df["miles"] <= RADIUS_MILES]
    inside, inside_states = len(within), within["state"].nunique()

    groups = [
        ("Peer colleges", "Peer", PEER_COLOR, 8, 1),
        ("NY6", "NY6", NY6_COLOR, 13, 2),
        ("Hobart & William Smith", "HWS", HWS_COLOR, 19, 3),
    ]
    for label, key, color, size, ring in groups:
        fig.add_trace(_trace(df[df["Group"] == key], label, color, size, ring))
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
        legend=dict(orientation="h", yanchor="bottom", y=1.01,
                    xanchor="left", x=0, title_text=""),
        margin=dict(l=10, r=10, t=60, b=10),
        annotations=[dict(
            text=(f"{len(df)} colleges · {df['state'].nunique()} states<br>"
                  f"{inside} within {RADIUS_MILES} mi "
                  f"({inside / len(df):.0%}) · {inside_states} states"),
            x=0.99, y=0.02, xref="paper", yref="paper",
            xanchor="right", align="right", showarrow=False,
            font=dict(size=12, color=TEXT_SECONDARY),
        )],
    )
    return fig
