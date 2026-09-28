"""Wspólne typy narzędzi (function calling)."""

import subprocess
import sys
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import requests

from jarvis.conversation import Conversation
from jarvis.events import EventBus
from jarvis.services.discord_client import DiscordClient
from jarvis.services.domownik_client import DomownikClient
from jarvis.services.inbox import Inbox
from jarvis.services.messenger import MessengerService
from jarvis.settings import SettingsStore


class ToolError(Exception):
    """Błąd z komunikatem dla użytkownika (po polsku)."""


def _http_get(url: str) -> str:
    response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "pl-PL"})
    response.raise_for_status()
    return response.text


def _run_command(args: list[str]) -> None:
    # pod pythonw (bez konsoli) program konsolowy mignąłby własnym oknem cmd
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.run(args, check=True, capture_output=True, timeout=10, creationflags=flags)


@dataclass
class ToolContext:
    """Zależności narzędzi – w testach podmieniane na atrapy."""

    settings: SettingsStore
    bus: EventBus
    domownik: DomownikClient  # kalendarz: obowiązki domowe, zakupy, grafik pracy
    discord: DiscordClient
    messenger: MessengerService
    inbox: Inbox  # ostatnia wiadomość przychodząca – do „odpisz jej”
    conversation: Conversation
    open_url: Callable[[str], Any] = webbrowser.open
    http_get: Callable[[str], str] = _http_get
    run_command: Callable[[list[str]], None] = _run_command
    clock: Callable[[], datetime] = field(default=datetime.now)


Handler = Callable[[ToolContext, dict[str, Any]], str]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Handler
    # True: wynik narzędzia jest od razu odpowiedzią dla użytkownika (bez drugiego zapytania do LLM).
    # False: wynik wraca do modelu, który formułuje odpowiedź (np. lista wydarzeń).
    speak_directly: bool = True

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


def params(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties or {}, "required": required or []}
