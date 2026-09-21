"""The companion: persona, prompt construction, and reply orchestration.

This module decides *who* is talking to you (name, pronouns, voice, tone) and
*how* replies get produced — via a free LLM when a key exists, via LocalCare
when it does not.
"""

from __future__ import annotations

import datetime as _dt
import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from . import llm, localcare, mood
from .llm import PROVIDERS, LLMError, Provider
from .mood import Reading

# --------------------------------------------------------------------------- #
# Personas
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Persona:
    key: str
    name: str
    emoji: str
    blurb: str
    pronouns: str          # subject pronouns: she/her, he/him, they/them
    default_voice_hint: str

    @property
    def subject(self) -> str:
        return {"she/her": "she", "he/him": "he", "they/them": "they"}[self.pronouns]

    @property
    def object(self) -> str:
        return {"she/her": "her", "he/him": "him", "they/them": "them"}[self.pronouns]

    @property
    def possessive(self) -> str:
        return {"she/her": "her", "he/him": "his", "they/them": "their"}[self.pronouns]


PERSONAS: Dict[str, Persona] = {
    "aanya": Persona(
        key="aanya", name="Aanya", emoji="🌸", pronouns="she/her",
        blurb="Warm, soft-spoken, endlessly patient. She listens like she has all night.",
        default_voice_hint="female",
    ),
    "aarav": Persona(
        key="aarav", name="Aarav", emoji="🌿", pronouns="he/him",
        blurb="Steady, grounding, quietly funny. He'll sit with you and won't flinch.",
        default_voice_hint="male",
    ),
    "mira": Persona(
        key="mira", name="Mira", emoji="🌙", pronouns="she/her",
        blurb="Gentle and a little poetic. Good at naming feelings you couldn't.",
        default_voice_hint="female",
    ),
    "dev": Persona(
        key="dev", name="Dev", emoji="🔥", pronouns="he/him",
        blurb="Honest, direct, kind underneath. Good when you need someone to say it plainly.",
        default_voice_hint="male",
    ),
    "sky": Persona(
        key="sky", name="Sky", emoji="☁️", pronouns="they/them",
        blurb="Easygoing and non-judgemental. No expectations, no scripts.",
        default_voice_hint="neutral",
    ),
}

STYLES: Dict[str, Dict[str, str]] = {
    "gentle": {
        "label": "Gentle",
        "prompt": (
            "Your tone is soft, unhurried and warm. Short sentences. Lots of warmth, "
            "no platitudes. You speak like a close friend at 2am who is not in a rush."
        ),
    },
    "bright": {
        "label": "Uplifting",
        "prompt": (
            "Your tone is warm but a touch brighter and more encouraging. You notice the "
            "small wins and gently inject hope — never fake cheerfulness, never dismiss pain."
        ),
    },
    "wise": {
        "label": "Wise",
        "prompt": (
            "Your tone is calm and grounded, like someone who has lived through hard things. "
            "You offer perspective and occasional gentle reframes. Never preachy."
        ),
    },
    "real": {
        "label": "Straight-talking",
        "prompt": (
            "Your tone is honest and direct, but never cold. You don't hedge everything, "
            "you say the true thing kindly, and you still put feelings first."
        ),
    },
}

LENGTHS: Dict[str, Dict[str, str]] = {
    "short": {"label": "Short & sweet", "prompt": "Keep replies to 1-3 short sentences."},
    "balanced": {"label": "Balanced", "prompt": "Keep replies to 2-5 short sentences or a short list. Stay under 100 words."},
    "deep": {"label": "Deeper", "prompt": "Replies may run 3-6 sentences when it genuinely helps. Still never a wall of text."},
}


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #

SYSTEM_TEMPLATE = """You are {name}, {pronouns_phrase} — a warm, emotionally intelligent companion inside an app called SensyGent. The person you are talking to uses {pronouns} to describe you.

{tone}

## How you show up
- You are a *listening companion*, not a therapist, doctor, or advice vending machine. Never diagnose, never prescribe, never claim clinical expertise.
- **Reflect first, solve later.** Before anything else, show that you understood the feeling. Name it.
- Validate the *reaction*, never the self-attack. If they say "I'm a failure", you never agree — you say something like "that's a brutal thing to say about yourself; what happened?"
- One question per reply, maximum. Open questions beat interrogation.
- Never toxic positivity. Banned: "everything happens for a reason", "just stay positive", "others have it worse", "at least…", "you should just…", "it could be worse".
- No lectures, no bullet-point life plans unless they ask for a plan.
- Never say "as an AI" or "I'm just a language model". You are {name}. If they sincerely ask what you are, be honest and kind in one short sentence.
- Match their energy: if they write three words, don't write three paragraphs.
- Use their own words back to them sometimes. That is what being heard feels like.
- You may offer one small, concrete, doable thing — never a list — and only when it fits or they ask.
- If they are just venting, do not problem-solve. Sit with them.

## Anti-repetition
- Vary your openings every single time. Never start two replies the same way.
- Avoid stock phrases like "I hear you", "I'm sorry to hear that", "it sounds like", "I understand" more than once in a conversation.

## Safety
- If there is any sign of self-harm, suicide, or immediate danger: drop the conversation style completely. Say you're glad they told you, tell them clearly that a real person needs to be involved right now, give the crisis line (988 US · 116 123 UK · 14416 India · findahelpline.com), ask if they are somewhere safe, and stay with them. Never be dismissive, never lecture about it, never promise secrecy.
- If they mention abuse, violence, or a medical emergency, gently point to real-world help.
- If they describe symptoms that sound medical (chest pain, fainting, not eating for days), suggest seeing a professional — kindly, not alarmingly.

## What they need right now
{context}

## How to end a reply
End with something that invites them forward: a gentle question, or a soft invitation to keep going. Never a dead end. Never "let me know if you need anything".
{length}"""


def _pronouns_phrase(persona: Persona) -> str:
    return {
        "she/her": "a she/her companion",
        "he/him": "a he/him companion",
        "they/them": "a they/them companion",
    }[persona.pronouns]


@dataclass
class Companion:
    """Everything needed to generate one reply."""

    persona: Persona = PERSONAS["aanya"]
    style: str = "gentle"
    length: str = "balanced"
    display_name: str = ""            # optional override of the persona name
    provider_key: str = ""            # "" → LocalCare only
    model: str = ""
    api_key: str = ""
    endpoint: str = ""
    temperature: float = 0.85
    mood_note: str = ""                 # summary of the user's own check-in history
    engine: localcare.LocalCare = field(default_factory=localcare.LocalCare)

    # -- naming ----------------------------------------------------------- #

    @property
    def name(self) -> str:
        return self.display_name.strip() or self.persona.name

    @property
    def emoji(self) -> str:
        return self.persona.emoji

    @property
    def brain(self) -> str:
        """A short human label for which engine is answering."""
        if self.provider_key and self.provider_key in PROVIDERS:
            return PROVIDERS[self.provider_key].label
        return "LocalCare (offline)"

    def profile(self) -> Dict[str, object]:
        return {
            "persona": self.persona.key,
            "name": self.name,
            "style": self.style,
            "length": self.length,
            "provider": self.provider_key,
            "model": self.model,
        }

    # -- prompt building -------------------------------------------------- #

    def build_system_prompt(self, reading: Reading, recent: Sequence[Dict[str, str]]) -> str:
        context_bits: List[str] = []
        if reading.emotion != "neutral":
            context_bits.append(
                f"- Detected emotion: {reading.emotion} (intensity {reading.intensity:.2f}/1.00, "
                f"mood around {reading.mood_score}/10)."
            )
        if reading.needs:
            context_bits.append("- They seem to want: " + ", ".join(reading.needs) + ".")
        if "vent" in reading.needs:
            context_bits.append("- They explicitly do NOT want advice. Do not give any.")
        if "sleep" in reading.needs:
            context_bits.append("- Sleep is a problem tonight. Be slow and soothing; short sentences.")
        if reading.crisis:
            context_bits.append("- CRISIS SIGNAL DETECTED. Follow the safety protocol above immediately.")
        if not context_bits:
            context_bits.append("- Nothing strongly signalled yet. Be curious and warm.")

        if self.mood_note:
            context_bits.append(f"- Their own check-in history: {self.mood_note}")

        now = _dt.datetime.now()
        hour = now.hour
        time_of_day = (
            "early morning" if hour < 6 else "morning" if hour < 12 else
            "afternoon" if hour < 17 else "evening" if hour < 21 else "late night"
        )
        context_bits.append(f"- Local time: {time_of_day} ({now:%H:%M}).")

        if recent:
            context_bits.append(
                "- In the last few messages the dominant feeling was "
                f"'{mood.dominant_emotion([m['content'] for m in recent if m['role'] == 'user'])}'."
            )

        system_prompt = SYSTEM_TEMPLATE.format(
            name=self.name,
            pronouns_phrase=_pronouns_phrase(self.persona),
            pronouns=self.persona.pronouns,
            tone=STYLES.get(self.style, STYLES["gentle"])["prompt"],
            context="\n".join(context_bits),
            length=LENGTHS.get(self.length, LENGTHS["balanced"])["prompt"],
        )
        # Post-history reminder — keeps the model on-voice after long chats.
        system_prompt += (
            f"\n\nRemember: you are {self.name}, speaking to a real person who is having a real day. "
            "Be a person, not a product."
        )
        return system_prompt

    def build_messages(self, history: Sequence[Dict[str, str]], reading: Reading) -> List[Dict[str, str]]:
        recent = list(history)[-16:]
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.build_system_prompt(reading, recent)}
        ]
        for message in recent:
            role = "assistant" if message["role"] == "assistant" else "user"
            content = str(message["content"]).strip()
            if content:
                messages.append({"role": role, "content": content})
        return messages

    # -- generation ------------------------------------------------------- #

    def stream_reply(self, history: Sequence[Dict[str, str]], user_text: str) -> Iterable[str]:
        """Yield reply chunks. Always ends up producing something."""
        reading = mood.read(user_text)
        self.engine.name = self.name

        if reading.crisis or not self._llm_ready():
            yield self.engine.reply(user_text, history)
            return

        provider: Provider = PROVIDERS[self.provider_key]
        model = self.model or provider.default_model
        messages = self.build_messages(history, reading)

        produced = False
        buffer: List[str] = []
        try:
            for chunk in llm.stream(
                provider=provider,
                model=model,
                messages=messages,
                api_key=self.api_key,
                temperature=self.temperature,
                max_tokens=800,
                endpoint=self.endpoint or None,
            ):
                produced = True
                buffer.append(chunk)
                yield chunk
        except LLMError as exc:
            message = self._friendly_error(exc)
            if produced:
                yield f"\n\n———\n*{message}*"
            else:
                yield self.engine.reply(user_text, history)
                yield f"\n\n———\n*{message} Fallback: LocalCare answered the above.*"
            return

        if not produced:
            yield self.engine.reply(user_text, history)

    def reply(self, history: Sequence[Dict[str, str]], user_text: str) -> str:
        return "".join(self.stream_reply(history, user_text)).strip()

    def _llm_ready(self) -> bool:
        if not self.provider_key or self.provider_key not in PROVIDERS:
            return False
        provider = PROVIDERS[self.provider_key]
        if provider.needs_key and not self.api_key:
            return False
        if self.provider_key == "custom" and not self.endpoint:
            return False
        return True

    def _friendly_error(self, exc: LLMError) -> str:
        text = str(exc)
        lowered = text.lower()
        if "401" in text or "403" in text or "api key" in lowered or "unauthor" in lowered:
            return "That API key isn't working — check it in Settings. I'm still here with LocalCare."
        if "429" in text or "quota" in lowered or "rate" in lowered:
            return "The free tier is rate-limited right now. LocalCare is answering instead."
        if "could not reach" in lowered:
            return "I couldn't reach the model — you may be offline. LocalCare answered instead."
        return f"Model error: {text[:160]}"

    # -- proactive -------------------------------------------------------- #

    def greeting(self, recent_moods: Sequence[int] = (), hour: Optional[int] = None) -> str:
        """Mood-aware opener for a fresh session."""
        hour = _dt.datetime.now().hour if hour is None else hour
        if recent_moods:
            average = sum(recent_moods[-4:]) / len(recent_moods[-4:])
            if average <= 4:
                emotion = "sad"
            elif average <= 6:
                emotion = "tired"
            else:
                emotion = "happy"
        else:
            emotion = "neutral"
        self.engine.name = self.name
        return self.engine.opening(emotion, hour, self.name)

    def comfort(self) -> str:
        self.engine.name = self.name
        return self.engine.comfort_sequence()


def persona_choices() -> List[str]:
    return list(PERSONAS.keys())


def resolve_persona(key: str) -> Persona:
    return PERSONAS.get(key, PERSONAS["aanya"])
