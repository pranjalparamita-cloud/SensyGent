"""Beautiful HTML components for SensyGent.

Streamlit's built-in widgets are functional but plain, so the app renders its
own design system: glassmorphic cards, gradient orbs, animated breathing
circles, a gratitude jar. Each helper here returns an HTML string which
:func:`render` injects into the page.

Content is HTML-escaped before it goes in, so nothing you type can break the
layout.
"""

from __future__ import annotations

import html as _html
import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import streamlit as st

from . import palette

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"
CSS_FILE = ASSET_DIR / "styles.css"

_CACHE: dict = {}


_IMPORT_RE = re.compile(r"^\s*@import[^;]+;", re.MULTILINE)


def load_css(theme: str = palette.DEFAULT_THEME) -> str:
    """Read the stylesheet, with the theme's variables injected.

    Order matters: CSS requires ``@import`` (the web fonts) to come before any
    other rule, so the imports are hoisted above the ``:root`` block — otherwise
    browsers silently drop the fonts.
    """
    key = str(CSS_FILE)
    if key not in _CACHE:
        try:
            raw = CSS_FILE.read_text(encoding="utf-8")
        except OSError:
            raw = "/* stylesheet missing */"
        imports = _IMPORT_RE.findall(raw)
        _CACHE[key] = (_IMPORT_RE.sub("", raw), imports)
    body, imports = _CACHE[key]
    return f"{chr(10).join(imports)}\n{palette.theme_css(theme)}\n{body}"


def font_links() -> str:
    """Preconnect + stylesheet links for the web fonts (belt and braces)."""
    return (
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        "family=Plus+Jakarta+Sans:ital,wght@0,300..800;1,300..800"
        "&family=Fraunces:ital,opsz,wght@0,9..144,300..700;1,9..144,300..700"
        "&family=JetBrains+Mono:wght@400;600&display=swap\">"
    )


def inject_theme(theme: str = palette.DEFAULT_THEME) -> None:
    """Install the whole design system: fonts, theme variables, stylesheet."""
    st.markdown(font_links(), unsafe_allow_html=True)
    st.markdown(f"<style>{load_css(theme)}</style>", unsafe_allow_html=True)


def render(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def esc(text: object) -> str:
    return _html.escape(str(text if text is not None else ""), quote=True)


# --------------------------------------------------------------------------- #
# Building blocks
# --------------------------------------------------------------------------- #

def orb(emoji: str = "🌸", size: str = "") -> str:
    return f'<div class="sg-orb {esc(size)}"><span>{esc(emoji)}</span></div>'


def hero(
    title: str,
    subtitle: str,
    eyebrow: str = "",
    emoji: str = "🌸",
    chips: Sequence[str] = (),
) -> str:
    chip_html = ""
    if chips:
        chip_html = '<div class="sg-chips">' + "".join(
            chip if chip.startswith("<") else f'<span class="sg-chip">{chip}</span>'
            for chip in chips
        ) + "</div>"
    eyebrow_html = f'<div class="sg-hero-eyebrow">{esc(eyebrow)}</div>' if eyebrow else ""
    return f"""
<div class="sg-hero">
  {orb(emoji)}
  <div class="sg-hero-body">
    {eyebrow_html}
    <div class="sg-hero-title">{esc(title)}</div>
    <p class="sg-hero-sub">{esc(subtitle)}</p>
    {chip_html}
  </div>
</div>"""


def chip(text: str, kind: str = "", icon: str = "") -> str:
    classes = "sg-chip"
    if kind:
        classes += f" sg-chip-{kind}"
    label = f"{icon} {esc(text)}" if icon else esc(text)
    return f'<span class="{classes}">{label}</span>'


def chips(items: Iterable[str]) -> str:
    return '<div class="sg-chips">' + "".join(items) + "</div>"


def section(title: str, icon: str = "") -> str:
    icon_html = f'<span class="sg-section-icon">{esc(icon)}</span>' if icon else ""
    return (
        f'<div class="sg-section">{icon_html}<h3>{esc(title)}</h3>'
        f'<div class="sg-section-line"></div></div>'
    )


def card(body: str, title: str = "") -> str:
    title_html = f'<div class="sg-card-title">{esc(title)}</div>' if title else ""
    return f'<div class="sg-card">{title_html}{body}</div>'


def stat(value: str, label: str, sub: str = "") -> str:
    sub_html = f'<div class="sg-stat-sub">{esc(sub)}</div>' if sub else ""
    return (
        '<div class="sg-card">'
        f'<div class="sg-card-title">{esc(label)}</div>'
        f'<div class="sg-stat-value">{esc(value)}</div>'
        f"{sub_html}</div>"
    )


def quote(text: str, author: str = "SensyGent") -> str:
    return (
        f'<div class="sg-quote">{esc(text)}'
        f'<span class="sg-quote-author">{esc(author)}</span></div>'
    )


def callout(text: str, icon: str = "💡", kind: str = "") -> str:
    classes = "sg-callout" + (f" sg-callout-{kind}" if kind else "")
    return (
        f'<div class="{classes}"><div class="sg-callout-icon">{esc(icon)}</div>'
        f"<div>{text}</div></div>"
    )


def mood_dots(score: int, emojis: Sequence[str] = ()) -> str:
    """Show a 1-10 scale with the current score highlighted."""
    from .store import MOOD_EMOJI

    emojis = emojis or [MOOD_EMOJI[i] for i in range(1, 11)]
    dots = []
    for index, emoji in enumerate(emojis, start=1):
        active = " sg-dot-on" if index == score else ""
        dots.append(f'<span class="sg-dot{active}">{emoji}</span>')
    return '<div class="sg-dots">' + "".join(dots) + "</div>"


def meter(percent: float, label: str = "") -> str:
    width = max(0.0, min(100.0, percent))
    label_html = f'<div class="sg-stat-sub">{esc(label)}</div>' if label else ""
    return (
        f'<div class="sg-meter"><div class="sg-meter-fill" style="width:{width:.1f}%"></div></div>'
        f"{label_html}"
    )


def breathing_circle(label: str = "Breathe", cycle_seconds: float = 10.0) -> str:
    return f"""
<div class="sg-breathe-wrap">
  <div class="sg-breathe" style="--sg-dur:{cycle_seconds:.1f}s">
    <div class="sg-breathe-halo"></div>
    <span class="sg-breathe-label">{esc(label)}</span>
  </div>
</div>"""


def gratitude_jar(count: int, cap: int = 60) -> str:
    visible = min(count, cap)
    notes = "".join('<div class="sg-note"></div>' for _ in range(visible))
    if visible == 0:
        notes = (
            '<div class="sg-stat-sub" style="margin:auto">'
            "The jar is empty for now. Add one small good thing and watch it fill.</div>"
        )
    return f'<div class="sg-jar">{notes}</div>'


def entry(meta: str, body: str, accent: str = "") -> str:
    style = f' style="border-left-color:{esc(accent)}"' if accent else ""
    return (
        f'<div class="sg-entry"{style}>'
        f'<div class="sg-entry-meta">{esc(meta)}</div>'
        f'<div class="sg-entry-body">{esc(body)}</div></div>'
    )


def typing_indicator() -> str:
    return '<div class="sg-typing"><span></span><span></span><span></span></div>'


def footer(persona_name: str = "Sensy") -> str:
    return f"""
<div class="sg-footer">
  <strong>{esc(persona_name)}</strong> is a supportive companion, not a therapist or doctor.
  It can't diagnose anything or replace real care.<br>
  If you're in crisis, please reach out to a human right now —
  <strong>988</strong> (US) · <strong>116 123</strong> (UK) · <strong>14416</strong> (India) ·
  <a href="https://findahelpline.com" target="_blank" rel="noopener">findahelpline.com</a><br>
  <span style="opacity:.7">Everything you write stays on this machine. Built with care by SensyGent.</span>
</div>"""


def sidebar_brand(name: str, tagline: str, emoji: str = "🌸") -> str:
    return f"""
<div class="sg-side-brand">
  <div class="sg-orb sg-orb-sm"><span>{esc(emoji)}</span></div>
  <div class="sg-side-brand-text">
    <div class="sg-side-name">{esc(name)}</div>
    <div class="sg-side-tag">{esc(tagline)}</div>
  </div>
</div>"""


def mood_pill(score: int, label: str = "") -> str:
    from .store import MOOD_LABELS

    kind = "good" if score >= 7 else "warn" if score >= 5 else "bad"
    text = label or f"{score}/10 · {MOOD_LABELS.get(score, '')}"
    return chip(text, kind=kind)
