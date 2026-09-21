"""SensyGent — a warm, free, AI companion that helps you manage your mood.

The package is intentionally dependency-light and works with **zero API keys**
thanks to the :mod:`sensy.localcare` engine, which turns on the moment you open
the app. If you *do* have a free LLM key (Groq / Google AI Studio / OpenRouter),
SensyGent automatically upgrades to a full conversational brain.
"""

from __future__ import annotations

__all__ = ["__version__", "APP_NAME", "TAGLINE"]

__version__ = "1.0.0"
APP_NAME = "SensyGent"
TAGLINE = "A gentle companion for heavy days."
