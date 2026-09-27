"""Historia rozmowy z Jarvisem – krótka pamięć kontekstu dla modelu."""

import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.jsonfile import read_json, write_json

INTERRUPTED_MARK = "[przerwano]"
_STORED_MESSAGES = 50


class Conversation:
    def __init__(self, path: Path, max_messages: Callable[[], int]):
        self._path = path
        self._max_messages = max_messages
        self._lock = threading.Lock()
        raw = read_json(path, [])
        self._items: list[dict[str, Any]] = [
            m for m in raw if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")
        ] if isinstance(raw, list) else []

    def messages(self) -> list[dict[str, str]]:
        """Ostatnie wiadomości w formacie dla modelu (bez znaczników czasu)."""
        with self._lock:
            limit = max(0, self._max_messages())
            items = self._items[-limit:] if limit else []
            # model nie powinien zaczynać kontekstu od własnej odpowiedzi
            while items and items[0]["role"] != "user":
                items = items[1:]
            return [{"role": m["role"], "content": m["content"]} for m in items]

    def add(self, role: str, content: str) -> None:
        with self._lock:
            self._items.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})
            self._items = self._items[-_STORED_MESSAGES:]
            write_json(self._path, self._items)

    def mark_interrupted(self, spoken: str) -> None:
        """Zastępuje ostatnią odpowiedź Jarvisa tym, co faktycznie zdążył powiedzieć."""
        with self._lock:
            for item in reversed(self._items):
                if item["role"] == "assistant":
                    item["content"] = f"{spoken.strip()}… {INTERRUPTED_MARK}" if spoken.strip() else INTERRUPTED_MARK
                    break
            write_json(self._path, self._items)

    def clear(self) -> None:
        with self._lock:
            self._items = []
            write_json(self._path, self._items)
