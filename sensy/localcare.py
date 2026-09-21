"""LocalCare — a 100% offline, key-free listening engine.

This is what makes SensyGent *free forever*: with no API key, no internet and
no account, the app still holds a real conversation. It is built on the parts
of counselling that are not magic — reflective listening, validation,
normalising, and one good open question at a time.

Rules it follows, borrowed from what actually helps people:

* Reflect before you respond. Name the feeling before you touch the problem.
* Validate the *reaction*, never the self-attack ("no wonder you're exhausted",
  not "you're right, you are a failure").
* Never toxic positivity. No "everything happens for a reason", no "just stay
  positive", no rushing to solutions.
* One question per turn, at most. Silence is allowed. Advice is offered, not
  imposed — and only after permission.
* Short. A wall of text is not comfort.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from . import mood
from .mood import Reading
from .tools import AFFIRMATIONS, DISTRACTIONS, TINY_STEPS, pick

REFLECTIONS: Dict[str, List[str]] = {
    "sad": [
        "That sounds heavy, and I'm glad you told me.",
        "I can hear how much this is sitting on you.",
        "There's real sadness in that. I'm not going to rush you past it.",
        "That's a lot to hold on your own.",
        "Okay. I'm here, and I'm listening properly.",
    ],
    "anxious": [
        "Your mind is running ahead of you — that's exhausting to live with.",
        "That sounds like your whole system is on alert right now.",
        "Anxiety like that makes everything feel urgent, even the small things.",
        "It sounds like your brain won't let you put it down.",
        "That's a lot of 'what ifs' to be carrying at once.",
    ],
    "angry": [
        "That anger makes sense — something important to you got stepped on.",
        "You're allowed to be angry about that.",
        "I'd be frustrated too. That would land badly on anyone.",
        "Anger like that usually means a line got crossed.",
        "That sounds genuinely unfair.",
    ],
    "tired": [
        "You sound worn down to the bone.",
        "That kind of tired isn't fixed by one early night.",
        "You've been running on empty for a while, haven't you?",
        "Exhaustion like that makes everything else harder. Of course it does.",
        "You've been carrying this for a long time without much of a break.",
    ],
    "overwhelmed": [
        "That's too many things at once for anyone to hold.",
        "It sounds like everything is shouting at the same volume.",
        "When it's all this loud, even small decisions feel impossible.",
        "That's a lot of weight on one set of shoulders.",
        "No wonder you feel like you're drowning — look at how much is coming at you.",
    ],
    "numb": [
        "Feeling nothing can be heavier than feeling everything.",
        "That flat, switched-off feeling is real, and it's usually a kind of protection.",
        "It sounds like you've gone quiet inside to cope with a lot.",
        "Numbness is often what's left after feeling too much for too long.",
    ],
    "ashamed": [
        "That's a harsh thing to be saying about yourself.",
        "I notice how unkind you're being to yourself right now.",
        "Shame is loud, but it isn't accurate.",
        "You're being much harder on yourself than you'd be to anyone else.",
    ],
    "happy": [
        "I love hearing that — tell me more.",
        "That's genuinely lovely.",
        "Good. You deserve a good day.",
        "That made me smile, honestly.",
    ],
    "neutral": [
        "Thanks for telling me.",
        "I'm with you.",
        "Okay — I'm listening.",
        "Go on, I'm here.",
    ],
}

VALIDATIONS: Dict[str, List[str]] = {
    "sad": [
        "Sadness isn't a malfunction. It's what happens when something mattered.",
        "You don't need permission to feel like this.",
        "Feeling this much doesn't mean you're weak — it means you're human.",
        "You're allowed to be a mess and still be someone worth being gentle with.",
        "Nothing about this makes you a burden.",
    ],
    "anxious": [
        "Your body is trying to protect you. It's just overdoing its job.",
        "Being scared doesn't mean the scary thing is true.",
        "You don't have to argue yourself out of feeling anxious. It can just be there for a bit.",
        "A racing mind at this hour is not a character flaw.",
        "You're not being dramatic. Your nervous system is genuinely activated.",
    ],
    "angry": [
        "Anger is often the bodyguard of something softer underneath.",
        "You can be angry without having to justify it to anyone.",
        "Getting angry here doesn't make you the bad guy.",
        "Your reaction tells me something mattered. That's not wrong.",
    ],
    "tired": [
        "Exhausted people are not lazy. You're running on reserves you don't have.",
        "Rest is not a reward you have to earn first.",
        "You can't think your way out of genuine tiredness — only rest does that.",
        "Being tired today doesn't cancel out how hard you've been trying.",
    ],
    "overwhelmed": [
        "You don't have to do all of it. Nobody could.",
        "Overwhelm is not a sign you can't cope — it's a sign you've been asked to cope with too much.",
        "Triage is allowed. Some things can wait, even if they're screaming.",
        "You're allowed to lower the bar for today.",
    ],
    "numb": [
        "Feeling nothing is not you being cold. It's you being spent.",
        "Your feelings aren't gone. They're muffled, and that's a form of rest.",
        "You don't have to force yourself to feel something to be doing it right.",
    ],
    "ashamed": [
        "You'd never say that to a friend in your position. You don't deserve it either.",
        "Guilt is worth listening to, but shame lies about who you are.",
        "Making a mistake and being a mistake are very different things.",
        "You're allowed to be imperfect and still be good.",
    ],
    "happy": [
        "Savour it. Let it land for a second before you move on.",
        "That's worth marking, even quietly.",
    ],
    "neutral": [
        "Whatever you bring here, you don't have to bring it neatly.",
        "You're allowed to be unsure how you feel.",
    ],
}

OPEN_QUESTIONS: Dict[str, List[str]] = {
    "sad": [
        "What's the heaviest part of it right now?",
        "If you had to put it into one sentence, what's hurting most?",
        "How long have you been carrying this?",
        "What would make tonight even one percent easier?",
        "Is there a part of this you haven't said out loud yet?",
    ],
    "anxious": [
        "What's the thought that keeps coming back?",
        "Where do you feel it in your body right now?",
        "What's the worst-case version your brain keeps showing you?",
        "If a friend felt this, what would you want them to do first?",
    ],
    "angry": [
        "What got crossed that shouldn't have been?",
        "What do you wish you could say to them?",
        "Under the anger — is there anything else in there?",
    ],
    "tired": [
        "What's been draining you most?",
        "When was the last time you actually rested?",
        "What could you take off your list this week — even temporarily?",
    ],
    "overwhelmed": [
        "What are the three things shouting the loudest?",
        "If only one thing had to be done today, which one?",
        "Which of those is actually yours to carry?",
    ],
    "numb": [
        "When did you notice yourself going quiet like this?",
        "What used to make you feel something, even a little?",
    ],
    "ashamed": [
        "Would you say that sentence to someone you love?",
        "What would a kinder version of you say here?",
    ],
    "happy": [
        "What made the difference today?",
        "Who was part of it?",
    ],
    "neutral": [
        "What's on your mind?",
        "Where would you like to start?",
        "What's going on for you today?",
    ],
}

NORMALISING = [
    "A lot of people feel exactly this and just don't say it out loud.",
    "This is such a common human thing to feel — and it still hurts when it's yours.",
    "You're not broken for feeling this. You're responding to something real.",
    "Nobody teaches us what to do with feelings this big. You're not behind.",
    "It makes complete sense to me that you'd feel that way.",
    "Feelings this loud usually arrive after a long stretch of holding things in.",
]

# Lines aimed at the specific feeling, so nothing ever lands tone-deaf.
AFFIRMATIONS_BY_EMOTION: Dict[str, List[str]] = {
    "sad": [
        "Sadness like this means something mattered. That's not a weakness.",
        "You don't have to be over it yet. Nobody is timing this but you.",
        "Grief and love are the same size. That's why this hurts.",
        "You're allowed to feel this for as long as it takes.",
    ],
    "anxious": [
        "Your body is trying to keep you safe. It's just being a little over-eager.",
        "Fear is loud, but it isn't a prediction.",
        "You don't have to solve all of it tonight — just the next few minutes.",
        "A racing heart says nothing about your character.",
    ],
    "tired": [
        "Rest isn't a reward you have to earn first.",
        "Exhausted people aren't lazy, they're empty. There's a difference.",
        "You're allowed to do less today and still be worth something.",
        "Sleep is maintenance, not a luxury.",
    ],
    "overwhelmed": [
        "You can't do all of it, and nobody could.",
        "Lowering the bar today isn't giving up — it's triage.",
        "One thing. Just the next one. That's the whole plan.",
        "Overwhelm isn't proof you can't cope. It's proof too much was asked.",
    ],
    "ashamed": [
        "You'd never say that sentence to someone you love.",
        "Making a mistake and being a mistake are different things.",
        "You're allowed to be imperfect and still be good.",
        "Shame is loud, but it isn't accurate.",
    ],
    "numb": [
        "Feeling nothing is often what's left after feeling too much.",
        "You don't have to force the feelings back. They'll come when it's safe.",
        "Flatness is a kind of exhaustion. It deserves rest, not judgement.",
    ],
    "angry": [
        "Anger usually means something mattered and got stepped on.",
        "You can be furious and still be a good person.",
        "You don't have to justify your anger to anyone.",
    ],
}

PRESENCE = [
    "I'm not going anywhere while you talk.",
    "You don't have to perform being okay here.",
    "Take your time. I'll wait.",
    "You can say it badly. I'll still understand.",
    "No pressure to have the right words.",
]

TOOL_OFFERS = [
    "If it would help, I can sit with you through a slow minute of breathing.",
    "Want me to give you one tiny thing to do? Just one.",
    "I could offer you a grounding thing that takes ninety seconds.",
    "Want something to take the edge off, or would you rather keep talking?",
]

CRISIS_REPLY = """I'm really glad you said that out loud, and I'm taking it seriously.

I'm an app, so I can't be the help you need in this moment — but a real person can be, right now:

**🇺🇸 988** · **🇬🇧 116 123** · **🇮🇳 14416** · **🌍 findahelpline.com**

If you can, reach out to someone tonight — a friend, family member, a helpline, or emergency services if you feel you might act on this. You don't have to explain it well. You just have to tell one person.

And I'll stay here with you for as long as you want to keep typing.

**Can you tell me where you are right now — are you somewhere safe?**"""

GREETING_REPLY = [
    "Hey. I'm here. How's your day actually going — not the polite version?",
    "Hello you. What's today been like?",
    "Hi. I've got time. What's on your mind?",
    "Hey, good to see you. How are you doing, honestly?",
]

THANKS_REPLY = [
    "Anytime. Genuinely. I'm here whenever it gets loud again.",
    "I'm glad it helped. You did the hard part — you said it out loud.",
    "You never have to thank me for listening. But thank you for letting me.",
    "Good. Keep going gently, okay?",
]

IDENTITY_REPLY = (
    "I'm {name} — a companion built to sit with you through the heavy parts of the day. "
    "I'm not a therapist and I won't pretend to be one. I listen, I ask honest questions, "
    "and I stay when things get messy.\n\n"
    "**So — how are you doing right now, really?**"
)

HELP_REPLY = (
    "Here's what I'm good for:\n\n"
    "- **Talking it out** when something's sitting on your chest\n"
    "- **Calming you down** — breathing, grounding, unwinding a spiral\n"
    "- **Mood check-ins** and a chart of how you've actually been\n"
    "- **A gratitude jar** and small reminders on rough days\n\n"
    "You can also turn on my voice in the sidebar and I'll speak instead of type.\n\n"
    "**What would help most right now?**"
)


@dataclass
class LocalCare:
    """A session-scoped listener, so it never repeats itself on you."""

    name: str = "Sensy"
    rng: random.Random = field(default_factory=random.Random)
    used: Dict[str, set] = field(default_factory=dict)
    turn: int = 0
    last_emotion: str = "neutral"
    last_question: Optional[str] = None
    offered_tool: bool = False

    # -- helpers ---------------------------------------------------------- #

    def _fresh(self, pool_key: str, options: Sequence[str]) -> str:
        chosen_set = self.used.setdefault(pool_key, set())
        remaining = [item for item in options if item not in chosen_set]
        if not remaining:
            chosen_set.clear()
            remaining = list(options)
        choice = self.rng.choice(remaining)
        chosen_set.add(choice)
        return choice

    def _reflect(self, emotion: str) -> str:
        return self._fresh(f"reflect:{emotion}", REFLECTIONS.get(emotion, REFLECTIONS["neutral"]))

    def _validate(self, emotion: str) -> str:
        pool = VALIDATIONS.get(emotion, VALIDATIONS["neutral"])
        return self._fresh(f"validate:{emotion}", pool)

    def _question(self, emotion: str) -> str:
        pool = OPEN_QUESTIONS.get(emotion, OPEN_QUESTIONS["neutral"])
        candidates = [q for q in pool if q != self.last_question] or list(pool)
        choice = self._fresh(f"question:{emotion}", candidates)
        self.last_question = choice
        return choice

    # -- the main entry point --------------------------------------------- #

    def reply(self, text: str, history: Optional[Sequence[Dict[str, str]]] = None) -> str:
        self.turn += 1
        cleaned = (text or "").strip()
        reading = mood.read(cleaned)

        if reading.crisis:
            return CRISIS_REPLY

        lowered = cleaned.lower()

        # Very short pleasantries / housekeeping
        if len(cleaned) <= 30:
            if re.fullmatch(r"[\s]*(hi|hey|hello|yo|sup|hola|namaste|hii+|hlo)[\s!.,]*", lowered):
                return self._fresh("greeting", GREETING_REPLY)
            if re.search(r"\b(thanks|thank you|thank u|ty|thx)\b", lowered):
                return self._fresh("thanks", THANKS_REPLY)
            if re.search(r"\b(help|what can you do|how do you work)\b", lowered):
                return HELP_REPLY
        if re.search(r"\b(who are you|what are you|your name|are you real|are you human)\b", lowered):
            return IDENTITY_REPLY.format(name=self.name)

        heavy = reading.intensity >= 0.2 and reading.emotion not in {"neutral", "happy"}
        self.last_emotion = reading.emotion if heavy else self.last_emotion

        # Affirmative / negative follow-ups to our own question
        if len(cleaned) <= 25 and re.fullmatch(r"[\s]*(yes|yeah|yep|sure|ok|okay|please|yes please|alright)[\s!.,]*", lowered):
            return self._affirm()
        if len(cleaned) <= 25 and re.fullmatch(r"[\s]*(no|nope|nah|not really|maybe later|no thanks)[\s!.,]*", lowered):
            return ("That's completely okay. No tools, no homework.\n\n"
                    "We can just sit here. You talk, I listen — or we can be quiet together and "
                    "you can tell me something completely ordinary about your day.\n\n"
                    "**What happened today, even something small?**")

        if reading.emotion == "happy" and reading.intensity > 0.2:
            return self._celebrate(reading)

        if not heavy and reading.emotion == "neutral" and len(cleaned.split()) < 4:
            return (self._fresh("short", [
                "I'm here. Say more when you're ready.",
                "Okay. Keep going — I'm listening.",
                "Take your time with it.",
                "I've got the time. What's underneath that?",
                "Tell me a bit more?",
            ]))

        return self._heavy_reply(cleaned, reading)

    # -- branches --------------------------------------------------------- #

    def _affirm(self) -> str:
        self.offered_tool = False
        if not self.used.get("breathing_done"):
            self.used["breathing_done"] = {True}
            return ("Good. Then let's do something small and doable.\n\n"
                    "Unclench your jaw. Drop your shoulders away from your ears. "
                    "Now breathe in through your nose for four, and out through your mouth "
                    "for six — twice as long on the way out. Three times, that's it.\n\n"
                    "The long exhale is the part that works. It tells your body the emergency is over.\n\n"
                    "**How does your chest feel now compared to thirty seconds ago?**")
        return ("Then here's the smallest possible version of a plan:\n\n"
                "1. Drink some water.\n"
                "2. Step away from the screen for two minutes.\n"
                "3. Tell me one thing you'll do next — not the whole list, just the next one.\n\n"
                "**What's the next one?**")

    def _celebrate(self, reading: Reading) -> str:
        opener = self._reflect("happy")
        tail = self._question("happy")
        if reading.echo:
            opener = f"I can hear it — \"{reading.echo}\"."
        return f"{opener}\n\n{tail}"

    def _heavy_reply(self, text: str, reading: Reading) -> str:
        """Three beats at most: reflect, sit with it, then invite them forward."""
        emotion = reading.emotion if reading.emotion != "neutral" else self.last_emotion
        beats: List[str] = []

        reflection = self._reflect(emotion)
        if reading.echo and self.rng.random() < 0.62:
            reflection = f'"{reading.echo}" — {reflection[0].lower()}{reflection[1:]}'
        beats.append(reflection)

        # Very activated people need a body-level tool, not more talking.
        if reading.intensity > 0.75 and self.rng.random() < 0.55 and "vent" not in reading.needs:
            beats.append(self._validate(emotion))
            beats.append(self._fresh("tool_offer", TOOL_OFFERS))
            return "\n\n".join(beats)

        if "sleep" in reading.needs:
            beats.append(
                "Sleep isn't something you can force. The trick is to stop fighting the "
                "wakefulness for a bit."
            )
            beats.append(
                "**Would you rather I walk you through a slow breathing pattern, or stay here "
                "and talk until you drift off?**"
            )
            return "\n\n".join(beats)

        if "vent" not in reading.needs and (
            "distraction" in reading.needs
            or ("guidance" in reading.needs and reading.intensity > 0.6)
        ):
            beats.append(self._validate(emotion))
            beats.append("Alright — one small thing to put between you and the feeling. "
                         "Not a cure, just a step sideways:")
            beats.append(f"→ *{self._fresh('distraction', DISTRACTIONS)}*")
            return "\n\n".join(beats)

        if "vent" in reading.needs:
            beats.append(
                "You don't need advice from me — you need someone to hear it properly. "
                "That's what I'm doing."
            )
            beats.append(f"**{self._question(emotion)}**")
            return "\n\n".join(beats)

        # The everyday case: sit with them, then one honest question.
        if self.turn >= 3 and self.rng.random() < 0.45:
            beats.append(self._fresh("normalising", NORMALISING))
        elif self.rng.random() < 0.7:
            beats.append(self._validate(emotion))
        else:
            beats.append(self._fresh("presence", PRESENCE))

        if "guidance" in reading.needs:
            beats.append(f"One small thing, and you can throw it away: *{self._fresh('tiny_step', TINY_STEPS)}*")
        elif self.rng.random() < 0.22:
            pool = AFFIRMATIONS_BY_EMOTION.get(emotion, AFFIRMATIONS)
            beats.append(f"*{self._fresh(f'affirm:{emotion}', pool)}*")

        beats.append(f"**{self._question(emotion)}**")
        return "\n\n".join(beats)

    # -- proactive lines -------------------------------------------------- #

    def opening(self, emotion: str, hour: int, name: str) -> str:
        """A warm greeting used when the app opens."""
        part_of_day = (
            "morning" if 5 <= hour < 12 else
            "afternoon" if 12 <= hour < 17 else
            "evening" if 17 <= hour < 22 else
            "late night"
        )
        greeting = self._fresh("opening_greeting", [
            f"Good {part_of_day}. I'm glad you're here.",
            f"Hi — {part_of_day}, then. How are you holding up?",
            f"Hey. {part_of_day.capitalize()} check-in: how's the inside of your head?",
        ])
        if emotion in {"sad", "overwhelmed", "tired", "numb"}:
            gentle = self._fresh("opening_heavy", [
                "You've been carrying something heavy lately. We don't have to fix it today — "
                "we can just make the next bit lighter.",
                "I noticed the last few days have been hard. Nothing to solve right now; "
                "I just want to know how today is going.",
                "You've had a rough run. Let's start where you actually are, not where you think "
                "you should be.",
            ])
            return f"{greeting}\n\n{gentle}\n\n**What's one word for how you feel right now?**"
        return f"{greeting}\n\n**What's on your mind?**"

    def comfort_sequence(self) -> str:
        """Used by the 'I feel low right now' SOS button."""
        return (
            "Okay. First — you're not doing anything wrong by feeling like this.\n\n"
            "Let's do this in three slow steps, and you can stop after any of them:\n\n"
            "**1.** Let your shoulders drop. Unclench your jaw. Let your hands be loose.\n"
            "**2.** Breathe in through your nose for 4. Out through your mouth for 6. "
            "Do it twice more, slower each time.\n"
            "**3.** Look around and name three things you can see. Anything.\n\n"
            "You don't have to feel better yet. You just have to get through the next few minutes, "
            "and you've already started.\n\n"
            "**I'm right here. Tell me what's happening — the messy version is fine.**"
        )


def respond(
    text: str,
    history: Optional[Sequence[Dict[str, str]]] = None,
    engine: Optional[LocalCare] = None,
    name: str = "Sensy",
) -> str:
    """Stateless helper for tests and one-off calls."""
    engine = engine or LocalCare(name=name)
    return engine.reply(text, history)
