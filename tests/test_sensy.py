"""Tests for the parts of SensyGent that must never break.

Run with:  python -m pytest tests/ -q      (or plain:  python tests/test_sensy.py)

No network, no API keys, no Streamlit runtime required — the whole point of the
offline engine is that it works on its own.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensy import localcare, mood, palette, styles, tools, voice  # noqa: E402
from sensy.companion import PERSONAS, Companion, resolve_persona  # noqa: E402
from sensy.store import Store  # noqa: E402


class MoodReadingTests(unittest.TestCase):
    def test_reads_sadness(self):
        reading = mood.read("I feel so sad today, I've been crying all morning")
        self.assertEqual(reading.emotion, "sad")
        self.assertGreater(reading.intensity, 0.2)
        self.assertLess(reading.valence, 0)
        self.assertLessEqual(reading.mood_score, 6)

    def test_reads_anxiety(self):
        self.assertEqual(mood.read("I'm panicking about tomorrow, I can't breathe").emotion, "anxious")

    def test_reads_positive(self):
        reading = mood.read("I feel great today, really proud of myself")
        self.assertEqual(reading.emotion, "happy")
        self.assertGreater(reading.valence, 0)
        self.assertGreaterEqual(reading.mood_score, 5)

    def test_negation_is_handled(self):
        """'not sad' should not be scored as strong sadness."""
        plain = mood.read("I am sad")
        negated = mood.read("I am not sad")
        self.assertLess(negated.intensity, plain.intensity)

    def test_need_detection(self):
        self.assertIn("vent", mood.read("I just want to vent, no advice please").needs)
        self.assertIn("sleep", mood.read("I can't sleep and it's 3am").needs)
        self.assertIn("guidance", mood.read("what should I do about my job?").needs)

    def test_empty_input(self):
        reading = mood.read("")
        self.assertEqual(reading.emotion, "neutral")
        self.assertFalse(reading.crisis)

    def test_crisis_detection(self):
        for phrase in [
            "I want to die",
            "honestly I don't want to live like this",
            "I've been thinking about suicide",
            "I might hurt myself tonight",
        ]:
            with self.subTest(phrase=phrase):
                self.assertTrue(mood.assess_safety(phrase))

    def test_normal_sadness_is_not_crisis(self):
        self.assertFalse(mood.assess_safety("I'm sad and tired but I'll be okay"))


class LocalCareTests(unittest.TestCase):
    def setUp(self):
        self.engine = localcare.LocalCare()

    def test_replies_are_non_empty(self):
        for message in [
            "hi",
            "I feel awful",
            "I'm so anxious about work",
            "I just need to talk",
            "thank you",
            "who are you?",
            "I can't sleep",
        ]:
            with self.subTest(message=message):
                reply = self.engine.reply(message)
                self.assertTrue(reply.strip())
                self.assertGreater(len(reply), 20)

    def test_crisis_message_gets_helplines(self):
        reply = self.engine.reply("I want to end my life")
        self.assertIn("988", reply)
        self.assertIn("findahelpline.com", reply)

    def test_vent_request_is_not_given_advice(self):
        reply = self.engine.reply("I just want to vent, please don't give me advice")
        self.assertNotIn("1.", reply)
        self.assertIn("?", reply)  # ends with an invitation, not a solution

    def test_no_repetition_across_turns(self):
        replies = [self.engine.reply("I feel really low and lonely") for _ in range(6)]
        self.assertGreater(len(set(replies)), 3)

    def test_sleep_requests_are_handled_gently(self):
        reply = self.engine.reply("I can't sleep, my mind won't switch off")
        self.assertIn("?", reply)
        self.assertRegex(reply.lower(), "breath|talk|stay|drift")


class VoiceTests(unittest.TestCase):
    def test_speakable_strips_markdown_and_emoji(self):
        text = "**Hello** 🌸 there — `code` and [a link](https://x.com)"
        clean = voice.speakable(text)
        for token in ["*", "`", "🌸", "http"]:
            self.assertNotIn(token, clean)
        self.assertIn("Hello", clean)
        self.assertIn("a link", clean)

    def test_chunking_splits_long_text(self):
        text = " ".join(["This is a calm sentence."] * 40)
        chunks = voice.chunk_text(text, limit=200)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 210 for chunk in chunks))

    def test_voice_catalogue_is_sane(self):
        self.assertTrue(voice.VOICE_INDEX)
        self.assertIn(voice.default_voice_for("female"), voice.VOICE_INDEX)
        self.assertIn(voice.default_voice_for("male"), voice.VOICE_INDEX)
        self.assertTrue(voice.voices_for("female"))
        self.assertTrue(all(item.gender == "female" for item in voice.voices_for("female")))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def test_mood_roundtrip(self):
        self.store.add_mood(7, ["tired", "hopeful"], "a decent day", energy=6, sleep_hours=7.5)
        rows = self.store.mood_entries()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["score"], 7)
        self.assertIn("tired", rows[0]["emotions"])

    def test_journal_and_gratitude(self):
        self.store.add_journal("something honest", "a prompt", 5)
        self.store.add_gratitude("hot tea")
        self.assertEqual(len(self.store.journal_entries()), 1)
        self.assertEqual(len(self.store.gratitude_entries()), 1)

    def test_chat_sessions(self):
        self.store.add_chat("user", "hello", "neutral", "abc")
        self.store.add_chat("assistant", "hi there", "", "abc")
        self.assertEqual(len(self.store.chat_history("abc")), 2)
        self.store.clear_chat("abc")
        self.assertEqual(len(self.store.chat_history("abc")), 0)

    def test_prefs(self):
        self.store.set_pref("theme", "blush")
        self.store.set_pref("theme", "aurora")
        self.assertEqual(self.store.get_pref("theme"), "aurora")
        self.assertEqual(self.store.get_pref("missing", "fallback"), "fallback")

    def test_stats_and_streak(self):
        self.store.add_mood(6, ["calm"])
        stats = self.store.stats(30)
        self.assertEqual(stats["entries"], 1)
        self.assertEqual(stats["streak"], 1)
        self.assertEqual(stats["tags"].get("calm"), 1)

    def test_export_contains_everything(self):
        self.store.add_mood(4, ["tired"], "long week")
        self.store.add_journal("dear diary", "prompt")
        dump = self.store.export_text()
        self.assertIn("MOOD CHECK-INS", dump)
        self.assertIn("JOURNAL", dump)
        self.assertIn("long week", dump)


class CompanionTests(unittest.TestCase):
    def test_offline_by_default(self):
        companion = Companion(engine=localcare.LocalCare())
        self.assertEqual(companion.brain, "LocalCare (offline)")
        reply = companion.reply([], "I feel really low today")
        self.assertTrue(reply)
        self.assertIsInstance(reply, str)

    def test_crisis_bypasses_llm(self):
        """Safety never depends on a third-party provider being reachable."""
        companion = Companion(provider_key="groq", api_key="pretend-key")
        reply = "".join(companion.stream_reply([], "I want to end my life"))
        self.assertIn("988", reply)

    def test_system_prompt_contains_safety_rules(self):
        companion = Companion()
        prompt = companion.build_system_prompt(mood.read("I'm sad"), [])
        self.assertIn("988", prompt)
        self.assertIn("not a therapist", prompt.lower())
        self.assertIn(companion.name, prompt)

    def test_prompt_includes_mood_context(self):
        companion = Companion(mood_note="Their recent mood averages 4.2/10.")
        prompt = companion.build_system_prompt(mood.read("rough day"), [])
        self.assertIn("4.2", prompt)

    def test_personas_have_names_and_pronouns(self):
        for key, persona in PERSONAS.items():
            with self.subTest(persona=key):
                self.assertTrue(persona.name)
                self.assertIn(persona.pronouns, {"she/her", "he/him", "they/them"})
                self.assertTrue(persona.blurb)
        self.assertEqual(resolve_persona("nope").key, "aanya")

    def test_greeting_is_personalised(self):
        companion = Companion(engine=localcare.LocalCare())
        heavy = companion.greeting([2, 3, 2], hour=22)
        self.assertTrue(heavy)
        self.assertIn("?", heavy)


class DesignSystemTests(unittest.TestCase):
    def test_every_theme_has_the_full_token_set(self):
        required = {
            "bg", "bg_2", "surface", "surface_2", "border", "text", "muted",
            "primary", "primary_2", "accent", "glow", "orb_1", "orb_2", "orb_3",
        }
        for name, theme in palette.THEMES.items():
            with self.subTest(theme=name):
                self.assertTrue(required.issubset(theme.keys()))
                self.assertTrue(theme["label"])

    def test_theme_css_renders_variables(self):
        css = palette.theme_css("aurora")
        self.assertIn("--sg-primary", css)
        self.assertIn(":root", css)

    def test_stylesheet_loads_and_is_real(self):
        css = styles.load_css("aurora")
        self.assertIn(".sg-hero", css)
        self.assertIn("stChatMessage", css)
        self.assertGreater(len(css), 8000)

    def test_components_escape_user_content(self):
        markup = styles.entry("<script>alert(1)</script>", "<b>bold</b>")
        self.assertNotIn("<script>", markup)
        self.assertIn("&lt;script&gt;", markup)

    def test_helpers_produce_html(self):
        self.assertIn("sg-hero", styles.hero("hi", "there"))
        self.assertIn("sg-chips", styles.chips([styles.chip("x")]))
        self.assertIn("sg-jar", styles.gratitude_jar(3))
        self.assertIn("sg-breathe", styles.breathing_circle("Calm", 10))
        self.assertIn("sg-meter-fill", styles.meter(80))
        self.assertIn("sg-dots", styles.mood_dots(5))


class ToolLibraryTests(unittest.TestCase):
    def test_breathing_patterns_are_valid(self):
        for key, pattern in tools.BREATHING_PATTERNS.items():
            with self.subTest(pattern=key):
                for field in ("inhale", "hold", "exhale", "hold_out", "rounds"):
                    self.assertIn(field, pattern)
                    self.assertGreaterEqual(pattern[field], 0)
                self.assertGreater(pattern["exhale"], 0)

    def test_grounding_has_five_steps(self):
        senses = [step[0] for step in tools.GROUNDING_54321]
        self.assertEqual(senses, ["See", "Touch", "Hear", "Smell", "Taste"])

    def test_content_pools_are_substantial(self):
        for pool in (tools.AFFIRMATIONS, tools.DISTRACTIONS, tools.TINY_STEPS,
                     tools.JOURNAL_PROMPTS, tools.MOOD_TAGS, tools.HELPLINES):
            self.assertGreater(len(pool), 5)

    def test_helplines_have_contacts(self):
        for line in tools.HELPLINES:
            self.assertTrue(line["place"] and line["name"] and line["contact"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
