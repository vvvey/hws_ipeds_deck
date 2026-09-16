"""Presentation deck — one slide per file, driven by this page.

Slides live in `dashboards/deck_slides/`. Every module there named `slide_*.py`
is discovered automatically and ordered by filename, so adding a slide means
dropping in a file — there is no registry to keep in sync. See
`deck_slides/_shared.py` for the contract a slide module implements.

A slide that raises is reported in place, with its traceback, and the rest of the
deck keeps working — a broken chart should never take down a talk mid-flow.
"""
from __future__ import annotations

import importlib
import pkgutil
import traceback
from types import ModuleType

import streamlit as st

from dashboards import deck_slides
from dashboards.deck_slides._shared import SOURCE, callout

SLIDE_KEY = "deck_slide"
JUMP_KEY = "deck_jump"
SLIDE_PREFIX = "slide_"


def _discover() -> list[ModuleType]:
    """Import every deck_slides.slide_*.py, ordered by filename.

    Not cached: importlib already memoizes modules, so re-running is cheap, and
    skipping the cache means a newly added slide file shows up on the next rerun
    instead of needing a restart.
    """
    mods = []
    for info in sorted(pkgutil.iter_modules(deck_slides.__path__),
                       key=lambda m: m.name):
        if not info.name.startswith(SLIDE_PREFIX):
            continue
        mods.append(importlib.import_module(f"{deck_slides.__name__}.{info.name}"))
    return mods


def _valid(mods: list[ModuleType]) -> list[ModuleType]:
    """Drop malformed slides with a visible message rather than a stack trace."""
    good = []
    for m in mods:
        missing = []
        if not hasattr(m, "TITLE"):
            missing.append("`TITLE`")
        # A slide supplies either build() -> figure, or render() to draw its own
        # body (needed when the chart is interactive and must read its own
        # selection state back).
        if not hasattr(m, "build") and not hasattr(m, "render"):
            missing.append("`build` or `render`")
        if missing:
            st.error(
                f"Slide `{m.__name__.split('.')[-1]}` is missing "
                f"{', '.join(missing)} — skipped.",
                icon="⚠️",
            )
        else:
            good.append(m)
    return good


def _step(delta: int, n: int) -> None:
    """Move the deck by delta slides, clamped. Runs as a button callback so the
    new index is set before the script re-runs and the slide is drawn."""
    st.session_state[SLIDE_KEY] = max(
        0, min(n - 1, st.session_state.get(SLIDE_KEY, 0) + delta)
    )


def _make_jump(titles: list[str]):
    def _jump() -> None:
        st.session_state[SLIDE_KEY] = titles.index(st.session_state[JUMP_KEY])
    return _jump


def render() -> None:
    slides = _valid(_discover())
    if not slides:
        st.warning(
            "No slides found. Add a `slide_*.py` module to "
            "`dashboards/deck_slides/`.",
            icon="🎞️",
        )
        return

    n = len(slides)
    idx = min(st.session_state.setdefault(SLIDE_KEY, 0), n - 1)
    slide = slides[idx]
    titles = [s.TITLE for s in slides]

    # --- navigation bar -------------------------------------------------
    prev_col, jump_col, next_col = st.columns([1, 6, 1], vertical_alignment="bottom")
    with prev_col:
        st.button("←  Prev", use_container_width=True, disabled=(idx == 0),
                  on_click=_step, args=(-1, n), key="deck_prev")
    with jump_col:
        # Push the current title into the widget's own state before drawing it.
        # A keyed selectbox reads session_state and ignores `index` on reruns, so
        # without this the box keeps showing the old slide after Prev/Next.
        st.session_state[JUMP_KEY] = slide.TITLE
        st.selectbox(f"Slide {idx + 1} of {n}", options=titles,
                     key=JUMP_KEY, on_change=_make_jump(titles))
    with next_col:
        st.button("Next  →", use_container_width=True, disabled=(idx == n - 1),
                  on_click=_step, args=(1, n), key="deck_next")

    st.progress((idx + 1) / n)

    # --- slide body -----------------------------------------------------
    st.title(slide.TITLE)
    if getattr(slide, "SUBTITLE", None):
        st.caption(slide.SUBTITLE)

    try:
        if hasattr(slide, "render"):
            slide.render()          # slide draws its own body
        else:
            st.plotly_chart(slide.build(), use_container_width=True,
                            key=f"deck_fig_{idx}")
    except Exception:
        st.error(f"Slide `{slide.__name__.split('.')[-1]}` failed to build.",
                 icon="🚨")
        st.code(traceback.format_exc(), language="text")
        return
    if getattr(slide, "TAKEAWAY", None):
        callout("takeaway", slide.TAKEAWAY)
    if getattr(slide, "CAVEAT", None):
        callout("caveat", slide.CAVEAT)
    st.caption(getattr(slide, "SOURCE", SOURCE))
