"""Configuration: defaults, preferences and companion assembly.

Precedence for anything configurable:

1. ``st.secrets`` (what you set on Streamlit Cloud) — highest priority
2. environment variables
3. what you chose in the sidebar (stored locally in SQLite)
4. the defaults in :data:`DEFAULTS`

API keys entered in the sidebar are only kept for the lifetime of the browser
session unless you write them into ``.streamlit/secrets.toml``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from . import llm, voice
from .companion import LENGTHS, PERSONAS, STYLES, Companion, resolve_persona
from .palette import DEFAULT_THEME, theme_names

DEFAULTS: Dict[str, str] = {
    "persona": "aanya",
    "display_name": "",
    "style": "gentle",
    "length": "balanced",
    "theme": DEFAULT_THEME,
    "voice_enabled": "on",
    "autospeak": "off",
    "voice_id": voice.default_voice_for("female"),
    "voice_rate": "Natural",
    "tts_engine": "auto",
    "provider": "",
    "model": "",
    "endpoint": "",
    "temperature": "0.85",
    "warm_mode": "on",
}

BOOL_KEYS = {"voice_enabled", "autospeak", "warm_mode"}


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def secrets_get(secrets: Optional[object], key: str, default: str = "") -> str:
    """Safe lookup inside Streamlit secrets (which may not exist at all)."""
    if secrets is None:
        return default
    try:
        value = secrets.get(key)  # type: ignore[union-attr]
    except Exception:
        for name in (key, key.upper()):
            try:
                value = secrets[name]  # type: ignore[index]
            except Exception:
                continue
            if value:
                return str(value)
        return default
    return str(value) if value else default


def resolved_provider(
    store,
    secrets: Optional[object] = None,
    session_key: str = "",
) -> Dict[str, str]:
    """Work out which brain to use, in priority order."""
    provider = secrets_get(secrets, "provider") or store.get_pref("provider", "")
    model = secrets_get(secrets, "model") or store.get_pref("model", "")
    endpoint = secrets_get(secrets, "endpoint") or store.get_pref("endpoint", "")
    api_key = ""

    if not provider:
        # Auto-detect: first provider that has a key available.
        for key in ("groq", "gemini", "openrouter", "deepseek"):
            found = llm.find_key(key, secrets)
            if found:
                provider, api_key = key, found
                break
        else:
            if secrets_get(secrets, "ollama_url"):
                provider, endpoint = "ollama", secrets_get(secrets, "ollama_url")

    if provider and provider in llm.PROVIDERS:
        spec = llm.PROVIDERS[provider]
        model = model or spec.default_model
        endpoint = endpoint or spec.endpoint
        api_key = session_key or llm.find_key(provider, secrets) or api_key
    else:
        provider, model, endpoint, api_key = "", "", "", ""

    return {"provider": provider, "model": model, "endpoint": endpoint, "api_key": api_key or ""}


def build_companion(
    store,
    secrets: Optional[object] = None,
    session_key: str = "",
    persona_key: str = "",
    style: str = "",
    length: str = "",
    temperature: float = 0.85,
    engine=None,
) -> Companion:
    """Assemble a ready-to-talk :class:`~sensy.companion.Companion`."""
    persona_key = persona_key or store.get_pref("persona", DEFAULTS["persona"])
    style = style or store.get_pref("style", DEFAULTS["style"])
    length = length or store.get_pref("length", DEFAULTS["length"])
    resolved = resolved_provider(store, secrets, session_key)

    companion = Companion(
        persona=resolve_persona(persona_key),
        style=style if style in STYLES else DEFAULTS["style"],
        length=length if length in LENGTHS else DEFAULTS["length"],
        display_name=store.get_pref("display_name", "") or secrets_get(secrets, "companion_name", ""),
        provider_key=resolved["provider"],
        model=resolved["model"],
        api_key=resolved["api_key"],
        endpoint=resolved["endpoint"],
        temperature=temperature,
        mood_note=mood_context(store),
    )
    if engine is not None:
        companion.engine = engine
    companion.engine.name = companion.name
    return companion


def mood_context(store) -> str:
    """Free-text summary of recent check-ins, injected into the prompt."""
    try:
        return store.mood_prompt_context()
    except Exception:
        return ""


@dataclass
class Settings:
    """Snapshot of everything the sidebar can change."""

    persona: str = DEFAULTS["persona"]
    display_name: str = ""
    style: str = DEFAULTS["style"]
    length: str = DEFAULTS["length"]
    theme: str = DEFAULTS["theme"]
    voice_enabled: bool = True
    autospeak: bool = False
    voice_id: str = ""
    voice_rate: str = "Natural"
    tts_engine: str = "auto"
    provider: str = ""
    model: str = ""
    endpoint: str = ""
    temperature: float = 0.85
    warm_mode: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_store(cls, store, secrets: Optional[object] = None) -> "Settings":
        data = {}
        for key, default in DEFAULTS.items():
            value = store.get_pref(key, "")
            if value == "":
                value = secrets_get(secrets, key, default)
            data[key] = value
        return cls(
            persona=data["persona"],
            display_name=data["display_name"],
            style=data["style"],
            length=data["length"],
            theme=data["theme"] if data["theme"] in theme_names() else DEFAULTS["theme"],
            voice_enabled=_as_bool(data["voice_enabled"], True),
            autospeak=_as_bool(data["autospeak"], False),
            voice_id=data["voice_id"] or voice.default_voice_for(
                resolve_persona(data["persona"]).default_voice_hint
            ),
            voice_rate=data["voice_rate"],
            tts_engine=data["tts_engine"],
            provider=data["provider"],
            model=data["model"],
            endpoint=data["endpoint"],
            temperature=float(data["temperature"] or 0.85),
            warm_mode=_as_bool(data["warm_mode"], True),
        )

    def save(self, store) -> None:
        for key, value in asdict(self).items():
            if key == "extra":
                continue
            store.set_pref(key, str(value))
