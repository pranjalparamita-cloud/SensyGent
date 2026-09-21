# 🌸 SensyGent

**A free, beautiful AI companion that talks with you when you're low — and actually helps.**

No signup. No credit card. No API key required. Your private data never leaves your machine.

```bash
git clone <this repo> && cd SensyGent
pip install -r requirements.txt
streamlit run app.py
```

---

## What it is

SensyGent is a mood companion for heavy days. When you're sad, anxious, overwhelmed or just
exhausted, it listens, asks honest questions, and stays with you instead of dumping a list of
self-care tips on your head.

It was built on one rule: **reflect before you solve, and never fake positivity.**

### The things it actually does

| | |
|---|---|
| 💬 **Talk** | A real conversation, with a companion who has a name, a personality and pronouns |
| 🔊 **Speak** | Free neural voices — it can talk out loud, in 30+ languages |
| 🫧 **Check in** | A 20-second mood log that quietly builds a picture of your week |
| 🧘 **Calm** | Box breathing, 4-7-8, a 5-4-3-2-1 grounding walkthrough, body scan, a "one small thing" generator |
| 📖 **Journal** | Prompts that get past "I'm fine", saved privately |
| 🫙 **Gratitude jar** | A visual jar of small good things for the days you can't remember any |
| 📊 **Insights** | Gentle patterns — mood over time, what you tag most, what actually helps *you* |
| 🆘 **Safety net** | Crisis detection that always routes to real human helplines, on every single message |

---

## Why it's genuinely free

Most "AI therapy" apps charge a subscription. SensyGent ships with **two brains** and falls
back automatically:

**1. LocalCare — built in, offline, unlimited.** No API key, no internet, no limits. It's a
careful listening engine built on the parts of counselling that aren't magic: reflective
listening, validation, normalising, one good question at a time. It never repeats itself, and
it never tells you to "just stay positive".

**2. Any free LLM, if you want it.** Paste a free key from Groq, Google AI Studio (Gemini),
OpenRouter, or run a local model with Ollama, and your companion upgrades to a full LLM for
longer, richer replies. If the key expires, the quota runs out, or the internet drops,
LocalCare takes over mid-conversation — you never hit a dead end.

Voice is free too: it uses **edge-tts** (Microsoft's neural voices) then **gTTS**, both
keyless. No third-party TTS bill, ever.

---

## Deploy it free on Streamlit Community Cloud

1. **Push this folder to GitHub** (public or private both work).
2. Go to **[share.streamlit.io](https://share.streamlit.io)** and sign in with GitHub.
3. Click **Create app → Deploy a public app from GitHub**.
4. Pick your repository, set **Main file path** to `app.py`, choose any app URL you like.
5. Press **Deploy**. It's live in about a minute — free tier, no card.

**Optional:** in *Settings → Secrets*, paste a free key to unlock the LLM brain:

```toml
GROQ_API_KEY = "gsk_..."          # free at console.groq.com/keys
provider     = "groq"             # optional, pins the provider
companion_name = "Momo"           # what you'd like to call your companion
```

Local run, full control:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

---

## Make it yours

| Setting | Where | Options |
|---|---|---|
| **Companion** | sidebar → 🎭 | Aanya 🌸 (she/her), Aarav 🌿 (he/him), Mira 🌙 (she/her), Dev 🔥 (he/him), Sky ☁️ (they/them) |
| **Nickname** | sidebar → 🎭 | call them whatever feels right |
| **Tone** | sidebar → 🎭 | Gentle · Uplifting · Wise · Straight-talking |
| **Reply length** | sidebar → 🎭 | Short & sweet · Balanced · Deeper |
| **Theme** | sidebar → 🎨 | Aurora Night · Blush Dawn · Forest Zen · Sunset Warm · Soft Daylight |
| **Voice** | sidebar → 🔊 | 30+ neural voices, filtered to match your companion; pace from very slow to brisk |
| **Brain** | sidebar → 🧠 | LocalCare, Groq, Gemini, OpenRouter, DeepSeek, Ollama, or any OpenAI-compatible endpoint |

Everything you change is remembered in the local database. Nothing is sent anywhere.

---

## How it's built

```
app.py                  the Streamlit app — 7 pages, one design system
assets/styles.css       the whole visual language (~900 lines of hand-written CSS)
sensy/
  companion.py          personas, the system prompt, reply orchestration
  localcare.py          the offline listening engine (this is why it's free)
  mood.py               transparent lexicon emotion + safety detection
  llm.py                free providers, streaming, graceful failure
  voice.py              edge-tts → gTTS → optional device voice
  store.py              SQLite: moods, journal, gratitude, chats, prefs
  styles.py             HTML components (heroes, cards, the breath circle, the jar)
  palette.py            5 themes as CSS custom properties
  tools.py              breathing patterns, grounding scripts, helplines, prompts
tests/                  37 unit tests + 13 end-to-end app tests
```

```bash
python tests/test_sensy.py    # engine, mood reading, voice, storage, design system
python tests/test_app.py      # drives the real app end to end (Streamlit AppTest)
```

### The design system

Glassmorphic cards over a slowly drifting aurora, Fraunces headings, Plus Jakarta Sans body,
gradient-initial avatars, rippling ambient orbs, an animated breathing circle that paces your
inhale and exhale, a gratitude jar that fills with paper notes. All colours flow from CSS
custom properties, so switching theme re-skins every card, chart and button instantly.
Respects `prefers-reduced-motion`, keyboard focus rings, and mobile widths.

---

## Privacy

- Mood scores, journal entries, gratitude notes and chat history live in **one local SQLite
  file** (`data/sensygent.db`) and nowhere else.
- With an LLM provider enabled, only **your message text** is sent to that provider to generate
  a reply. Nothing else — not your mood history, not your journal, not your name.
- Export everything as a plain text file, or erase all of it, from the sidebar. No accounts,
  no analytics, no tracking, `gatherUsageStats = false`.

---

## A necessary limit

**SensyGent is a companion, not a therapist.** It can't diagnose, prescribe, or replace real
care, and it will tell you so when that matters.

If you're in crisis or thinking about harming yourself, please reach out to a human right now:

| | |
|---|---|
| 🇺🇸 **988** | Suicide & Crisis Lifeline (call or text) |
| 🇬🇧 **116 123** | Samaritans, free 24/7 |
| 🇮🇳 **14416** | Tele-MANAS · AASRA +91 98204 66726 |
| 🇦🇺 **13 11 14** | Lifeline Australia |
| 🌍 **[findahelpline.com](https://findahelpline.com)** | every country, free |

SensyGent detects crisis language on every message and shows these numbers immediately — no
LLM required, no waiting, no judgement.

---

## License

MIT — use it, fork it, change the companions' names, deploy it for people you love.
Made with care. 💙
