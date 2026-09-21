"""Voice — SensyGent's talking skills.

Free text-to-speech with two hands:

* **edge-tts** (primary) — Microsoft Edge's neural voices. Genuinely lovely,
  no API key, no cost, ~400 voices across 70+ languages.
* **gTTS** (fallback) — Google Translate's voice. Also free, also keyless.

Both need outbound internet. If neither works, the app quietly stays silent —
nothing else breaks.

Voices are filtered by the companion's pronouns so "she" sounds like she.
These are voice *characters*, not the companion's gender identity.
"""

from __future__ import annotations

import asyncio
import io
import re
from dataclasses import dataclass
from typing import Dict, List, NamedTuple, Optional, Tuple

# --------------------------------------------------------------------------- #
# Voice catalogue (curated — keyless, neural, free)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Voice:
    id: str
    label: str
    gender: str
    locale: str
    flag: str = ""


CATALOGUE: List[Voice] = [
    # English — India
    Voice("en-IN-NeerjaNeural", "Neerja · English (India)", "female", "en-IN", "🇮🇳"),
    Voice("en-IN-PrabhatNeural", "Prabhat · English (India)", "male", "en-IN", "🇮🇳"),
    # English — US
    Voice("en-US-AriaNeural", "Aria · English (US)", "female", "en-US", "🇺🇸"),
    Voice("en-US-JennyNeural", "Jenny · English (US)", "female", "en-US", "🇺🇸"),
    Voice("en-US-EmmaNeural", "Emma · English (US)", "female", "en-US", "🇺🇸"),
    Voice("en-US-MichelleNeural", "Michelle · English (US)", "female", "en-US", "🇺🇸"),
    Voice("en-US-GuyNeural", "Guy · English (US)", "male", "en-US", "🇺🇸"),
    Voice("en-US-AndrewNeural", "Andrew · English (US)", "male", "en-US", "🇺🇸"),
    Voice("en-US-BrianNeural", "Brian · English (US)", "male", "en-US", "🇺🇸"),
    # English — UK
    Voice("en-GB-SoniaNeural", "Sonia · English (UK)", "female", "en-GB", "🇬🇧"),
    Voice("en-GB-LibbyNeural", "Libby · English (UK)", "female", "en-GB", "🇬🇧"),
    Voice("en-GB-RyanNeural", "Ryan · English (UK)", "male", "en-GB", "🇬🇧"),
    Voice("en-GB-ThomasNeural", "Thomas · English (UK)", "male", "en-GB", "🇬🇧"),
    # Beyond English
    Voice("hi-IN-SwaraNeural", "Swara · हिन्दी", "female", "hi-IN", "🇮🇳"),
    Voice("hi-IN-MadhurNeural", "Madhur · हिन्दी", "male", "hi-IN", "🇮🇳"),
    Voice("es-ES-ElviraNeural", "Elvira · Español", "female", "es-ES", "🇪🇸"),
    Voice("es-MX-DaliaNeural", "Dalia · Español (MX)", "female", "es-MX", "🇲🇽"),
    Voice("fr-FR-DeniseNeural", "Denise · Français", "female", "fr-FR", "🇫🇷"),
    Voice("fr-FR-HenriNeural", "Henri · Français", "male", "fr-FR", "🇫🇷"),
    Voice("de-DE-KatjaNeural", "Katja · Deutsch", "female", "de-DE", "🇩🇪"),
    Voice("de-DE-ConradNeural", "Conrad · Deutsch", "male", "de-DE", "🇩🇪"),
    Voice("pt-BR-FranciscaNeural", "Francisca · Português", "female", "pt-BR", "🇧🇷"),
    Voice("it-IT-ElsaNeural", "Elsa · Italiano", "female", "it-IT", "🇮🇹"),
    Voice("ja-JP-NanamiNeural", "Nanami · 日本語", "female", "ja-JP", "🇯🇵"),
    Voice("ko-KR-SunHiNeural", "SunHi · 한국어", "female", "ko-KR", "🇰🇷"),
    Voice("zh-CN-XiaoxiaoNeural", "Xiaoxiao · 中文", "female", "zh-CN", "🇨🇳"),
    Voice("ar-EG-SalmaNeural", "Salma · العربية", "female", "ar-EG", "🇪🇬"),
    Voice("ru-RU-SvetlanaNeural", "Svetlana · Русский", "female", "ru-RU", "🇷🇺"),
    Voice("bn-IN-TanishaaNeural", "Tanishaa · বাংলা", "female", "bn-IN", "🇧🇩"),
    Voice("ta-IN-PallaviNeural", "Pallavi · தமிழ்", "female", "ta-IN", "🇮🇳"),
    Voice("mr-IN-AarohiNeural", "Aarohi · मराठी", "female", "mr-IN", "🇮🇳"),
]

VOICE_INDEX: Dict[str, Voice] = {voice.id: voice for voice in CATALOGUE}

RATE_OPTIONS: Dict[str, str] = {
    "Very slow": "-25%",
    "Slow": "-12%",
    "Natural": "+0%",
    "Brisk": "+10%",
}

# --------------------------------------------------------------------------- #
# Text preparation
# --------------------------------------------------------------------------- #

_EMOJI = re.compile(
    "[" "\U0001F300-\U0001FAFF" "\U00002700-\U000027BF" "\U0001F000-\U0001F2FF"
    "\U00002600-\U000026FF" "\U0001F900-\U0001F9FF" "\u200d\u2640\u2642\ufe0f" "]",
    flags=re.UNICODE,
)


def speakable(text: str) -> str:
    """Strip markdown/emoji so the voice sounds like a person, not a README."""
    if not text:
        return ""
    clean = text
    clean = re.sub(r"```.*?```", " ", clean, flags=re.DOTALL)
    clean = re.sub(r"`([^`]*)`", r"\1", clean)
    clean = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", clean)
    clean = re.sub(r"^\s{0,3}#{1,6}\s*", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"(\*\*|__|\*|_|~~)", "", clean)
    clean = re.sub(r"^\s*[-*+]\s+", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"^\s*>\s?", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"———+", " ", clean)
    clean = _EMOJI.sub(" ", clean)
    clean = re.sub(r"[ \t]{2,}", " ", clean)
    clean = re.sub(r"\n{2,}", "\n", clean)
    # Long dashes read badly; commas breathe better.
    clean = clean.replace(" — ", ", ").replace(" – ", ", ")
    return clean.strip()


def chunk_text(text: str, limit: int = 280) -> List[str]:
    """Split long text on sentence boundaries for smoother synthesis."""
    text = speakable(text)
    if len(text) <= limit:
        return [text] if text else []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= limit:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


# --------------------------------------------------------------------------- #
# Engines
# --------------------------------------------------------------------------- #

def _run_async(coro):
    """Run a coroutine safely even if a loop is already running somewhere."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    # A loop is running (rare in Streamlit): use a separate thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


def edge_tts_available() -> bool:
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


def gtts_available() -> bool:
    try:
        from gtts import gTTS  # noqa: F401
        return True
    except ImportError:
        return False


def synthesise_edge(text: str, voice: str, rate: str = "+0%", volume: str = "+0%") -> Optional[bytes]:
    """Neural speech via edge-tts. Returns MP3 bytes or None."""
    if not edge_tts_available():
        return None
    import edge_tts

    async def _collect() -> bytes:
        communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
        buffer = bytearray()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                buffer.extend(chunk["data"])
        return bytes(buffer)

    try:
        audio = _run_async(_collect())
    except Exception:
        return None
    return audio or None


def synthesise_gtts(text: str, lang: str = "en", slow: bool = False) -> Optional[bytes]:
    """Fallback speech via gTTS. Returns MP3 bytes or None."""
    if not gtts_available():
        return None
    try:
        from gtts import gTTS

        buffer = io.BytesIO()
        gTTS(text=text, lang=lang, slow=slow).write_to_fp(buffer)
        return buffer.getvalue() or None
    except Exception:
        return None


def pyttsx3_available() -> bool:
    try:
        import pyttsx3  # noqa: F401
        return True
    except Exception:
        return False


def synthesise_offline(text: str) -> Optional[bytes]:
    """Last resort: the operating system's own voice. No internet needed.

    Only used if ``pyttsx3`` happens to be installed (it is optional; on Linux
    it also needs espeak-ng). Returns WAV bytes, or None if unavailable.
    """
    if not pyttsx3_available():
        return None
    import os
    import tempfile

    handle, path = tempfile.mkstemp(suffix=".wav")
    os.close(handle)
    try:
        import pyttsx3

        engine = pyttsx3.init()
        engine.save_to_file(text, path)
        engine.runAndWait()
        with open(path, "rb") as file:
            data = file.read()
        return data or None
    except Exception:
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


class Speech(NamedTuple):
    """The result of a synthesis attempt."""

    audio: Optional[bytes]
    engine: str
    mime: str


def synthesize(
    text: str,
    voice: str = "en-IN-NeerjaNeural",
    rate: str = "+0%",
    prefer: str = "auto",
) -> Speech:
    """Synthesise speech: edge-tts -> gTTS -> the device's own voice.

    Never raises. ``Speech.audio`` is None when nothing worked, and the app
    degrades to silence instead of breaking.
    """
    chunks = chunk_text(text)
    if not chunks:
        return Speech(None, "empty", "audio/mp3")

    joined = " ".join(chunks)

    if prefer in {"auto", "edge"} and edge_tts_available():
        audio = synthesise_edge(joined, voice, rate)
        if audio:
            return Speech(audio, "edge-tts neural voice", "audio/mp3")

    if prefer in {"auto", "edge", "gtts"} and gtts_available():
        lang = VOICE_INDEX.get(voice, Voice("", "", "", "en-US")).locale.split("-")[0] or "en"
        audio = synthesise_gtts(joined, lang=lang, slow=rate.startswith("-"))
        if audio:
            return Speech(audio, "gTTS", "audio/mp3")

    audio = synthesise_offline(joined)
    if audio:
        return Speech(audio, "your device's voice", "audio/wav")

    return Speech(None, "unavailable", "audio/mp3")


def voices_for(gender_hint: str = "any", locale_prefix: str = "") -> List[Voice]:
    """Filter the catalogue by gender hint and/or locale prefix."""
    result = []
    for voice in CATALOGUE:
        if gender_hint in {"female", "male"} and voice.gender != gender_hint:
            continue
        if locale_prefix and not voice.locale.startswith(locale_prefix):
            continue
        result.append(voice)
    return result or CATALOGUE


def default_voice_for(gender_hint: str) -> str:
    """A sensible default voice id for a persona's pronouns."""
    preference = {
        "female": ["en-IN-NeerjaNeural", "en-US-AriaNeural", "en-US-JennyNeural"],
        "male": ["en-IN-PrabhatNeural", "en-US-AndrewNeural", "en-GB-RyanNeural"],
        "neutral": ["en-US-AriaNeural", "en-GB-SoniaNeural", "en-IN-NeerjaNeural"],
    }.get(gender_hint, ["en-US-AriaNeural"])
    for candidate in preference:
        if candidate in VOICE_INDEX:
            return candidate
    return CATALOGUE[0].id


def engine_status() -> Dict[str, bool]:
    """Which speech engines are importable right now."""
    return {
        "edge-tts": edge_tts_available(),
        "gTTS": gtts_available(),
        "device voice": pyttsx3_available(),
    }
