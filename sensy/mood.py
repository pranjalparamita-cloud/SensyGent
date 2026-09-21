"""Emotion reading and safety triage.

A small, transparent, fully offline lexicon model. It is not trying to be a
classifier benchmark — it only needs to answer three questions well:

1. *How is this person feeling right now?* → valence + emotion label
2. *What do they seem to need?* → venting / guidance / distraction / company
3. *Is this a crisis?* → route to real human help immediately, no games.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from .tools import CRISIS_PHRASES

# --------------------------------------------------------------------------- #
# Lexicon: term → (emotion, weight)
# --------------------------------------------------------------------------- #

LEXICON: Dict[str, Tuple[str, float]] = {}


def _load(emotion: str, weight: float, words: Sequence[str]) -> None:
    for word in words:
        LEXICON[word] = (emotion, weight)


_load("sad", 1.0, [
    "sad", "sadness", "unhappy", "down", "low", "heartbroken", "heart broken",
    "crying", "cry", "tears", "teary", "miserable", "gloomy", "blue", "hurting",
    "hurt", "broken", "empty", "hopeless", "worthless", "useless", "failure",
    "failed", "rejected", "rejection", "dumped", "grief", "grieving", "lost",
    "miss her", "miss him", "miss them", "miss you", "homesick", "lonely",
    "alone", "isolated", "unloved", "invisible", "abandoned", "left out",
    # plain-language heaviness — people rarely say "melancholy", they say "awful"
    "awful", "terrible", "horrible", "horrid", "bad", "worst", "worse",
    "depressed", "depression", "upset", "devastated", "crushed", "shattered",
    "despair", "desperate", "suffering", "pain", "painful", "aching",
    "sobbing", "weeping", "tearful", "meh", "blah", "nightmare",
    "bad day", "rough day", "rough week", "hard day", "hard week",
])
_load("anxious", 1.0, [
    "anxious", "anxiety", "panic", "panicking", "panicked", "scared", "afraid",
    "fear", "fearful", "terrified", "worried", "worry", "worrying", "nervous",
    "dread", "dreading", "restless", "on edge", "overthinking", "overthink",
    "spiralling", "spiraling", "catastrophe", "what if", "tense", "uneasy",
    "shaking", "heart racing", "can't breathe", "cant breathe", "stressed",
    "stress", "pressure", "deadline", "exam", "interview tomorrow",
])
_load("angry", 1.0, [
    "angry", "anger", "furious", "rage", "raging", "mad", "irritated", "annoyed",
    "frustrated", "frustrating", "pissed", "resentful", "unfair", "betrayed",
    "fed up", "hate", "hating", "snapped", "screaming", "yelling",
])
_load("tired", 0.9, [
    "tired", "exhausted", "exhausting", "drained", "burnt out", "burned out",
    "burnout", "no energy", "sleepy", "fatigued", "worn out", "knackered",
    "can't sleep", "cant sleep", "insomnia", "awake all night", "no sleep",
    "sleep deprived", "sleepless",
])
_load("overwhelmed", 1.1, [
    "overwhelmed", "overwhelming", "too much", "can't cope", "cant cope",
    "cannot cope", "drowning", "swamped", "buried", "snowed under", "juggling",
    "spiralling out", "falling apart", "breaking down", "can't handle",
    "cant handle", "stuck", "trapped", "no way out", "losing it", "chaos",
])
_load("numb", 0.8, [
    "numb", "nothing matters", "don't care", "dont care", "empty inside",
    "detached", "disconnected", "flat", "hollow", "going through the motions",
    "zombie", "shut down", "shut off",
])
_load("ashamed", 0.9, [
    "ashamed", "shame", "embarrassed", "humiliated", "guilty", "guilt",
    "my fault", "i'm sorry for", "im sorry for", "i ruined", "stupid",
    "pathetic", "hate myself", "disgusting", "bad person", "let everyone down",
    "disappointment", "i am a burden", "burden",
])
_load("happy", 1.0, [
    "happy", "great", "amazing", "wonderful", "good day", "excited", "proud",
    "grateful", "thankful", "joy", "joyful", "delighted", "relieved", "calm",
    "peaceful", "content", "better today", "feeling better", "hopeful",
    "optimistic", "loved", "supported", "achieved", "passed", "promoted",
])

NEGATORS = {"not", "no", "never", "isn't", "isnt", "aren't", "arent", "don't",
            "dont", "didn't", "didnt", "can't", "cant", "won't", "wont",
            "hardly", "barely", "less", "without", "stopped"}

INTENSIFIERS = {"very": 1.5, "really": 1.4, "so": 1.35, "extremely": 1.7,
                "incredibly": 1.6, "completely": 1.6, "totally": 1.4,
                "super": 1.3, "awful": 1.5, "terribly": 1.5, "deeply": 1.4,
                "honestly": 1.1, "literally": 1.2}

# --- need detection ------------------------------------------------------- #

VENT_MARKERS = ["just want to vent", "vent", "just listen", "listen to me",
                "don't want advice", "dont want advice", "no advice",
                "not looking for advice", "just need to talk", "let me talk",
                "hear me out", "get it off my chest"]
GUIDANCE_MARKERS = ["what should i do", "what do i do", "any advice", "advice",
                    "help me fix", "how do i", "how can i", "what would you do",
                    "need a plan", "give me", "any tips", "how to"]
DISTRACTION_MARKERS = ["distract me", "take my mind off", "take my mind",
                       "something else", "cheer me up", "make me laugh",
                       "can't think about", "cant think about"]
SLEEP_MARKERS = ["can't sleep", "cant sleep", "insomnia", "awake", "3am",
                 "lying in bed", "tossing", "nightmare", "nightmares"]
COMPANY_MARKERS = ["are you there", "talk to me", "stay with me", "don't leave",
                   "dont leave", "keep me company", "i'm alone", "im alone",
                   "no one", "nobody"]
GRATEFUL_MARKERS = ["thank you", "thanks", "thank u", "that helped", "helpful",
                    "feel better", "feeling better", "you're kind", "youre kind"]

EMOTION_EMOJI = {
    "sad": "💙", "anxious": "🌪️", "angry": "🔥", "tired": "🌙",
    "overwhelmed": "🌊", "numb": "🌫️", "ashamed": "🫂", "happy": "☀️",
    "neutral": "🫧",
}

EMOTION_COLOUR = {
    "sad": "#6f9dff", "anxious": "#b58cff", "angry": "#ff8a6b",
    "tired": "#8fa7ff", "overwhelmed": "#7fd7ff", "numb": "#9aa0c4",
    "ashamed": "#ff9fc0", "happy": "#5ee6a8", "neutral": "#8b7bf7",
}


@dataclass
class Reading:
    """The result of reading a single message."""

    emotion: str = "neutral"
    intensity: float = 0.0          # 0 → 1
    valence: float = 0.0            # -1 (awful) → +1 (great)
    needs: List[str] = field(default_factory=list)
    crisis: bool = False
    echo: str = ""                  # a fragment of the user's own words

    @property
    def emoji(self) -> str:
        return EMOTION_EMOJI.get(self.emotion, "🫧")

    @property
    def colour(self) -> str:
        return EMOTION_COLOUR.get(self.emotion, "#8b7bf7")

    @property
    def is_heavy(self) -> bool:
        return self.emotion in {"sad", "overwhelmed", "numb", "ashamed"} and self.intensity > 0.25

    @property
    def mood_score(self) -> int:
        """1-10 scale derived from valence, for pre-filling the check-in."""
        return max(1, min(10, round(5.5 + self.valence * 4.5)))


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z']+", text.lower())


def _term_hits(lowered: str, tokens: List[str]) -> List[Tuple[str, int, float]]:
    """Find lexicon terms, honouring simple negation/intensifier windows."""
    hits: List[Tuple[str, int, float]] = []
    for term, (emotion, weight) in LEXICON.items():
        if " " in term:
            if term in lowered:
                idx = lowered.index(term)
                hits.append((emotion, idx, weight))
            continue
        if term not in tokens:
            continue
        positions = [i for i, tok in enumerate(tokens) if tok == term]
        for pos in positions:
            window = tokens[max(0, pos - 3): pos]
            if any(word in NEGATORS for word in window):
                # "not sad" → mild positive signal, but weak
                hits.append(("happy", pos, weight * 0.35))
                continue
            modifier = 1.0
            for word in window:
                modifier *= INTENSIFIERS.get(word, 1.0)
            hits.append((emotion, pos, weight * min(modifier, 2.0)))
    return hits


def _echo(text: str, emotion: str) -> str:
    """Try to quote back the user's own phrasing — that is what feels heard."""
    lowered = text.lower()
    best, best_pos = "", 10 ** 6
    for term, (emo, _weight) in LEXICON.items():
        if emo != emotion:
            continue
        pos = lowered.find(term)
        if pos == -1:
            continue
        if pos < best_pos:
            best, best_pos = term, pos
    if not best:
        return ""
    words = text.split()
    lowered_words = [w.lower().strip(".,!?;:'\"") for w in words]
    idx = next((i for i, w in enumerate(lowered_words) if best.split()[0] in w), None)
    if idx is None:
        return ""
    start = max(0, idx - 4)
    fragment = " ".join(words[start: idx + 4]).strip(" ,.;:!?")
    if len(fragment) > 90:
        fragment = fragment[:87].rstrip() + "…"
    return fragment


def assess_safety(text: str) -> bool:
    """True when the message suggests risk of harm to self."""
    lowered = text.lower()
    compact = re.sub(r"[\s\-_]+", "", lowered)
    for phrase in CRISIS_PHRASES:
        if phrase in lowered:
            return True
        if len(phrase) > 6 and phrase.replace(" ", "").replace("-", "") in compact:
            return True
    # "I want to die" style patterns with pronouns in between
    if re.search(r"\b(i|we)\b[^.!?]{0,25}\b(die|dead|suicide|kill)\b", lowered):
        if re.search(r"\b(want|wanna|wish|going to|gonna|end|better off|thinking)\b", lowered):
            return True
    return False


def read(text: str) -> Reading:
    """Read a single user message."""
    if not text or not text.strip():
        return Reading()

    lowered = text.lower()
    tokens = _tokens(text)
    reading = Reading()
    reading.crisis = assess_safety(text)

    hits = _term_hits(lowered, tokens)
    if hits:
        scores: Dict[str, float] = {}
        for emotion, pos, weight in hits:
            # recency bonus — the last thing said matters most
            recency = 1.0 + (pos / max(len(tokens), 1)) * 0.6
            scores[emotion] = scores.get(emotion, 0.0) + weight * recency
        dominant = max(scores, key=lambda key: scores[key])
        reading.emotion = dominant
        raw = scores[dominant]
        reading.intensity = round(min(1.0, math.log1p(raw) / math.log1p(3.5)), 3)

        positive = scores.get("happy", 0.0)
        negative = sum(v for k, v in scores.items() if k != "happy")
        total = positive + negative
        reading.valence = round((positive - negative) / total, 3) if total else 0.0

        word_count = len(tokens)
        if reading.emotion == "happy":
            reading.valence = max(0.25, abs(reading.valence))
        reading.echo = _echo(text, dominant)

    # needs
    needs = set()
    if any(marker in lowered for marker in VENT_MARKERS):
        needs.add("vent")
    if any(marker in lowered for marker in GUIDANCE_MARKERS):
        needs.add("guidance")
    if any(marker in lowered for marker in DISTRACTION_MARKERS):
        needs.add("distraction")
    if any(marker in lowered for marker in SLEEP_MARKERS):
        needs.add("sleep")
    if any(marker in lowered for marker in COMPANY_MARKERS):
        needs.add("company")
    if any(marker in lowered for marker in GRATEFUL_MARKERS):
        needs.add("gratitude")
    if reading.emotion == "neutral" and "?" in text:
        needs.add("question")
    if not needs and reading.intensity > 0.35:
        needs.add("vent" if reading.emotion in {"sad", "angry", "overwhelmed"} else "company")
    reading.needs = sorted(needs)

    if reading.intensity > 0.55:
        reading.intensity = min(1.0, reading.intensity + 0.12)
    if "!" in text or text.isupper() and len(text) > 8:
        reading.intensity = min(1.0, reading.intensity + 0.1)

    return reading


def dominant_emotion(texts: Sequence[str]) -> str:
    """The most common heavy emotion across a set of messages."""
    counts: Dict[str, int] = {}
    for text in texts:
        label = read(text).emotion
        if label != "neutral":
            counts[label] = counts.get(label, 0) + 1
    if not counts:
        return "neutral"
    return max(counts, key=lambda key: counts[key])
