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

**Persistence.** User data lives in `data/` (gitignored): `settings.json`, `events.json`, `conversation.json`, `reminders_state.json`, and `models/`. Secrets stay in `.env` (`GROQ_API_KEY`, `CEREBRAS_API_KEY`, `DISCORD_USER_TOKEN`; legacy `USER_TOKEN` is still read). `settings.Secrets` writes them from the UI. `settings.SettingsStore.update` deep-merges partial dicts, validates them with Polish error messages, and publishes `settings.changed`. Every path comes from `paths.py`, so nothing depends on the CWD. The first run migrates old `calendar_app/events.json`, `cache/`, and `CHANNEL_*` env contacts.

**Calendar.** `services/calendar_store.py` stores events with either `date` or `days` (English weekday names). Reminders are tracked per occurrence (`id|date`), so recurring events remind every week.

## Testing notes

Audio and LLM code is tested with fakes; see `tests/test_voice_loop.py` (fake wake/VAD/STT/speaker and synthetic frames) and `tests/test_player.py` (`_callback` driven directly and a fake `OutputStream`). No test needs a microphone, network, or API key. For end-to-end checks without a microphone, synthesize speech with `EdgeTTS`, resample it to 16 kHz, and feed its frames to `VoiceLoop.process_frame`.

## Gotchas

- `shutdown_computer` really schedules a shutdown (30 s delay by default). Tests stub `ToolContext.run_command`, and so should any manual experiments.
- Discord uses a user token (self-bot), and messages go out from the user's own account.
- `scripts/usos/` are standalone USOS timetable scripts that read `USOS_*` from `.env` and need `requests-oauthlib`.
