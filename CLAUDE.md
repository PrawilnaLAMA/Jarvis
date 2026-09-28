# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Jarvis is a Polish-language voice assistant with an HTML/CSS/JS UI. Everything the user sees or hears (prompts, replies, UI text, error messages) is Polish. Code identifiers are English, and comments/docstrings are Polish; match that. Commit messages are in Polish.

## Commands

```
py -m pip install -r requirements-dev.txt   # Windows uses the `py` launcher (global Python 3.11, .venv is unused)
py -m jarvis [--browser] [--no-voice] [--fullscreen] [--port N] [--debug]
py -m pytest                                 # all tests
py -m pytest tests/test_voice_loop.py -k barge   # single test
py -m ruff check .                           # lint (line length 120)
make pi-setup && make pi-run                 # Raspberry Pi 4/5, 64-bit OS
```

`--no-voice` runs without microphone/TTS (typed commands only), which is the fastest way to exercise the assistant. Logs go to `data/jarvis.log`.

`jarvis.bat` and Windows autostart run `jarvis.pyw` through `pythonw`, so there is no console. Under `pythonw`, `sys.stdout`/`stderr` are `None`: `__main__` swaps in devnull (uvicorn calls `isatty()`), unhandled exceptions go to the log, and a startup failure shows a message box. Console subprocesses need `CREATE_NO_WINDOW` (see `tools/base._run_command`). Only one instance runs: if the UI port is taken by a Jarvis, a second start calls `POST /api/window/show` (bus `ui.show`, which brings the window to front) and exits. Autostart is the `HKCU\...\Run` value "Jarvis" (`jarvis/autostart.py`). The registry is the source of truth, toggled from Settings → Interfejs via `/api/autostart`, and `refresh()` rewrites a stale path on start. Tests use their own registry key.

## Architecture

`jarvis/app.py` `JarvisApp` is the composition root. `jarvis/__main__.py` starts uvicorn in a background thread (`web/server.py`) and runs the pywebview window on the main thread (`ui/window.py`). pywebview must own the main thread; if it is missing, the app falls back to a browser.

**Data flow.** Background threads never touch the UI directly. They publish to `events.EventBus` (topics are documented in its module docstring). `web/server.py` `WebSocketHub` forwards every event to `/ws` clients and keeps chat history for reconnecting clients. `state.StatusTracker` merges listener, transcribing, thinking, and speaking into the single `state` the orb displays. The UI contract (REST + WS) is what `jarvis/web/static/js/*` expects, so change both sides together.

**Command understanding.** `assistant.Assistant.handle()` makes one LLM call with function calling (Groq `openai/gpt-oss-120b` via `llm.LLMClient`, with fallback to Cerebras on 429). Tools live in `jarvis/tools/`. To add one, write `handler(ctx, args) -> str`, add a `Tool(...)` to that module's `tools()`, and register the module in `tools/__init__.py:build_tools`. `speak_directly=True` means the handler's return string is the spoken reply, with no second LLM round. Informational tools set it to False, so the model phrases the answer. Raise `ToolError` with a Polish message for user-facing failures.

The system prompt is static so Groq can cache the prefix. Dynamic context (current date, the next-14-days table used for relative dates, and interruption notes) is prepended to the latest user message in a `<kontekst>` block by `build_context`. The free Groq tier allows about 8K tokens/min, and a request is about 1.3–1.5K tokens, so keep tool descriptions and the prompt short.

**Voice pipeline** (`jarvis/audio/`):
- **Mic loop.** `voice_loop.VoiceLoop.process_frame` handles 80 ms, 16 kHz int16 frames and never blocks on the network. A worker thread does STT, then `app.respond`, then TTS.
- **Wake word.** openWakeWord "hey_jarvis" runs through onnx, with models downloaded to `data/models`. A score between `threshold × SOFT_WAKE_RATIO` and the threshold starts a silent "tentative" recording, which is accepted only if Whisper's transcript contains "Jarvis". This catches "Hej Jarvis, która…" said without a pause.
- **STT.** `stt.WhisperSTT` uses Groq `whisper-large-v3`, prompted with contact names. `transcript.py` strips the wake phrase and filters Whisper hallucinations.
- **TTS.** `tts.EdgeTTS` synthesizes sentence by sentence while `player.Player` is already playing. The player tracks sample position, which drives word events, subtitles, and knowing what was said before an interruption. It also handles gain ramps (duck/stop) and output level.
- **Barge-in** (`bargein.py`). `EchoGate` learns the mic/output echo ratio, then `DuckTest` ducks Jarvis to −16 dB and checks whether the mic level stays above the expected echo. An "uncertain" result means Jarvis keeps talking; it does not transcribe. Transcripts of confirmed interruptions are still rejected if they are Jarvis's own words (`transcript.is_echo`). The interrupted reply is rewritten in history via `Conversation.mark_interrupted`, and the LLM gets the spoken fragment as context.
- **Follow-up.** After an uninterrupted reply, the user can speak for `follow_up_seconds` without the wake word.

**Messaging.** Contacts have `channel_id` (Discord), `messenger` (messenger.com chat link or id, normalized by `settings.messenger_thread`), or both. The tool `tools/messaging.py:send_message` picks the app: the one the user named, else the one the contact last wrote from (`services/inbox.Inbox`), else the contact's first app. Both monitors report incoming messages to `Inbox.receive`, which speaks them, publishes `discord.message`/`messenger.message`, and remembers the last one. `build_context` adds that last message, so "odpisz jej" works.

**Messenger** (`services/messenger.py`). There is no API for personal accounts and chats are E2EE, so Playwright drives messenger.com in Chrome (then Edge, then Chromium; the user wants Chrome) with a persistent profile in `data/messenger`. The window is headed because login and the E2EE PIN need it; it is minimized once logged in. The sync Playwright API must stay on one thread: `MessengerService` owns a worker thread, and other threads submit work through a queue of futures. `BrowserSession` is the seam, faked in `tests/test_messenger.py`. Incoming messages are read from the chat-list row previews (`parse_row`: name / text / `·` / time), without opening the chat, so no "seen" receipt. Only real chat links count (`_CHAT_HREF`); nav links like `/t/…?focus_target`, `/requests/t/…` look similar. The E2EE placeholder ("…chronione przy użyciu pełnego szyfrowania") is ignored, and only previews at most `FRESH_MINUTES` old are announced, because restored history also changes previews. Sending clicks the chat row, types into `div[role=textbox]` (Lexical), presses Enter, and waits for the box to empty.

**Persistence.** User data lives in `data/` (gitignored): `settings.json`, `conversation.json`, `models/`, `messenger/` (browser profile), and `domownik/` (household data). Secrets stay in `.env` (`GROQ_API_KEY`, `CEREBRAS_API_KEY`, `DISCORD_USER_TOKEN`; legacy `USER_TOKEN` is still read). `settings.Secrets` writes them from the UI. `settings.SettingsStore.update` deep-merges partial dicts, validates them with Polish error messages, and publishes `settings.changed`. Every path comes from `paths.py`, so nothing depends on the CWD. The first run migrates the old `cache/` conversation and `CHANNEL_*` env contacts.

**Domownik (the "Dom" tab).** Household chores (people `leon`/`natalia`, "na zmianę" rotation), calendar, shopping list, and Natalia's work schedule. It was the separate HouseholdChoresApp and now lives in `jarvis/domownik/` as a Flask app (`create_app(data_file)`); its internals and pitfalls are in `jarvis/domownik/CLAUDE.md`. `services/domownik_server.DomownikServer` runs it under waitress in a thread on its own port (`settings.domownik.port`, default 8080), bound to 0.0.0.0 when `lan=True` so phones and the PWA work. The Jarvis control API stays on 127.0.0.1. Settings changes restart it live, and a busy port (usually the old `start-serwer.bat`) gives state `error` and retries. It reacts to settings only after `start()`, so API tests never open a port. Tools still talk to it over HTTP (`services/domownik_client.py`, base URL `DomownikSettings.base_url`): the built-in server, or `url` when `serve=False`, e.g. a PC Jarvis using the Domownik of a Pi Jarvis. Only one server may own a data file (in-process `RLock`). Tools are in `tools/domownik.py`; the user is Leon, so agenda output groups items by person as "twoje: …; Natalia: …; wspólne: …" (the model misattributed chores when it saw "Leon"). Chores have no time of day and there are no reminders. Titles are fuzzy-matched word by word on shared word prefixes, because Polish inflection changes endings ("mleka"/"mleko"), and a whole-string ratio would match "odkurzanie" to "pranie". The UI's Dom tab embeds the Domownik site in an iframe (`static/js/domownik.js`), and `ui.navigate {view: "dom", path}` opens a subpage. Inside the frame Domownik hides its logo (`is-embedded`) and refreshes itself live over SSE. Its style copies Jarvis's tokens (dark only), so change both palettes together.

## Testing notes

Audio and LLM code is tested with fakes; see `tests/test_voice_loop.py` (fake wake/VAD/STT/speaker and synthetic frames) and `tests/test_player.py` (`_callback` driven directly and a fake `OutputStream`). No test needs a microphone, network, or API key. For end-to-end checks without a microphone, synthesize speech with `EdgeTTS`, resample it to 16 kHz, and feed its frames to `VoiceLoop.process_frame`.

## Gotchas

- `shutdown_computer` really schedules a shutdown (30 s delay by default). Tests stub `ToolContext.run_command`, and so should any manual experiments.
- Discord uses a user token (self-bot), and messages go out from the user's own account.
- Messenger experiments use the user's logged-in real account (`data/messenger`). Never send a message or open a chat without asking. Mask names and message text in any DOM probe. Only one process at a time can use the profile, so close Jarvis first.
- `scripts/usos/` are standalone USOS timetable scripts that read `USOS_*` from `.env` and need `requests-oauthlib`.
- `data/domownik/chores.json` is the household's real data (phones write to it too). Never point experiments at it: build `create_app(tmp_path / "chores.json")`, or run `JarvisApp(data_dir=<temp dir>, voice=False)` with a copy and `{"domownik": {"lan": False, "port": <free port>}}`. Never bind 0.0.0.0 in experiments. Tool tests use `FakeDomownik` from `tests/conftest.py`.
- The old HouseholdChoresApp repo is no longer used. Running its `start-serwer.bat` next to Jarvis would take port 8080, and its data would diverge from `data/domownik/`.
