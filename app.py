"""SensyGent — a free, beautiful AI mood companion.

Run locally:      streamlit run app.py
Deploy for free:  share.streamlit.io  →  point it at this repo, main file: app.py

No API key is required. Without one, the offline LocalCare engine answers.
With a free key (Groq / Gemini / OpenRouter / Ollama), a full LLM takes over.
"""

from __future__ import annotations

import datetime as dt
import random
import time
import uuid
from typing import Dict, Iterable, List, Sequence

import altair as alt
import pandas as pd
import streamlit as st

from sensy import __version__, config as config_mod, llm, localcare
from sensy import mood as mood_mod
from sensy import palette, styles, tools, voice as voice_mod
from sensy.companion import LENGTHS, PERSONAS, STYLES, Companion
from sensy.store import MOOD_EMOJI, MOOD_LABELS, Store

# --------------------------------------------------------------------------- #

st.set_page_config(
    page_title="SensyGent · your mood companion",
    page_icon="🌸",
    layout="wide",
    initial_sidebar_state="expanded",
)

PAGES = [
    ("talk", "Talk", "💬"),
    ("checkin", "Mood check-in", "🫧"),
    ("calm", "Calm & breathe", "🧘"),
    ("journal", "Journal", "📖"),
    ("gratitude", "Gratitude jar", "🫙"),
    ("insights", "Insights", "📊"),
    ("settings", "Settings", "⚙️"),
]

QUICK_ACTIONS = [
    ("I feel low right now", "I feel really low right now and I don't know what to do.", "💙"),
    ("Help me calm down", "I'm feeling really anxious and overwhelmed, help me calm down.", "🌊"),
    ("I just need to talk", "I just need to talk. I don't want advice, I just want someone to listen.", "🫂"),
    ("Distract me", "Can you distract me? I can't stop thinking about something painful.", "🎈"),
    ("I can't sleep", "I can't sleep and my mind won't switch off.", "🌙"),
    ("Something good happened", "Something good actually happened today and I want to tell someone.", "☀️"),
]


# --------------------------------------------------------------------------- #
# Resources & state
# --------------------------------------------------------------------------- #

@st.cache_resource(show_spinner=False)
def _open_store(db_path: str) -> Store:
    return Store(db_path)


def get_store() -> Store:
    """One Store per database path (cached across reruns, but path-aware)."""
    return _open_store(Store.resolve_path())


@st.cache_data(show_spinner=False, max_entries=64, ttl=7200)
def cached_tts(text: str, voice_id: str, rate: str, prefer: str):
    """Free text-to-speech, cached so replays are instant."""
    return voice_mod.synthesize(text, voice_id, rate, prefer)


def get_secrets():
    try:
        return st.secrets
    except Exception:
        return None


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("nav", "talk")
    ss.setdefault("session_id", uuid.uuid4().hex[:12])
    ss.setdefault("engine", localcare.LocalCare())
    ss.setdefault("messages", [])
    ss.setdefault("pending", None)
    ss.setdefault("autoplay_text", None)
    ss.setdefault("api_key", "")
    ss.setdefault("tts_cache", {})
    ss.setdefault("tts_failures", 0)
    ss.setdefault("flash", [])
    ss.setdefault("ground_prompt", random.choice(tools.GRATITUDE_PROMPTS))
    ss.setdefault("reminders", random.sample(tools.AFFIRMATIONS, 3))


def flash(message: str, icon: str = "🌿", balloons: bool = False) -> None:
    """Queue a toast/balloon that survives the rerun after an action."""
    st.session_state["flash"].append({"message": message, "icon": icon, "balloons": balloons})


def drain_flash() -> None:
    queued = st.session_state.get("flash") or []
    for item in queued:
        st.toast(item["message"], icon=item["icon"])
        if item["balloons"]:
            st.balloons()
    st.session_state["flash"] = []


def init_widget_defaults(store: Store, secrets) -> Dict[str, object]:
    """Seed widget state from saved preferences, sanitising anything stale."""
    settings = config_mod.Settings.from_store(store, secrets)
    defaults: Dict[str, object] = {
        "persona": settings.persona,
        "theme": settings.theme,
        "style": settings.style,
        "length": settings.length,
        "display_name": settings.display_name,
        "voice_enabled": settings.voice_enabled,
        "autospeak": settings.autospeak,
        "voice_id": settings.voice_id,
        "voice_rate": settings.voice_rate,
        "tts_engine": settings.tts_engine,
        "provider": settings.provider,
        "model": settings.model,
        "endpoint": settings.endpoint,
        "temperature": settings.temperature,
        "show_all_voices": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

    ss = st.session_state
    if ss["persona"] not in PERSONAS:
        ss["persona"] = "aanya"
    if ss["theme"] not in palette.THEMES:
        ss["theme"] = palette.DEFAULT_THEME
    if ss["style"] not in STYLES:
        ss["style"] = "gentle"
    if ss["length"] not in LENGTHS:
        ss["length"] = "balanced"
    if ss["voice_rate"] not in voice_mod.RATE_OPTIONS:
        ss["voice_rate"] = "Natural"
    if ss["provider"] and ss["provider"] not in llm.PROVIDERS:
        ss["provider"] = ""
    if ss["voice_id"] not in voice_mod.VOICE_INDEX:
        ss["voice_id"] = voice_mod.default_voice_for(
            PERSONAS[ss["persona"]].default_voice_hint
        )
    ss.setdefault("welcome_done", store.get_pref("welcome_done", "") == "1")
    return defaults


def persist_prefs(store: Store, defaults: Dict[str, object]) -> None:
    """Write changed widget values back into the local database (only if changed)."""
    for key in defaults:
        if key in {"show_all_voices", "threshold"}:
            continue
        value = st.session_state.get(key)
        if value is None:
            continue
        text = str(value)
        if store.get_pref(key, "\x00") != text:
            store.set_pref(key, text)


def build_companion(store: Store, secrets) -> Companion:
    ss = st.session_state
    companion = config_mod.build_companion(
        store,
        secrets,
        session_key=ss.get("api_key", ""),
        persona_key=ss.get("persona", ""),
        style=ss.get("style", "") or "",
        length=ss.get("length", "") or "",
        temperature=float(ss.get("temperature", 0.85)),
        engine=ss.get("engine"),
    )
    if ss.get("display_name"):
        companion.display_name = ss["display_name"]
    return companion


# --------------------------------------------------------------------------- #
# Chat plumbing
# --------------------------------------------------------------------------- #

def store_turn(store: Store, role: str, content: str, emotion: str = "") -> None:
    try:
        store.add_chat(role, content, emotion, st.session_state["session_id"])
    except Exception:
        pass


def history_for_model() -> List[Dict[str, str]]:
    return [
        {"role": message["role"], "content": message["content"]}
        for message in st.session_state["messages"]
    ]


def slow_words(text: str, delay: float = 0.022) -> Iterable[str]:
    """Type offline replies out word by word so they land like speech."""
    words = text.split(" ")
    for index, word in enumerate(words):
        yield word if index == 0 else " " + word
        time.sleep(delay if index % 3 else delay * 1.7)


def stream_reply(companion: Companion, prompt: str, history: Sequence[Dict[str, str]]) -> str:
    """Render a streaming reply inside the current chat bubble; return the text."""
    reading = mood_mod.read(prompt)
    placeholder = st.empty()

    if reading.crisis:
        text = "".join(companion.stream_reply(history, prompt))
        placeholder.markdown(text)
        return text

    reply = ""
    source = companion.stream_reply(history, prompt)
    if companion.provider_key and companion.api_key:
        for chunk in source:
            reply += chunk
            placeholder.markdown(reply + " ▌")
    else:
        for piece in slow_words("".join(source)):
            reply += piece
            placeholder.markdown(reply + " ▌")
    placeholder.markdown(reply)
    return reply.strip()


def speak(text: str, autoplay: bool = False) -> None:
    """Show an audio player for the given text (free, keyless TTS)."""
    ss = st.session_state
    if not ss.get("voice_enabled", True) or not text.strip():
        return
    plain = voice_mod.speakable(text)
    if not plain:
        return

    # Circuit breaker: if the voice service is unreachable (offline device,
    # blocked network), stop making the user wait for it every single reply.
    if ss.get("tts_failures", 0) >= 2:
        st.caption(
            "🔇 Voice is unavailable on this network — everything else works normally. "
            "It will come back automatically when there's a connection."
        )
        return

    signature = f"{plain[:300]}|{ss['voice_id']}|{ss['voice_rate']}"
    cached = ss["tts_cache"].get(signature)
    if cached is None:
        with st.spinner("Finding my voice…"):
            cached = cached_tts(
                plain,
                ss["voice_id"],
                voice_mod.RATE_OPTIONS.get(ss["voice_rate"], "+0%"),
                ss.get("tts_engine", "auto"),
            )
        ss["tts_cache"][signature] = cached

    audio, engine, mime = cached
    if audio:
        ss["tts_failures"] = 0
        st.audio(audio, format=mime, autoplay=autoplay)
        st.caption(f"🔊 free voice · {engine}")
    else:
        ss["tts_failures"] = ss.get("tts_failures", 0) + 1
        st.caption(
            "🔇 Couldn't reach the voice service just now — voice needs a little internet. "
            "Everything else works normally."
        )


def render_user_turn(prompt: str, emotion: str) -> None:
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)
        if emotion != "neutral":
            st.markdown(
                styles.chips([
                    styles.chip(f"heard: {emotion} {mood_mod.EMOTION_EMOJI.get(emotion, '')}", "on"),
                ]),
                unsafe_allow_html=True,
            )


def handle_user_message(store: Store, companion: Companion, prompt: str) -> None:
    """Append, stream, persist — the whole turn loop."""
    ss = st.session_state
    prompt = prompt.strip()
    if not prompt:
        return

    reading = mood_mod.read(prompt)
    ss["messages"].append({"role": "user", "content": prompt, "emotion": reading.emotion})
    store_turn(store, "user", prompt, reading.emotion)

    render_user_turn(prompt, reading.emotion)

    with st.chat_message("assistant", avatar=companion.emoji):
        reply = stream_reply(companion, prompt, history_for_model()[:-1])

    ss["messages"].append({"role": "assistant", "content": reply, "emotion": ""})
    store_turn(store, "assistant", reply)
    ss["autoplay_text"] = reply

    if reading.crisis:
        st.markdown(
            styles.callout(
                "<b>You deserve real support right now, and I'm only an app.</b><br>"
                "🇺🇸 <b>988</b> · 🇬🇧 <b>116 123</b> · 🇮🇳 <b>14416</b> · "
                "<a href='https://findahelpline.com' target='_blank'>findahelpline.com</a><br>"
                "<span style='opacity:.82'>If you might act on this, please contact local "
                "emergency services or tell one person near you tonight. You don't have to "
                "explain it well.</span>",
                icon="🆘",
                kind="bad",
            ),
            unsafe_allow_html=True,
        )


def regenerate_last(store: Store, companion: Companion) -> None:
    """Ask for another reply to the same message."""
    ss = st.session_state
    if ss["messages"] and ss["messages"][-1]["role"] == "assistant":
        ss["messages"].pop()
    last_user = next(
        (message["content"] for message in reversed(ss["messages"]) if message["role"] == "user"),
        None,
    )
    if not last_user:
        return
    with st.chat_message("assistant", avatar=companion.emoji):
        reply = stream_reply(companion, last_user, ss["messages"])
    ss["messages"].append({"role": "assistant", "content": reply, "emotion": ""})
    store_turn(store, "assistant", reply)
    ss["autoplay_text"] = reply


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #

def sidebar(store: Store, secrets, companion: Companion) -> None:
    ss = st.session_state

    with st.sidebar:
        st.markdown(
            styles.sidebar_brand(
                companion.name,
                f"{companion.persona.pronouns} · always free",
                companion.emoji,
            ),
            unsafe_allow_html=True,
        )

        if st.button("🆘  I need comfort right now", key="sos", type="primary", width="stretch"):
            message = companion.comfort()
            ss["messages"].append({"role": "assistant", "content": message, "emotion": ""})
            store_turn(store, "assistant", message)
            ss["autoplay_text"] = message
            ss["nav"] = "talk"
            st.rerun()

        st.markdown(styles.section("Navigate", "🧭"), unsafe_allow_html=True)
        for key, label, icon in PAGES:
            if st.button(
                f"{icon}  {label}",
                key=f"nav_{key}",
                type="primary" if ss["nav"] == key else "secondary",
                width="stretch",
            ):
                ss["nav"] = key
                st.rerun()

        status = []
        latest = store.latest_mood()
        streak = store.mood_streak()
        if latest:
            status.append(styles.mood_pill(int(latest["score"])))
        if streak:
            status.append(styles.chip(f"{streak}-day streak", "good", "🔥"))
        if not status:
            status.append(styles.chip("no check-in yet", "warn", "🫧"))
        st.markdown(styles.chips(status), unsafe_allow_html=True)

        st.divider()

        # -- companion -----------------------------------------------------
        with st.expander("🎭  Your companion", expanded=False):
            st.radio(
                "Companion",
                options=list(PERSONAS.keys()),
                format_func=lambda key: f"{PERSONAS[key].emoji}  {PERSONAS[key].name} · {PERSONAS[key].pronouns}",
                key="persona",
                label_visibility="collapsed",
            )
            st.caption(PERSONAS[ss["persona"]].blurb)
            st.text_input("Nickname (optional)", key="display_name", placeholder="call them something of your own")
            st.markdown("**Tone**")
            st.pills("Tone", options=list(STYLES.keys()),
                     format_func=lambda key: STYLES[key]["label"], key="style",
                     label_visibility="collapsed")
            st.markdown("**Reply length**")
            st.pills("Length", options=list(LENGTHS.keys()),
                     format_func=lambda key: LENGTHS[key]["label"], key="length",
                     label_visibility="collapsed")

        # -- appearance ----------------------------------------------------
        with st.expander("🎨  Look & feel", expanded=False):
            st.pills("Theme", options=list(palette.THEMES.keys()),
                     format_func=lambda key: palette.THEMES[key]["label"], key="theme",
                     label_visibility="collapsed")
            st.caption("Colours flow through every card, chart and button.")

        # -- voice ---------------------------------------------------------
        with st.expander("🔊  Voice", expanded=False):
            st.toggle("Let my companion speak", key="voice_enabled")
            st.toggle("Speak every reply automatically", key="autospeak")
            if ss.get("voice_enabled"):
                st.toggle("Show every language", key="show_all_voices")
                catalogue = (
                    voice_mod.CATALOGUE if ss.get("show_all_voices")
                    else voice_mod.voices_for(PERSONAS[ss["persona"]].default_voice_hint)
                )
                labels = {voice.id: f"{voice.flag} {voice.label}" for voice in catalogue}
                if ss["voice_id"] not in labels:
                    ss["voice_id"] = voice_mod.default_voice_for(
                        PERSONAS[ss["persona"]].default_voice_hint
                    )
                st.selectbox("Voice", options=list(labels.keys()),
                             format_func=lambda vid: labels.get(vid, vid), key="voice_id")
                st.pills("Pace", options=list(voice_mod.RATE_OPTIONS.keys()),
                         key="voice_rate", label_visibility="collapsed")
                if st.button("▶️  Hear a sample", width="stretch"):
                    sample = (
                        f"Hi, I'm {companion.name}. I'm here whenever the day feels heavy — "
                        "you don't have to carry it alone."
                    )
                    audio, engine, mime = cached_tts(
                        sample, ss["voice_id"],
                        voice_mod.RATE_OPTIONS.get(ss["voice_rate"], "+0%"),
                        ss.get("tts_engine", "auto"),
                    )
                    if audio:
                        ss["tts_failures"] = 0
                        st.audio(audio, format=mime, autoplay=True)
                        st.caption(f"spoken free, no key needed · {engine}")
                    else:
                        ss["tts_failures"] = ss.get("tts_failures", 0) + 1
                        st.warning(
                            "Couldn't reach the voice service. Free neural voices need a little "
                            "internet — the rest of SensyGent works offline."
                        )

        # -- brain ---------------------------------------------------------
        with st.expander("🧠  Brain (optional)", expanded=False):
            st.caption(
                "Works beautifully with **no key at all** — the offline engine answers. "
                "Add a free key for longer, richer conversations."
            )
            st.selectbox(
                "Provider",
                options=[""] + list(llm.PROVIDERS.keys()),
                format_func=lambda key: "🫧  Built-in LocalCare (offline, unlimited)"
                if key == "" else llm.PROVIDERS[key].label,
                key="provider",
            )
            provider = ss.get("provider", "")
            if provider:
                spec = llm.PROVIDERS[provider]
                if spec.needs_key:
                    st.text_input("API key", key="api_key", type="password",
                                  placeholder="paste your free key",
                                  help="Kept in this browser session only. Use secrets.toml for permanence.")
                st.text_input("Model", key="model", placeholder=spec.default_model)
                if provider == "custom":
                    st.text_input("Endpoint", key="endpoint",
                                  placeholder="https://…/v1/chat/completions")
                elif provider == "ollama":
                    st.text_input("Ollama URL", key="endpoint",
                                  placeholder="http://localhost:11434/v1/chat/completions")
                st.slider("Creativity", 0.0, 1.2, step=0.05, key="temperature")

                connected = bool(ss.get("api_key")) or bool(llm.find_key(provider, secrets))
                if connected:
                    st.success(f"Connected to {spec.label}.", icon="✅")
                else:
                    st.info(f"Free key → {spec.docs}" if spec.docs else spec.note, icon="🔑")
                if spec.note and spec.docs:
                    st.caption(spec.note)

        # -- data ----------------------------------------------------------
        with st.expander("🔐  Your data", expanded=False):
            st.caption("Stored locally in SQLite. Nothing is sold, nothing is shared.")
            st.download_button(
                "⬇️  Download everything",
                data=store.export_text(),
                file_name=f"sensygent-{dt.date.today().isoformat()}.txt",
                mime="text/plain",
                width="stretch",
            )
            if st.button("🧹  Clear this conversation", width="stretch"):
                store.clear_chat(ss["session_id"])
                ss["messages"] = []
                flash("Conversation cleared — a fresh start.")
                st.rerun()
            sure = st.checkbox("I'm sure — erase everything")
            if sure and st.button("🗑️  Erase all data", type="primary", width="stretch"):
                store.clear_chat()
                ss["messages"] = []
                flash("Everything erased.", "🧽")
                st.rerun()

        st.markdown(
            f"""<div class="sg-footer" style="margin-top:1rem;border:none">
            v{__version__} · a companion, not a therapist<br>
            <a href="https://findahelpline.com" target="_blank">find a helpline</a>
            </div>""",
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #

def time_based_greeting() -> str:
    hour = dt.datetime.now().hour
    if hour < 5:
        return "Still awake?"
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    if hour < 21:
        return "Good evening"
    return "Late night again?"


def page_talk(store: Store, companion: Companion) -> None:
    ss = st.session_state
    latest = store.latest_mood()
    streak = store.mood_streak()

    chip_row = [
        styles.chip(companion.brain, "on", "🧠"),
        styles.chip(STYLES[companion.style]["label"], "", "🎚️"),
        styles.chip(
            "voice on" if ss.get("voice_enabled") else "voice off",
            "good" if ss.get("voice_enabled") else "",
            "🔊",
        ),
    ]
    if latest:
        chip_row.append(styles.mood_pill(int(latest["score"])))
    if streak:
        chip_row.append(styles.chip(f"{streak} days", "good", "🔥"))

    st.markdown(
        styles.hero(
            title=time_based_greeting(),
            subtitle=(
                f"I'm {companion.name}. I'm here to listen, to steady you, and to stay "
                "when things feel heavy — no judgement, no rush, no bill."
            ),
            eyebrow="your companion is here",
            emoji=companion.emoji,
            chips=chip_row,
        ),
        unsafe_allow_html=True,
    )

    today = dt.date.today().isoformat()
    checked_in_today = any(
        str(row["ts"]).startswith(today) for row in store.mood_entries(20)
    )
    if not checked_in_today:
        left, right = st.columns([3, 1])
        with left:
            st.markdown(
                styles.callout(
                    "You haven't checked in today. Ten seconds, and it helps me understand "
                    "your week properly.", icon="🫧",
                ),
                unsafe_allow_html=True,
            )
        with right:
            if st.button("Check in", width="stretch"):
                ss["nav"] = "checkin"
                st.rerun()

    if len(ss["messages"]) < 2:
        st.markdown(styles.section("Where would you like to start?", "✨"), unsafe_allow_html=True)
        columns = st.columns(3)
        for index, (label, prompt, icon) in enumerate(QUICK_ACTIONS):
            with columns[index % 3]:
                if st.button(f"{icon}  {label}", key=f"quick_{index}", width="stretch"):
                    ss["pending"] = prompt
                    st.rerun()

    if not ss["messages"]:
        opening = companion.greeting(
            [int(row["score"]) for row in store.mood_entries(6)], dt.datetime.now().hour
        )
        ss["messages"].append({"role": "assistant", "content": opening, "emotion": ""})
        store_turn(store, "assistant", opening)

    st.markdown(styles.section("Our conversation", "💬"), unsafe_allow_html=True)

    for index, message in enumerate(ss["messages"]):
        avatar = companion.emoji if message["role"] == "assistant" else "🧑"
        wrapper = "ai" if message["role"] == "assistant" else "user"
        with st.container(key=f"sgmsg-{wrapper}-{index}"):
            with st.chat_message(message["role"], avatar=avatar):
                st.markdown(message["content"])

    actions = st.columns([1.1, 1.1, 1.1, 4])
    with actions[0]:
        if ss["messages"] and ss["messages"][-1]["role"] == "assistant":
            if st.button("🔁  Reply again", key="regen", width="stretch"):
                regenerate_last(store, companion)
                st.rerun()
    with actions[1]:
        if ss.get("voice_enabled") and ss["messages"]:
            if st.button("🔊  Speak it", key="speak_last", width="stretch"):
                last = next(
                    (m for m in reversed(ss["messages"]) if m["role"] == "assistant"), None
                )
                if last:
                    ss["autoplay_text"] = last["content"]
                    ss["speak_once"] = True       # play it now, don't change settings
                    st.rerun()

    if ss.get("autoplay_text"):
        last_assistant = next(
            (m for m in reversed(ss["messages"]) if m["role"] == "assistant"), None
        )
        if last_assistant:
            play_now = bool(ss.pop("speak_once", False))
            speak(last_assistant["content"], autoplay=bool(ss.get("autospeak")) or play_now)
        ss["autoplay_text"] = None

    prompt = st.chat_input(f"Tell {companion.name} what's on your mind…")
    if ss.get("pending"):
        prompt = ss["pending"]
        ss["pending"] = None
    if prompt:
        handle_user_message(store, companion, prompt)
        st.rerun()


def page_checkin(store: Store, companion: Companion) -> None:
    ss = st.session_state
    st.markdown(
        styles.hero(
            "How are you, really?",
            "No right answers here. Slide to whatever number fits, tag what's true, and let "
            "that be enough for today.",
            eyebrow="mood check-in",
            emoji="🫧",
            chips=[styles.chip("takes 20 seconds", "on", "⏱️")],
        ),
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.25, 1])

    with left:
        score = st.slider("Mood right now", 1, 10, 5, key="checkin_score")
        st.markdown(
            styles.mood_dots(score) + f"<div class='sg-stat-sub'>{MOOD_LABELS[score]}</div>",
            unsafe_allow_html=True,
        )

        st.markdown(styles.section("What's underneath it?", "🏷️"), unsafe_allow_html=True)
        tags = st.multiselect(
            "Feeling tags", options=tools.MOOD_TAGS, key="checkin_tags",
            label_visibility="collapsed", placeholder="pick any that fit",
        )
        energy = st.slider("Energy", 1, 10, 5, key="checkin_energy")
        sleep_hours = st.number_input(
            "Sleep last night (hours)", min_value=0.0, max_value=16.0, value=7.0,
            step=0.5, key="checkin_sleep",
        )
        note = st.text_area(
            "Anything you want to note down? (optional)", key="checkin_note", height=110,
            placeholder="A sentence is plenty. Nobody else reads this.",
        )

        if st.button("💾  Save check-in", type="primary", width="stretch"):
            store.add_mood(
                score=int(score), emotions=tags, note=note,
                energy=int(energy), sleep_hours=float(sleep_hours),
            )
            ss["checkin_reflection"] = reflect_on_checkin(score, tags, note)
            flash(f"Logged {score}/10 · {MOOD_LABELS[int(score)]}", "🌿",
                  balloons=int(score) >= 8)
            st.rerun()

    with right:
        stats = store.stats(30)
        st.markdown(
            styles.card(
                styles.chip(f"{stats['streak']}-day streak", "good", "🔥")
                + f"<div class='sg-stat-value' style='margin-top:.7rem'>{stats['average'] or '—'}</div>"
                + "<div class='sg-stat-sub'>average mood over the last 30 days</div>"
                + styles.meter(float(stats["average"] or 0) * 10,
                               f"{stats['check_in_days']} days logged"),
                title="Your month so far",
            ),
            unsafe_allow_html=True,
        )
        if ss.get("checkin_reflection"):
            st.markdown(
                styles.quote(ss["checkin_reflection"], companion.name), unsafe_allow_html=True
            )

        recent = store.mood_entries(5)
        if recent:
            st.markdown(styles.section("Recent days", "🗓️"), unsafe_allow_html=True)
            for row in recent:
                st.markdown(
                    styles.entry(
                        f"{str(row['ts'])[:16]} · {MOOD_EMOJI[int(row['score'])]} {row['score']}/10"
                        + (f" · {row['emotions']}" if row["emotions"] else ""),
                        row["note"] or "—",
                    ),
                    unsafe_allow_html=True,
                )


def reflect_on_checkin(score: int, tags: List[str], note: str) -> str:
    """A short, human reflection after a check-in — offline and instant."""
    if score >= 8:
        base = "That's genuinely lovely to see. Hold onto whatever made today work."
    elif score >= 6:
        base = ("Steady is underrated. Thanks for logging it — these are the days that build "
                "the picture.")
    elif score >= 4:
        base = ("Middle-ground days still count. You showed up and told the truth, which is "
                "more than most people do.")
    else:
        base = ("That's a low number, and it's okay that it's low. Logging it is already a kind "
                "thing to do for yourself.")
    if tags:
        base += f" I noticed you tagged {', '.join(tags[:3])} — useful to know."
    if note and len(note.split()) > 3:
        base += " And thank you for writing it down."
    if score <= 4:
        base += " If you want, come and talk to me — I'm right here."
    return base


def page_calm(store: Store, companion: Companion) -> None:
    st.markdown(
        styles.hero(
            "Let's slow things down",
            "Ninety seconds of breathing changes more than you'd expect. Pick what fits — "
            "or just press the red button.",
            eyebrow="calm toolkit",
            emoji="🧘",
            chips=[styles.chip("free · no signup", "good", "🌿")],
        ),
        unsafe_allow_html=True,
    )

    if st.button("🆘  I feel low right now — help me through it", type="primary", width="stretch"):
        st.session_state["comfort_mode"] = True

    if st.session_state.get("comfort_mode"):
        st.markdown(styles.quote(companion.comfort(), companion.name), unsafe_allow_html=True)
        st.markdown(
            styles.callout(
                "If talking has become hard, these people are there 24/7 and free: "
                "<b>988</b> (US) · <b>116 123</b> (UK) · <b>14416</b> (India) · "
                "<a href='https://findahelpline.com' target='_blank'>findahelpline.com</a>",
                icon="☎️", kind="warn",
            ),
            unsafe_allow_html=True,
        )
        if st.button("Close this"):
            st.session_state["comfort_mode"] = False
            st.rerun()
        st.divider()

    tab_breath, tab_ground, tab_scan, tab_lift = st.tabs(
        ["🌬️  Breathe", "🖐️  5-4-3-2-1", "🫧  Body scan", "🎈  Lift me up"]
    )

    with tab_breath:
        chosen = st.pills(
            "Pattern", options=list(tools.BREATHING_PATTERNS.keys()),
            format_func=lambda key: tools.BREATHING_PATTERNS[key]["label"],
            default="calm", key="breath_pattern",
        ) or "calm"
        pattern = tools.BREATHING_PATTERNS[chosen]
        cycle = (
            pattern["inhale"] + pattern["hold"] + pattern["exhale"] + pattern["hold_out"]
        ) * 1.0

        columns = st.columns([1, 1.15])
        with columns[0]:
            st.markdown(
                styles.breathing_circle(pattern["subtitle"], cycle_seconds=cycle),
                unsafe_allow_html=True,
            )
        with columns[1]:
            st.markdown(
                styles.card(
                    f"<b>{pattern['label']}</b>"
                    f"<div class='sg-stat-sub' style='margin-top:.35rem'>{pattern['note']}</div>",
                    title="How it works",
                ),
                unsafe_allow_html=True,
            )
            beats = [
                f"1️⃣ In · {pattern['inhale']}s",
                f"2️⃣ Hold · {pattern['hold']}s" if pattern["hold"] else "2️⃣ no hold",
                f"3️⃣ Out slowly · {pattern['exhale']}s",
                f"4️⃣ Rest · {pattern['hold_out']}s" if pattern["hold_out"] else "4️⃣ repeat",
            ]
            st.markdown(
                "".join(
                    f"<span class='sg-chip' style='margin:.3rem .3rem 0 0'>{beat}</span>"
                    for beat in beats
                ),
                unsafe_allow_html=True,
            )
            st.caption(
                f"Follow the circle — it expands as you breathe in. "
                f"{pattern['rounds']} rounds is a full set."
            )
            if st.button("😮‍💨  I did it", width="stretch"):
                flash("Notice the difference — that was you, not me. 💙")
                st.rerun()

    with tab_ground:
        st.caption("Work down the list slowly. Slow is the whole point.")
        for step, (sense, instruction, icon, detail) in enumerate(tools.GROUNDING_54321, start=1):
            with st.expander(f"{icon}  {sense} — {instruction}", expanded=step == 1):
                st.markdown(f"*{detail}*")
                st.text_input("What did you notice? (optional)", key=f"ground_{step}",
                              placeholder="typing it makes it stick")

    with tab_scan:
        st.caption("A nine-step scan, top to toe. Stopping early counts too.")
        if st.button("▶️  Walk me through it", type="primary"):
            bar = st.progress(0.0, text="Settling in…")
            for index, (part, guidance) in enumerate(tools.BODY_SCAN_STEPS, start=1):
                bar.progress(index / len(tools.BODY_SCAN_STEPS), text=f"{part} — {guidance}")
                time.sleep(1.3)
            st.toast("Scan complete. Notice anything looser? 🌿")
        st.markdown(
            styles.callout(
                "Let your whole body be held by whatever you're sitting or lying on. You don't "
                "have to hold yourself up right now.",
                icon="🛏️",
            ),
            unsafe_allow_html=True,
        )

    with tab_lift:
        st.caption("A step sideways, not a cure.")
        if st.button("🎲  Give me one small thing", type="primary"):
            st.session_state["distraction"] = random.choice(tools.DISTRACTIONS)
        if st.session_state.get("distraction"):
            st.markdown(
                styles.card(
                    f"<div style='font-size:1.06rem;line-height:1.62'>"
                    f"{st.session_state['distraction']}</div>",
                    title="try this",
                ),
                unsafe_allow_html=True,
            )

        st.markdown(styles.section("Kind reminders", "💌"), unsafe_allow_html=True)
        for line in st.session_state.get("reminders") or random.sample(tools.AFFIRMATIONS, 3):
            st.markdown(
                f"<div class='sg-quote' style='margin-bottom:.5rem;font-size:1rem'>{line}</div>",
                unsafe_allow_html=True,
            )
        if st.button("↻  Three more", width="stretch"):
            st.session_state["reminders"] = random.sample(tools.AFFIRMATIONS, 3)
            st.rerun()

    st.divider()
    st.markdown(styles.section("If it ever gets darker than this", "☎️"), unsafe_allow_html=True)
    for helpline in tools.HELPLINES:
        st.markdown(
            styles.entry(f"{helpline['place']} · {helpline['name']}", helpline["contact"]),
            unsafe_allow_html=True,
        )


def page_journal(store: Store, companion: Companion) -> None:
    st.markdown(
        styles.hero(
            "A page that keeps your secrets",
            "Write badly. Write in fragments. Nobody grades this — it just helps to get it "
            "out of your head and onto something.",
            eyebrow="journal",
            emoji="📖",
            chips=[styles.chip("stays on this machine", "good", "🔒")],
        ),
        unsafe_allow_html=True,
    )

    if "journal_prompt" not in st.session_state:
        st.session_state["journal_prompt"] = random.choice(tools.JOURNAL_PROMPTS)

    st.markdown(
        styles.quote(st.session_state["journal_prompt"], "today's prompt"), unsafe_allow_html=True
    )
    if st.button("🎲  Different prompt"):
        st.session_state["journal_prompt"] = random.choice(tools.JOURNAL_PROMPTS)
        st.rerun()

    body = st.text_area(
        "Your entry", height=220, key="journal_body",
        placeholder="Start anywhere. Even “I don't know what to say” works.",
    )
    columns = st.columns([1, 1, 2])
    with columns[0]:
        if st.button("💾  Save entry", type="primary", width="stretch"):
            if body.strip():
                store.add_journal(body.strip(), st.session_state["journal_prompt"])
                flash("Kept. Thank you for trusting me with it. 📖")
                st.rerun()
            else:
                st.warning("Nothing to save yet — write a line first.")
    with columns[1]:
        if st.button("💬  Talk it through", width="stretch"):
            if body.strip():
                st.session_state["pending"] = (
                    f"{st.session_state['journal_prompt']}\n\n{body.strip()}"
                )
                st.session_state["nav"] = "talk"
                st.rerun()
            else:
                st.warning("Write something first and I'll respond to it.")

    st.markdown(styles.section("Your entries", "🗂️"), unsafe_allow_html=True)
    entries = store.journal_entries(50)
    if not entries:
        st.markdown(
            styles.callout("No entries yet. The first one is the hardest — it gets easier.",
                           icon="✍️"),
            unsafe_allow_html=True,
        )
    for row in entries:
        st.markdown(
            styles.entry(f"{str(row['ts'])[:16]} · {str(row['prompt'])[:70]}", row["body"]),
            unsafe_allow_html=True,
        )
        if st.button("Delete", key=f"del_j_{row['id']}"):
            store.delete_journal(int(row["id"]))
            st.rerun()


def page_gratitude(store: Store, companion: Companion) -> None:
    entries = store.gratitude_entries(400)
    st.markdown(
        styles.hero(
            "The gratitude jar",
            "One small good thing at a time. On the rough days, this is the evidence that the "
            "rough days aren't all of it.",
            eyebrow="good things",
            emoji="🫙",
            chips=[styles.chip(f"{len(entries)} notes", "good", "🧡")],
        ),
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 1.15])
    with left:
        st.markdown(styles.gratitude_jar(len(entries)), unsafe_allow_html=True)
        st.caption(f"{len(entries)} notes in the jar · fills up to 60 at a time")

    with right:
        st.markdown(
            styles.quote(st.session_state["ground_prompt"], "prompt"), unsafe_allow_html=True
        )
        if st.button("🎲  New prompt"):
            st.session_state["ground_prompt"] = random.choice(tools.GRATITUDE_PROMPTS)
            st.rerun()
        note = st.text_area(
            "One good thing", key="gratitude_note", height=110,
            placeholder="It can be tiny. “The tea was hot” counts.",
        )
        if st.button("🫙  Add to the jar", type="primary", width="stretch"):
            if note.strip():
                store.add_gratitude(note.strip())
                flash("Added — the jar just got heavier in the best way. 🧡")
                st.rerun()
            else:
                st.warning("Even three words will do.")

    entries = store.gratitude_entries(400)
    if entries:
        st.markdown(styles.section("In the jar", "📜"), unsafe_allow_html=True)
        for row in entries[:12]:
            st.markdown(
                styles.entry(str(row["ts"])[:16], row["body"], accent="#ffb36b"),
                unsafe_allow_html=True,
            )


def page_insights(store: Store, companion: Companion) -> None:
    stats = store.stats(30)
    st.markdown(
        styles.hero(
            "Your patterns, gently",
            "Not a scoreboard. Just a picture of how you've actually been — so the hard weeks "
            "become visible instead of invisible.",
            eyebrow="insights",
            emoji="📊",
        ),
        unsafe_allow_html=True,
    )

    if stats["entries"] == 0:
        st.markdown(
            styles.callout(
                "No check-ins yet. Log one and this page fills with your own story — trends, "
                "tags, and what actually helps you.",
                icon="🫧",
            ),
            unsafe_allow_html=True,
        )
        if st.button("🫧  Do my first check-in", type="primary"):
            st.session_state["nav"] = "checkin"
            st.rerun()
        return

    theme = palette.get_theme(st.session_state.get("theme", palette.DEFAULT_THEME))
    columns = st.columns(4)
    metrics = [
        (f"{stats['average']}", "30-day average", "out of 10"),
        (f"{stats['streak']}", "day streak", "keep it going 🔥"),
        (f"{stats['check_in_days']}", "days logged", f"of the last {stats['days']}"),
        (f"{stats['chat_turns']}", "things shared", "with your companion"),
    ]
    for column, (value, label, sub) in zip(columns, metrics):
        with column:
            st.markdown(styles.stat(value, label, sub), unsafe_allow_html=True)

    st.markdown(styles.section("Mood over time", "📈"), unsafe_allow_html=True)
    if stats["series"]:
        frame = pd.DataFrame(
            [{"day": day, "mood": score} for day, score in sorted(stats["series"].items())]
        )
        frame["day"] = pd.to_datetime(frame["day"])
        chart = (
            alt.Chart(frame)
            .mark_area(
                line={"color": theme["primary"], "strokeWidth": 3},
                color=alt.Gradient(
                    gradient="linear",
                    stops=[
                        alt.GradientStop(color=theme["primary"], offset=0),
                        alt.GradientStop(color="rgba(0,0,0,0)", offset=1),
                    ],
                    x1=1, x2=1, y1=1, y2=0,
                ),
                interpolate="monotone",
            )
            .encode(
                x=alt.X("day:T", title=None, axis=alt.Axis(format="%d %b", grid=False,
                                                           labelColor=theme["muted"])),
                y=alt.Y("mood:Q", title="mood", scale=alt.Scale(domain=[1, 10]),
                        axis=alt.Axis(gridColor="rgba(255,255,255,.07)",
                                      labelColor=theme["muted"])),
                tooltip=[alt.Tooltip("day:T", title="Day", format="%a %d %b"),
                         alt.Tooltip("mood:Q", title="Mood", format=".1f")],
            )
            .properties(height=260)
            .configure_view(strokeOpacity=0)
            .configure(background="transparent")
        )
        st.altair_chart(chart, width="stretch")
    else:
        st.caption("Not enough data for a trend yet — a few days of check-ins is all it takes.")

    left, right = st.columns(2)
    with left:
        st.markdown(styles.section("What you tag most", "🏷️"), unsafe_allow_html=True)
        if stats["tags"]:
            frame = pd.DataFrame(
                [{"tag": tag, "count": count} for tag, count in list(stats["tags"].items())[:8]]
            )
            chart = (
                alt.Chart(frame)
                .mark_bar(cornerRadiusEnd=8, color=theme["primary_2"])
                .encode(
                    x=alt.X("count:Q", title=None,
                            axis=alt.Axis(grid=False, labelColor=theme["muted"])),
                    y=alt.Y("tag:N", title=None, sort="-x",
                            axis=alt.Axis(labelColor=theme["text"], labelFontSize=12)),
                    tooltip=["tag", "count"],
                )
                .properties(height=240)
                .configure_view(strokeOpacity=0)
                .configure(background="transparent")
            )
            st.altair_chart(chart, width="stretch")
        else:
            st.caption("No tags yet.")

    with right:
        st.markdown(styles.section("Emotional weather", "🌦️"), unsafe_allow_html=True)
        timeline = store.emotion_timeline(300)
        if timeline:
            counts: Dict[str, int] = {}
            for row in timeline:
                counts[row["emotion"]] = counts.get(row["emotion"], 0) + int(row["n"])
            rows = sorted(counts.items(), key=lambda kv: -kv[1])[:7]
            frame = pd.DataFrame([{"emotion": key, "messages": value} for key, value in rows])
            chart = (
                alt.Chart(frame)
                .mark_arc(innerRadius=55, outerRadius=95, cornerRadius=6)
                .encode(
                    theta=alt.Theta("messages:Q"),
                    color=alt.Color(
                        "emotion:N",
                        scale=alt.Scale(
                            domain=list(mood_mod.EMOTION_COLOUR.keys()),
                            range=list(mood_mod.EMOTION_COLOUR.values()),
                        ),
                        legend=alt.Legend(labelColor=theme["muted"], title=None,
                                          orient="bottom", columns=2),
                    ),
                    tooltip=["emotion", "messages"],
                )
                .properties(height=250)
                .configure_view(strokeOpacity=0)
                .configure(background="transparent")
            )
            st.altair_chart(chart, width="stretch")
        else:
            st.caption("Talk with your companion and the emotional mix appears here.")

    st.markdown(styles.section("What tends to help you", "🌿"), unsafe_allow_html=True)
    for observation in build_observations(store, stats):
        st.markdown(styles.callout(observation, icon="🔎"), unsafe_allow_html=True)


def build_observations(store: Store, stats: Dict[str, object]) -> List[str]:
    """Small, honest, non-clinical observations from the user's own data."""
    notes: List[str] = []
    rows = store.mood_entries(60)
    if len(rows) >= 4:
        with_sleep = [row for row in rows if float(row["sleep_hours"] or 0) > 0]
        long_sleep = [row for row in with_sleep if float(row["sleep_hours"]) >= 7]
        short_sleep = [row for row in with_sleep if float(row["sleep_hours"]) < 6]
        if long_sleep and short_sleep:
            good = sum(int(row["score"]) for row in long_sleep) / len(long_sleep)
            poor = sum(int(row["score"]) for row in short_sleep) / len(short_sleep)
            if good - poor >= 0.7:
                notes.append(
                    f"On nights you sleep 7+ hours, your mood averages <b>{good:.1f}/10</b>, "
                    f"versus <b>{poor:.1f}/10</b> after short sleep. Sleep may be doing more "
                    "heavy lifting than it gets credit for."
                )
        energies = [int(row["energy"]) for row in rows]
        scores = [int(row["score"]) for row in rows]
        high = [score for score, energy in zip(scores, energies) if energy >= 7]
        low = [score for score, energy in zip(scores, energies) if energy <= 3]
        if high and low and (sum(high) / len(high)) - (sum(low) / len(low)) >= 0.8:
            notes.append(
                "Your energy and your mood move together in your data — protecting the things "
                "that recharge you matters as much as finishing the list."
            )
    if int(stats["gratitude_count"]) >= 5:
        notes.append(
            f"You've collected <b>{stats['gratitude_count']} good things</b>. Rereading them on "
            "a low day is one of the cheapest things that genuinely works."
        )
    if int(stats["streak"]) >= 3:
        notes.append(
            f"That's a <b>{stats['streak']}-day check-in streak</b>. Consistency is what makes "
            "everything else here useful."
        )
    weekdays: Dict[str, int] = {}
    for row in rows:
        try:
            weekday = dt.date.fromisoformat(str(row["ts"])[:10]).strftime("%A")
        except ValueError:
            continue
        weekdays[weekday] = weekdays.get(weekday, 0) + 1
    if weekdays:
        busiest, count = max(weekdays.items(), key=lambda kv: kv[1])
        if count >= 4:
            notes.append(
                f"You check in most often on <b>{busiest}s</b> — maybe the day of the week to "
                "plan something gentle for. Just an observation, not a diagnosis."
            )
    if not notes:
        notes.append(
            "Keep checking in. After about a week this page starts telling you things about your "
            "own patterns that are genuinely hard to notice from the inside."
        )
    return notes


def page_settings(store: Store, companion: Companion, secrets) -> None:
    st.markdown(
        styles.hero(
            "Make it yours",
            "Change who your companion is, how they sound, and which brain answers. Everything "
            "here is optional — it works beautifully untouched.",
            eyebrow="settings",
            emoji="⚙️",
        ),
        unsafe_allow_html=True,
    )

    left, right = st.columns(2)
    with left:
        st.markdown(styles.section("Your companions", "🎭"), unsafe_allow_html=True)
        for key, persona in PERSONAS.items():
            active = key == companion.persona.key
            st.markdown(
                styles.entry(
                    f"{persona.emoji} {persona.name} · {persona.pronouns}"
                    + ("   ← with you now" if active else ""),
                    persona.blurb,
                    accent="#8b7bf7" if active else "",
                ),
                unsafe_allow_html=True,
            )
        st.caption("Switch any time in the sidebar — the conversation carries over.")

        st.markdown(styles.section("Voice", "🔊"), unsafe_allow_html=True)
        status = voice_mod.engine_status()
        st.markdown(
            styles.callout(
                "Text-to-speech is <b>free and keyless</b> — it uses "
                f"{'edge-tts neural voices' if status['edge-tts'] else 'gTTS'}. "
                "Choose a voice in the sidebar under 🔊 Voice, then press play on any reply.",
                icon="🎙️", kind="good",
            ),
            unsafe_allow_html=True,
        )
        st.caption(f"engines → edge-tts: {status['edge-tts']} · gTTS: {status['gTTS']}")

    with right:
        st.markdown(styles.section("Which brain answers", "🧠"), unsafe_allow_html=True)
        st.markdown(
            styles.callout(
                "<b>LocalCare</b> is built in, offline and unlimited — it needs nothing at all. "
                "Add a free API key and your companion upgrades to a full LLM for longer, "
                "nuanced replies — and falls back automatically if the key runs out or the "
                "internet drops.",
                icon="🫧",
            ),
            unsafe_allow_html=True,
        )
        for spec in llm.PROVIDERS.values():
            st.markdown(
                styles.entry(
                    spec.label + (f"  ·  {spec.docs}" if spec.docs else ""),
                    spec.note or "OpenAI-compatible endpoint.",
                ),
                unsafe_allow_html=True,
            )

        st.markdown(styles.section("Deploy it for free", "🚀"), unsafe_allow_html=True)
        st.markdown(
            styles.callout(
                "Push this repo to GitHub, open <a href='https://share.streamlit.io' "
                "target='_blank'>share.streamlit.io</a>, choose the repo, set the main file to "
                "<code>app.py</code> and press deploy. Free tier, no card, live in a minute. "
                "Add API keys as secrets in the dashboard if you want the LLM brain.",
                icon="☁️", kind="good",
            ),
            unsafe_allow_html=True,
        )

    st.markdown(styles.section("Privacy & limits", "🔐"), unsafe_allow_html=True)
    st.markdown(
        styles.callout(
            f"Your mood scores, journal and gratitude notes live in a local SQLite file "
            f"(<code>{store.path}</code>). With an LLM provider enabled, your message text is "
            "sent to that provider to generate the reply — nothing else is. SensyGent is a "
            "supportive companion, <b>not a therapist</b>: it can't diagnose, prescribe or "
            "replace care. In a crisis please reach a human — <b>988</b> (US) · "
            "<b>116 123</b> (UK) · <b>14416</b> (India) · "
            "<a href='https://findahelpline.com' target='_blank'>findahelpline.com</a>.",
            icon="🛡️",
        ),
        unsafe_allow_html=True,
    )

    with st.expander("🔑  Keep an API key permanently (secrets.toml)"):
        st.code(
            '# .streamlit/secrets.toml\n'
            'GROQ_API_KEY = "gsk_..."\n'
            '# or\n'
            'GEMINI_API_KEY = "AIza..."\n'
            '# optional\n'
            'provider = "groq"\n'
            'companion_name = "Aanya"\n',
            language="toml",
        )
        st.caption("On Streamlit Community Cloud, paste these into the app's Secrets box instead.")


# --------------------------------------------------------------------------- #

def welcome_dialog(store: Store, companion: Companion) -> None:
    @st.dialog(f"Welcome to SensyGent {companion.emoji}")
    def _dialog() -> None:
        st.markdown(
            f"""
Hi. I'm **{companion.name}** — your mood companion.

- 🫂 **Talk to me** whenever the day gets heavy. I listen first, always.
- 🫧 **Check in** with a mood score — it builds a picture of your real week.
- 🧘 **Breathe with me** when your chest is tight.
- 🫙 **Keep a gratitude jar** for the days you can't remember anything good.

I'm **free forever**, need **no account**, and everything you write stays on this machine.
"""
        )
        st.markdown(
            styles.callout(
                "I'm a companion, not a therapist — and I'll always tell you when a real human "
                "would help more.", icon="💙",
            ),
            unsafe_allow_html=True,
        )
        if st.button("Let's begin  →", type="primary", width="stretch"):
            store.set_pref("welcome_done", "1")
            st.session_state["welcome_done"] = True
            st.rerun()

    _dialog()


def main() -> None:
    init_state()
    store = get_store()
    secrets = get_secrets()
    defaults = init_widget_defaults(store, secrets)

    styles.inject_theme(st.session_state.get("theme", palette.DEFAULT_THEME))

    companion = build_companion(store, secrets)
    sidebar(store, secrets, companion)
    companion = build_companion(store, secrets)
    persist_prefs(store, defaults)

    if not st.session_state.get("welcome_done"):
        welcome_dialog(store, companion)

    nav = st.session_state.get("nav", "talk")
    if nav == "talk":
        page_talk(store, companion)
    elif nav == "checkin":
        page_checkin(store, companion)
    elif nav == "calm":
        page_calm(store, companion)
    elif nav == "journal":
        page_journal(store, companion)
    elif nav == "gratitude":
        page_gratitude(store, companion)
    elif nav == "insights":
        page_insights(store, companion)
    elif nav == "settings":
        page_settings(store, companion, secrets)

    st.markdown(styles.footer(companion.name), unsafe_allow_html=True)
    drain_flash()


if __name__ == "__main__":
    main()
