"""Wspólne typy narzędzi (function calling)."""

import os
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


# pod pythonw (bez konsoli) program konsolowy mignąłby własnym oknem cmd
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _run_command(args: list[str]) -> None:
    subprocess.run(args, check=True, capture_output=True, timeout=10, creationflags=_NO_WINDOW)


def _launch(args: list[str]) -> None:
    """Uruchamia program i nie czeka na niego (aplikacja, folder, strona ustawień)."""
    subprocess.Popen(args, creationflags=_NO_WINDOW, close_fds=True)


def _powershell(script: str, env: dict[str, str] | None = None) -> str:
    """Nasz stały skrypt PowerShell; to, co podał użytkownik, wchodzi tylko przez zmienne środowiska
    (nigdy doklejone do kodu). Zwraca wyjście jako tekst."""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         "[Console]::OutputEncoding = [Text.Encoding]::UTF8\n" + script],
        capture_output=True, timeout=30, creationflags=_NO_WINDOW, env={**os.environ, **(env or {})},
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, "powershell", result.stdout, result.stderr)
    return result.stdout.decode("utf-8", errors="replace").strip()


def _press_key(vk: int, times: int = 1) -> None:
    """Klawisz multimedialny (głośność, pauza…) – działa z każdym odtwarzaczem, jak klawisze na klawiaturze."""
    import ctypes

    user32 = ctypes.windll.user32
    for _ in range(times):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP


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
    launch: Callable[[list[str]], None] = _launch
    powershell: Callable[..., str] = _powershell
    press_key: Callable[[int, int], None] = _press_key
    announce: Callable[[str], None] = lambda text: None  # mówi na głos (minutnik); JarvisApp podaje swój
    clock: Callable[[], datetime] = field(default=datetime.now)
    state: dict[str, Any] = field(default_factory=dict)  # pamięć narzędzi (minutniki, lista aplikacji)


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
