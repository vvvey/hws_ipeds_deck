"""Shared data and chart helpers for deck slides.

## The slide contract

Each `slide_*.py` module in this package declares:

| Name       | Required | Meaning                                              |
|------------|----------|------------------------------------------------------|
| `TITLE`    | yes      | Slide headline (rendered as the page title)          |
| `build()`  | yes      | Returns a Plotly figure                              |
| `SUBTITLE` | no       | One line under the title                             |
| `FACTOIDS` | no       | KPI tiles under the chart — see below                |
| `TAKEAWAY` | no       | The "so what", shown in a callout below the chart    |
| `CAVEAT`   | no       | Data-quality warning, shown below the takeaway       |
| `SOURCE`   | no       | Overrides the default source caption                 |

## Factoids

A factoid is one number the audience should leave with — the chart shows the
shape, the factoids pin the figures a presenter says out loud. Declare either a
constant sequence or, when the numbers have to be computed from data, a
`factoids()` function returning one:

```python
FACTOIDS = [("States represented", "43"), ("From abroad", "128", "Non-US")]

def factoids():                      # takes precedence over the constant
    df = deck_data()
    return [("Revenue / expenses", f"{coverage:.0%}")]
```

Each entry is `(label, value)` or `(label, value, help)`; `help` becomes the
tooltip. They render as one row of bordered tiles between the chart and the
takeaway, so the slide reads chart → numbers → so-what.

`TAKEAWAY` and `CAVEAT` render as Streamlit markdown, which treats `$...$` as
LaTeX — write literal dollar amounts as `\\$101K`.

## Ordering

Slides sort by filename, so the numeric prefix is the running order. Prefixes
step by ten (`slide_10_`, `slide_20_`, …) so a new slide can be dropped between
two existing ones without renaming anything.
"""
from __future__ import annotations

import html

import streamlit as st

from core.data import query
from core.theme import (BRAND, CALLOUT_FILL, CATEGORICAL, DISPLAY_FONT_FAMILY,
                        FONT_FAMILY, GRID, ON_ACCENT, SURFACE, SURFACE_ALT,
                        SURFACE_WARN, TEXT_PRIMARY, TEXT_SECONDARY)

START_YEAR = 2014

# The "New York Six" liberal-arts consortium, HWS first.
NY6 = {
    191630: "Hobart & William Smith",
    190099: "Colgate",
    191515: "Hamilton",
    195526: "Skidmore",
    195216: "St. Lawrence",
    196866: "Union",
}
# Fixed identity colors — an institution keeps its hue on every slide.
COLOR = {name: CATEGORICAL[i] for i, name in enumerate(NY6.values())}

# Animation pacing, in milliseconds — shared so every slide advances alike.
FRAME_MS = 300
EASE_MS = 100

SOURCE = (
    "Source: IPEDS Finance survey (F2, private nonprofit / FASB); "
    "full-time enrollment from IPEDS Fall Enrollment (EF), taken from the fall "
    "term inside each fiscal year (FY2023-24 pairs with Fall 2023)."
)


def fy(year) -> str:
    """Finance fiscal-year label: 2024 -> '2023-24'."""
    y = int(year)
    return f"{y - 1}-{y % 100:02d}"


@st.cache_data(ttl=3600)
def deck_data():
    """Finance + full-time enrollment for the NY6, one query for the whole deck."""
    ids = ", ".join(str(u) for u in NY6)
    df = query(
        f"""
        SELECT f.unitid, f.year,
               CAST(f.f2b02   AS DOUBLE) AS expenses,
               CAST(f.f2d01   AS DOUBLE) AS tuition,
               CAST(f.f2h02   AS DOUBLE) AS endowment,
               CAST(e.eftotlt AS BIGINT) AS ft_enrollment
        FROM f2 f
        -- Fall enrollment is offset one year on purpose. IPEDS labels the
        -- finance file by fiscal-year END (F2324 -> year 2024 = Jul 2023-Jun
        -- 2024) but the fall file by term (EF2024A -> Fall 2024, which begins
        -- the NEXT fiscal year). The fall term inside FY2324 is Fall 2023.
        LEFT JOIN ef_a e
          ON f.unitid = e.unitid AND e.year = f.year - 1 AND e.efalevel = 21
        WHERE f.unitid IN ({ids}) AND f.year >= ?
        ORDER BY f.year, f.unitid
        """,
        (START_YEAR,),
    )
    df["Institution"] = df["unitid"].map(NY6)
    df["FY"] = df["year"].map(fy)
    return df.dropna(subset=["expenses", "ft_enrollment"])


# --- Factoids ---------------------------------------------------------------
# Tiles are capped at one row: past four or five, a KPI strip stops being read
# and starts being scanned, and the slide has no single number to remember.
MAX_FACTOIDS = 5
FACTOID_KEY = "deck_factoids"


def _normalize(item) -> tuple[str, str, str | None]:
    """Accept (label, value) or (label, value, help) — dicts too, for clarity."""
    if isinstance(item, dict):
        return item["label"], item["value"], item.get("help")
    label, value, *rest = item
    return label, value, (rest[0] if rest else None)


def slide_factoids(slide) -> list[tuple[str, str, str | None]]:
    """Resolve a slide's factoids: the `factoids()` function, else `FACTOIDS`.

    The callable wins because a computed number is the common case — a constant
    is only right for a figure that cannot move.
    """
    fn = getattr(slide, "factoids", None)
    items = fn() if callable(fn) else getattr(slide, "FACTOIDS", None)
    return [_normalize(i) for i in (items or [])]


def _factoid_css() -> str:
    """Tile styling, scoped to the row's own `st-key-` class.

    The value is set in Cera Stencil Pro, which the brand standards reserve for
    display type and graphic callouts — a factoid number is exactly that. The
    label stays Cera Pro: stencil letterforms are cut through, which reads well
    at 2rem and badly at 0.8rem, and the standards bar stencil from body copy.
    """
    return f"""<style>
        .st-key-{FACTOID_KEY} {{ gap: 0.75rem; }}
        .st-key-{FACTOID_KEY} .deck-factoid {{
            background-color: {SURFACE};
            border: 1px solid {GRID};
            border-top: 4px solid {BRAND["green"]};
            padding: 0.7rem 0.9rem 0.8rem;
            height: 100%;
        }}
        .st-key-{FACTOID_KEY} .deck-factoid-label {{
            font-family: {FONT_FAMILY};
            font-size: 0.8rem;
            font-weight: 500;
            color: {TEXT_SECONDARY};
            line-height: 1.3;
        }}
        .st-key-{FACTOID_KEY} .deck-factoid-value {{
            font-family: {DISPLAY_FONT_FAMILY};
            /* Bold (700) — Black (900) is available but too dense at this size. */
            font-weight: 700;
            font-size: 2.1rem;
            line-height: 1.15;
            color: {BRAND["green"]};
            margin-top: 0.25rem;
            /* Stencil cuts read as uneven spacing in a run of digits. */
            letter-spacing: 0.01em;
        }}
    </style>"""


def factoid_row(items) -> None:
    """Draw factoids as one row of KPI tiles, values in the display face.

    Built from markup rather than `st.metric` because the value has to carry a
    different font family than the label, which st.metric gives no hook for
    short of styling its internal testids. Values and labels are plain strings,
    so nothing here needs markdown.
    """
    items = [_normalize(i) for i in items][:MAX_FACTOIDS]
    if not items:
        return
    # Re-emitted each run: Streamlit rebuilds the element tree, so a style block
    # written once would not survive the next rerun.
    st.markdown(_factoid_css(), unsafe_allow_html=True)
    with st.container(key=FACTOID_KEY):
        for col, (label, value, help_text) in zip(st.columns(len(items)), items):
            tip = f' title="{html.escape(str(help_text), quote=True)}"' if help_text else ""
            col.markdown(
                f'<div class="deck-factoid"{tip}>'
                f'<div class="deck-factoid-label">{html.escape(str(label))}</div>'
                f'<div class="deck-factoid-value">{html.escape(str(value))}</div>'
                "</div>",
                unsafe_allow_html=True,
            )


# --- Slide callouts ---------------------------------------------------------
# st.info / st.warning paint themselves from Streamlit's own semantic blue and
# yellow, neither of which is an HWS brand color — so the deck's two most
# prominent pieces of prose were the only off-palette elements on the page.
# These callouts are ordinary st.container(border) blocks repainted from the
# brand tokens: takeaway on green (the primary), caveat on orange (the brand's
# caution hue). The fill is solid and the text white, so from the back of a room
# the two conclusions on the slide read as blocks before they read as words; the
# matching 10% tint stays on as a light left rule against the solid field.
#
# One padding pair for both callouts, named so the vertical value is stated once
# and cannot drift apart between the top and the bottom of the block.
CALLOUT_PAD_Y = "0.85rem"
CALLOUT_PAD_X = "1.1rem"

# (kind -> fill, edge rule, icon)
CALLOUTS = {
    "takeaway": (CALLOUT_FILL["takeaway"], SURFACE_ALT, "💡"),
    "caveat": (CALLOUT_FILL["caveat"], SURFACE_WARN, "⚠️"),
}


def _callout_css() -> str:
    """Scoped rules keyed off the container's own `st-key-<key>` class.

    Styling through the key class is the supported hook — targeting Streamlit's
    internal alert testids would break on any release that reshuffles the DOM.
    Corners stay square to match `baseRadius = "none"` in config.toml.
    """
    blocks = "".join(
        f"""
        .st-key-deck_callout_{kind} {{
            background-color: {fill};
            border: none;
            border-left: 4px solid {edge};
            padding: {CALLOUT_PAD_Y} {CALLOUT_PAD_X};
            border-radius: 0;
        }}
        /* Streamlit wraps markdown several levels deep — stVerticalBlock,
           then stElementContainer, then stMarkdown — and the wrappers carry
           row gaps and margins of their own. Zeroing only the outermost one
           leaves the rest, which lands as extra space at the top and makes the
           fill look bottom-tight however symmetric the padding is. The
           descendant selector reaches every level, so the container's padding
           is the only vertical spacing left. */
        .st-key-deck_callout_{kind} div {{
            gap: 0;
            padding: 0;
            margin: 0;
        }}
        .st-key-deck_callout_{kind} p {{
            color: {ON_ACCENT};
            /* Zeroed top *and* bottom: Streamlit's markdown paragraph carries
               an asymmetric default margin, which on a solid fill shows up as
               a visibly thicker band under the text than over it. With both at
               zero the container's own padding is the only spacing, so the
               text sits centered in the block. */
            margin: 0;
        }}
        /* Links and inline code inherit the fill's foreground too, or they
           revert to the light-surface ink and vanish into the block. */
        .st-key-deck_callout_{kind} a,
        .st-key-deck_callout_{kind} code {{
            color: {ON_ACCENT};
        }}"""
        for kind, (fill, edge, _) in CALLOUTS.items()
    )
    return f"<style>{blocks}</style>"


def callout(kind: str, text: str) -> None:
    """Draw a brand-colored slide callout. `kind` is a key of CALLOUTS.

    The body goes through st.markdown untouched, so slide prose keeps its
    markdown — including the `\\$` escaping the module docstring calls for.
    Wrapping the text in raw HTML instead would silence that formatting.
    """
    _fill, _edge, icon = CALLOUTS[kind]
    # Re-emitted every run on purpose: Streamlit rebuilds the element tree each
    # rerun, so a style block guarded behind a session flag would vanish on the
    # second run. Duplicate identical <style> tags are inert.
    st.markdown(_callout_css(), unsafe_allow_html=True)
    # One callout of each kind per slide, so the key stays unique per rerun.
    with st.container(key=f"deck_callout_{kind}"):
        st.markdown(f"{icon} {text}")


def play_controls(fig, *, y=1.12) -> None:
    """Attach Play/Pause buttons with the deck's shared pacing.

    px.* animations ship their own buttons but at Plotly's default speed; this
    replaces them so hand-built go.Figure frames and px figures advance alike.
    """
    fig.update_layout(
        updatemenus=[dict(
            type="buttons", direction="left", showactive=False,
            x=0, xanchor="left", y=y, yanchor="bottom",
            pad=dict(t=0, r=10), bgcolor=SURFACE,
            bordercolor=GRID, borderwidth=1, font=dict(size=12),
            buttons=[
                dict(label="▶  Play", method="animate",
                     args=[None, dict(frame=dict(duration=FRAME_MS, redraw=True),
                                      transition=dict(duration=EASE_MS,
                                                      easing="cubic-in-out"),
                                      fromcurrent=True, mode="immediate")]),
                dict(label="❚❚  Pause", method="animate",
                     args=[[None], dict(frame=dict(duration=0, redraw=False),
                                        transition=dict(duration=0),
                                        mode="immediate")]),
            ],
        )],
    )
