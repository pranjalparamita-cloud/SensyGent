"""End-to-end tests that actually drive the Streamlit app.

Uses Streamlit's own AppTest harness: it runs app.py for real (all pages,
widgets, database writes) and fails on any uncaught exception.

Run with:  python -m pytest tests/ -q
       or: python tests/test_app.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "app.py")

PAGES = [
    "Talk",
    "Mood check-in",
    "Calm & breathe",
    "Journal",
    "Gratitude jar",
    "Insights",
    "Settings",
]


def fresh_app(db_path: str) -> AppTest:
    os.environ["SENSYGENT_DB"] = db_path
    app = AppTest.from_file(APP, default_timeout=120)
    app.run()
    dismiss_welcome(app)
    return app


def dismiss_welcome(app: AppTest) -> AppTest:
    for button in app.button:
        if "begin" in str(button.label).lower():
            button.click()
            app.run()
            break
    return app


def go_to(app: AppTest, page: str) -> AppTest:
    for button in app.sidebar.button:
        if page in str(button.label):
            button.click()
            app.run()
            break
    return app


def errors(app: AppTest) -> list:
    return [str(exception.value) for exception in app.exception]


class AppSmokeTests(unittest.TestCase):
    def setUp(self):
        # Each test gets a clean database: clear per-path caches so the app
        # rebuilds its Store against the new file.
        st.cache_resource.clear()
        st.cache_data.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "test.db")
        self.app = fresh_app(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_app_starts_without_errors(self):
        self.assertEqual(errors(self.app), [])
        self.assertTrue(self.app.session_state["messages"])

    def test_first_run_shows_a_welcome(self):
        """A brand-new database should be greeted by the welcome dialog."""
        fresh_db = os.path.join(self.tmp.name, "brand-new.db")
        os.environ["SENSYGENT_DB"] = fresh_db
        app = AppTest.from_file(APP, default_timeout=120).run()
        labels = [str(button.label).lower() for button in app.button]
        self.assertTrue(any("begin" in label for label in labels))
        os.environ["SENSYGENT_DB"] = self.db

    def test_every_page_renders(self):
        for page in PAGES:
            with self.subTest(page=page):
                go_to(self.app, page)
                self.assertEqual(errors(self.app), [])

    def test_hero_and_design_system_render(self):
        markup = " ".join(str(item.value) for item in self.app.markdown)
        self.assertIn("sg-hero", markup)
        self.assertIn("--sg-primary", markup)          # theme variables
        self.assertIn("988", markup)                    # safety net is always on screen

    def test_chat_gets_an_offline_reply(self):
        go_to(self.app, "Talk")
        before = len(self.app.session_state["messages"])
        self.app.chat_input[0].set_value("I feel really low today and very tired").run()
        self.assertEqual(errors(self.app), [])
        self.assertGreater(len(self.app.session_state["messages"]), before)
        reply = self.app.session_state["messages"][-1]
        self.assertEqual(reply["role"], "assistant")
        self.assertGreater(len(reply["content"]), 20)

    def test_crisis_message_returns_helplines(self):
        go_to(self.app, "Talk")
        self.app.chat_input[0].set_value("I want to end my life").run()
        self.assertEqual(errors(self.app), [])
        reply = self.app.session_state["messages"][-1]["content"]
        self.assertIn("988", reply)
        self.assertIn("findahelpline.com", reply)

    def test_mood_check_in_saves_to_database(self):
        from sensy.store import Store

        go_to(self.app, "Mood check-in")
        self.app.slider[0].set_value(3)
        self.app.multiselect[0].set_value(["tired", "lonely"])
        for button in self.app.button:
            if "Save check-in" in str(button.label):
                button.click()
                break
        self.app.run()
        self.assertEqual(errors(self.app), [])
        latest = Store(self.db).latest_mood()
        self.assertIsNotNone(latest)
        self.assertEqual(int(latest["score"]), 3)
        self.assertIn("tired", latest["emotions"])

    def test_journal_entry_saves(self):
        from sensy.store import Store

        go_to(self.app, "Journal")
        self.app.text_area(key="journal_body").set_value("Today was hard. I wrote it down anyway.")
        for button in self.app.button:
            if "Save entry" in str(button.label):
                button.click()
                break
        self.app.run()
        self.assertEqual(errors(self.app), [])
        self.assertEqual(len(Store(self.db).journal_entries()), 1)

    def test_gratitude_jar_fills(self):
        from sensy.store import Store

        go_to(self.app, "Gratitude jar")
        self.app.text_area(key="gratitude_note").set_value("the tea was hot")
        for button in self.app.button:
            if "Add to the jar" in str(button.label):
                button.click()
                break
        self.app.run()
        self.assertEqual(errors(self.app), [])
        self.assertEqual(len(Store(self.db).gratitude_entries()), 1)

    def test_sos_button_adds_comfort_message(self):
        for button in self.app.sidebar.button:
            if "comfort" in str(button.label):
                button.click()
                break
        self.app.run()
        self.assertEqual(errors(self.app), [])
        self.assertEqual(self.app.session_state["nav"], "talk")
        joined = " ".join(str(item.value) for item in self.app.markdown)
        self.assertIn("shoulders", joined)          # the grounding script

    def test_companion_can_be_switched(self):
        self.app.radio[0].set_value("aarav").run()
        self.assertEqual(errors(self.app), [])
        self.assertEqual(self.app.session_state["persona"], "aarav")

    def test_theme_can_be_switched(self):
        """Switching theme must re-skin the whole app via CSS variables."""
        self.app.session_state["theme"] = "blush"
        self.app.run()
        self.assertEqual(errors(self.app), [])
        markup = " ".join(str(item.value) for item in self.app.markdown)
        self.assertIn("--sg-primary: #f4739b", markup)          # blush palette
        self.assertNotIn("--sg-primary: #8b7bf7", markup)       # aurora is gone
        self.assertIn(".sg-hero", markup)                       # stylesheet still applied

    def test_insights_handles_empty_state(self):
        go_to(self.app, "Insights")
        self.assertEqual(errors(self.app), [])
        markup = " ".join(str(item.value) for item in self.app.markdown)
        self.assertIn("sg-hero", markup)


if __name__ == "__main__":
    unittest.main(verbosity=2)
