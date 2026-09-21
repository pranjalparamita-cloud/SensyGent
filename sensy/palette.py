"""Colour themes for SensyGent.

Every theme is a flat dictionary of CSS custom properties. :func:`theme_css`
renders them into a ``:root`` block so the stylesheet can stay declarative.
"""

from __future__ import annotations

from typing import Dict, Tuple

Theme = Dict[str, str]

THEMES: Dict[str, Theme] = {
    "aurora": {
        "label": "Aurora Night",
        "swatch": "#8b7bf7",
        "bg": "#07070f",
        "bg_2": "#0d0d1c",
        "surface": "rgba(21, 21, 41, 0.62)",
        "surface_2": "rgba(30, 30, 58, 0.55)",
        "border": "rgba(139, 123, 247, 0.20)",
        "text": "#eef0ff",
        "muted": "#9aa0c4",
        "primary": "#8b7bf7",
        "primary_2": "#4fd1c5",
        "accent": "#ff8fc7",
        "glow": "rgba(139, 123, 247, 0.45)",
        "orb_1": "#8b7bf7",
        "orb_2": "#4fd1c5",
        "orb_3": "#ff8fc7",
        "good": "#5ee6a8",
        "warn": "#ffc46b",
        "bad": "#ff7a8a",
    },
    "blush": {
        "label": "Blush Dawn",
        "swatch": "#f4739b",
        "bg": "#140910",
        "bg_2": "#1e0d17",
        "surface": "rgba(48, 22, 36, 0.60)",
        "surface_2": "rgba(64, 28, 46, 0.50)",
        "border": "rgba(244, 115, 155, 0.22)",
        "text": "#fff0f5",
        "muted": "#c9a2b4",
        "primary": "#f4739b",
        "primary_2": "#ffb36b",
        "accent": "#c79bff",
        "glow": "rgba(244, 115, 155, 0.42)",
        "orb_1": "#ff8fb1",
        "orb_2": "#ffb36b",
        "orb_3": "#c79bff",
        "good": "#7fe3b0",
        "warn": "#ffcb7a",
        "bad": "#ff8095",
    },
    "forest": {
        "label": "Forest Zen",
        "swatch": "#4fd1a5",
        "bg": "#06120f",
        "bg_2": "#0a1c17",
        "surface": "rgba(16, 42, 34, 0.60)",
        "surface_2": "rgba(22, 55, 44, 0.50)",
        "border": "rgba(79, 209, 165, 0.20)",
        "text": "#eafff6",
        "muted": "#8fbcac",
        "primary": "#4fd1a5",
        "primary_2": "#7fd7ff",
        "accent": "#d9e86b",
        "glow": "rgba(79, 209, 165, 0.38)",
        "orb_1": "#4fd1a5",
        "orb_2": "#7fd7ff",
        "orb_3": "#d9e86b",
        "good": "#7ee7b3",
        "warn": "#f0d07a",
        "bad": "#ff9a86",
    },
    "sunset": {
        "label": "Sunset Warm",
        "swatch": "#ff9a62",
        "bg": "#140d06",
        "bg_2": "#20130a",
        "surface": "rgba(52, 30, 14, 0.60)",
        "surface_2": "rgba(70, 40, 18, 0.50)",
        "border": "rgba(255, 154, 98, 0.22)",
        "text": "#fff5ec",
        "muted": "#d3ab8d",
        "primary": "#ff9a62",
        "primary_2": "#ffd166",
        "accent": "#ff6b81",
        "glow": "rgba(255, 154, 98, 0.40)",
        "orb_1": "#ff9a62",
        "orb_2": "#ffd166",
        "orb_3": "#ff6b81",
        "good": "#a8e6a1",
        "warn": "#ffd166",
        "bad": "#ff7b72",
    },
    "daylight": {
        "label": "Soft Daylight",
        "swatch": "#6b7cff",
        "bg": "#f4f5fd",
        "bg_2": "#e9ecfb",
        "surface": "rgba(255, 255, 255, 0.78)",
        "surface_2": "rgba(255, 255, 255, 0.62)",
        "border": "rgba(107, 124, 255, 0.20)",
        "text": "#1c2040",
        "muted": "#5f6689",
        "primary": "#6b7cff",
        "primary_2": "#00b3a4",
        "accent": "#e0578f",
        "glow": "rgba(107, 124, 255, 0.28)",
        "orb_1": "#8f9bff",
        "orb_2": "#7fe3d6",
        "orb_3": "#ffb0cd",
        "good": "#12a06a",
        "warn": "#c98410",
        "bad": "#dc4a5d",
        "scheme": "light",
    },
}

DEFAULT_THEME = "aurora"


def get_theme(name: str) -> Theme:
    """Return a theme by key, falling back to the default."""
    return THEMES.get(name, THEMES[DEFAULT_THEME])


def theme_css(name: str) -> str:
    """Render a theme as a ``:root`` custom-property block."""
    theme = get_theme(name)
    lines = []
    for key, value in theme.items():
        if key in {"label", "swatch"}:
            continue
        lines.append(f"--sg-{key.replace('_', '-')}: {value};")
    body = "\n  ".join(lines)
    scheme = theme.get("scheme", "dark")
    return f":root {{\n  color-scheme: {scheme};\n  {body}\n}}"


def theme_names() -> Tuple[str, ...]:
    return tuple(THEMES.keys())
