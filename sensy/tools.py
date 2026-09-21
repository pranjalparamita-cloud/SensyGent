"""Content library: micro-tools, prompts, affirmations and helplines.

Everything here is deliberately short, kind and doable in under three minutes,
because when someone feels low, a long "self-care plan" is just noise.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List

# --------------------------------------------------------------------------- #
# Grounding / calming tools
# --------------------------------------------------------------------------- #

BREATHING_PATTERNS: Dict[str, Dict[str, Any]] = {
    "calm": {
        "label": "Calming Breath",
        "subtitle": "4 in · 6 out",
        "inhale": 4,
        "hold": 0,
        "exhale": 6,
        "hold_out": 0,
        "rounds": 6,
        "note": "A long exhale tells your nervous system the danger has passed.",
    },
    "478": {
        "label": "4-7-8 Sleep Breath",
        "subtitle": "4 in · 7 hold · 8 out",
        "inhale": 4,
        "hold": 7,
        "exhale": 8,
        "hold_out": 0,
        "rounds": 4,
        "note": "Best lying down. Slower than you think — that is the point.",
    },
    "box": {
        "label": "Box Breathing",
        "subtitle": "4 · 4 · 4 · 4",
        "inhale": 4,
        "hold": 4,
        "exhale": 4,
        "hold_out": 4,
        "rounds": 6,
        "note": "Used by people who need a steady head under pressure.",
    },
    "sigh": {
        "label": "Physiological Sigh",
        "subtitle": "Two quick breaths, long release",
        "inhale": 2,
        "hold": 1,
        "exhale": 6,
        "hold_out": 0,
        "rounds": 8,
        "note": "The fastest known way to drop acute stress — one breath at a time.",
    },
}

GROUNDING_54321 = [
    ("See", "5 things you can see right now", "👀",
     "Look slowly. Name them out loud if you can — the colours, not just the objects."),
    ("Touch", "4 things you can feel", "🤲",
     "Your feet on the floor. Fabric on your arm. The temperature of the air."),
    ("Hear", "3 things you can hear", "👂",
     "Nearest sound, then further, then furthest. Even silence has a texture."),
    ("Smell", "2 things you can smell", "👃",
     "If nothing is there, breathe in and notice the air itself."),
    ("Taste", "1 thing you can taste", "👄",
     "A sip of water counts. So does noticing the inside of your mouth."),
]

BODY_SCAN_STEPS = [
    ("Settle", "Sit or lie down. Let the chair or bed take your full weight."),
    ("Feet", "Notice your feet. Wriggle your toes once. Let them be heavy."),
    ("Legs", "Soften your calves and thighs. No need to hold them up."),
    ("Belly", "Let your belly be soft. Let the breath drop low and slow."),
    ("Chest", "Notice your chest. If it is tight, you are not broken — that is stress."),
    ("Shoulders", "Let your shoulders fall away from your ears. They do not need guarding."),
    ("Jaw", "Unclench your jaw. Let your tongue rest loose."),
    ("Face", "Soften your forehead and the space behind your eyes."),
    ("Whole", "Feel your whole body, sitting here, still breathing. You made it to now."),
]

CALM_SOUNDS = [
    "Rain on a window",
    "A distant train at night",
    "Pages of a book turning",
    "Waves, slow and unhurried",
    "Snow dampening a whole city",
    "Your favourite song, the quiet intro",
]

DISTRACTIONS = [
    "Open your camera roll and find one photo that makes you smile. Look at it for 20 seconds.",
    "Make a drink — tea, water, anything — and do nothing else while you drink it.",
    "Text one person a single sentence that has nothing to do with how you feel.",
    "Tidy one square metre. Only one. Then stop.",
    "Step outside for 3 minutes, even just to the door. Notice the sky on purpose.",
    "Put on one song and listen to it properly, lying down, eyes closed.",
    "Write the next 3 things you'll do today. Keep them absurdly small.",
    "Stretch your arms above your head and yawn on purpose. Twice.",
    "Splash cold water on your face and wrists. It resets the alarm system.",
    "Name three things that are not going wrong right now.",
]

TINY_STEPS = [
    "Drink a glass of water.",
    "Open one window for 60 seconds.",
    "Send one short message to someone who feels safe.",
    "Put on clothes you'd be okay being seen in.",
    "Eat something — anything — even if you're not hungry.",
    "Write down the one thing that's loudest in your head, then close the page.",
    "Set a timer for 10 minutes and rest without a screen.",
    "Stand up and stretch for 10 seconds.",
]

AFFIRMATIONS = [
    "You don't have to fix everything tonight. Just the next hour.",
    "Feeling this much means you're alive, not broken.",
    "You have survived every version of this day so far.",
    "You're allowed to rest before you're finished.",
    "Your worth isn't on trial here.",
    "Sadness is weather, not climate. It will move.",
    "You don't need to earn the right to be gentle with yourself.",
    "Asking for company is a skill, not a weakness.",
    "The fact that you're still trying says something good about you.",
    "You can be proud of yourself and tired at the same time.",
    "Nothing about today has to be perfect to count.",
    "You are allowed to be a work in progress and still be enough.",
]

GRATITUDE_PROMPTS = [
    "One small thing that was okay today",
    "Someone who was kind to you this week",
    "Something your body did for you today",
    "A comfort you'd miss if it vanished",
    "Something you noticed that was beautiful",
    "A hard thing you got through",
    "Something you're looking forward to, however small",
]

JOURNAL_PROMPTS = [
    "What's taking up the most space in your head right now?",
    "If your feeling could speak, what would it say it needs?",
    "What would you say to a friend who felt exactly like this?",
    "What part of today would you keep?",
    "What are you carrying that isn't yours to carry?",
    "What made today harder than it needed to be?",
    "Who or what helped, even a little?",
]

MOOD_TAGS = [
    "tired", "anxious", "lonely", "overwhelmed", "angry", "numb",
    "hopeful", "grateful", "proud", "calm", "restless", "ashamed",
    "excited", "burnt out", "loved", "insecure",
]

# --------------------------------------------------------------------------- #
# Safety resources
# --------------------------------------------------------------------------- #

HELPLINES = [
    {"place": "🇺🇸 United States", "name": "988 Suicide & Crisis Lifeline", "contact": "Call or text 988"},
    {"place": "🇮🇳 India", "name": "Tele-MANAS / AASRA", "contact": "14416 · +91 98204 66726"},
    {"place": "🇬🇧 United Kingdom", "name": "Samaritans", "contact": "Call 116 123 (free, 24/7)"},
    {"place": "🇦🇺 Australia", "name": "Lifeline", "contact": "Call 13 11 14"},
    {"place": "🇨🇦 Canada", "name": "Talk Suicide Canada", "contact": "Call or text 988"},
    {"place": "🌍 Everywhere", "name": "Find a helpline", "contact": "findahelpline.com"},
]


def pick(pool: List[str], avoid: str | None = None, rng: random.Random | None = None) -> str:
    """Pick from ``pool``, avoiding ``avoid`` when the pool is big enough."""
    rng = rng or random
    if avoid and avoid in pool and len(pool) > 1:
        pool = [item for item in pool if item != avoid]
    return rng.choice(pool)


CRISIS_PHRASES = [
    "kill myself", "killing myself", "end my life", "end it all", "want to die",
    "wanna die", "don't want to live", "dont want to live", "no reason to live",
    "better off dead", "hurt myself", "hurting myself", "self harm", "self-harm",
    "cut myself", "overdose", "suicidal", "suicide", "take my own life",
    "not want to be here", "disappear forever",
]
