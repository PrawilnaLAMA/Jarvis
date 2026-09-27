"""Ścieżki projektu – wszystko liczone od katalogu repozytorium, nie od CWD."""

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parent
ENV_FILE = ROOT / ".env"
STATIC_DIR = PACKAGE_DIR / "web" / "static"

# Katalog danych użytkownika (gitignored); można nadpisać, np. w testach
DATA_DIR = Path(os.environ.get("JARVIS_DATA_DIR", ROOT / "data"))
MODELS_DIR = DATA_DIR / "models"
SETTINGS_FILE = DATA_DIR / "settings.json"
EVENTS_FILE = DATA_DIR / "events.json"
CONVERSATION_FILE = DATA_DIR / "conversation.json"
REMINDERS_STATE_FILE = DATA_DIR / "reminders_state.json"
LOG_FILE = DATA_DIR / "jarvis.log"

# Lokalizacje danych sprzed refaktoru (do jednorazowej migracji)
LEGACY_EVENTS_FILE = ROOT / "calendar_app" / "events.json"
LEGACY_CONVERSATION_FILE = ROOT / "cache" / "conversation_history_default.json"
