"""Wiadomości przychodzące z komunikatorów (Discord, Messenger).

Monitory komunikatorów zgłaszają tu nowe wiadomości od kontaktów. Skrzynka czyta je na głos,
wysyła zdarzenie do UI i pamięta ostatnią – dzięki temu „odpisz jej, że OK” trafia do właściwej
osoby i przez ten sam komunikator.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from jarvis.events import EventBus
from jarvis.settings import Contact

APP_NAMES = {"discord": "Discord", "messenger": "Messenger"}
APP_LOCATIVE = {"discord": "na Discordzie", "messenger": "na Messengerze"}
APP_GENITIVE = {"discord": "Discorda", "messenger": "Messengera"}


@dataclass(frozen=True)
class IncomingMessage:
    app: str  # discord | messenger
    contact: str  # nazwa kontaktu z ustawień, np. "NATALIA"
    author: str  # nazwa do wyświetlenia, np. "Natalia"
    content: str
    received_at: float


class Inbox:
    def __init__(self, bus: EventBus, speak: Callable[[str], None], clock: Callable[[], float] = time.time):
        self._bus = bus
        self._speak = speak
        self._clock = clock
        self._last: IncomingMessage | None = None
        self._lock = threading.Lock()

    def receive(self, app: str, contact: Contact, content: str, read_aloud: bool) -> str:
        """Ogłasza nową wiadomość; zwraca wypowiadany tekst."""
        content = content.strip()
        # komunikator podajemy tylko wtedy, gdy kontakt jest w kilku – inaczej to zbędne słowa
        where = f" {APP_LOCATIVE[app]}" if len(contact.apps) > 1 else ""
        text = (
            f"{contact.display_name} pisze{where}: {content}"
            if content
            else f"{contact.display_name} przesyła załącznik{where}."
        )
        message = IncomingMessage(app, contact.name, contact.display_name, content, self._clock())
        with self._lock:
            self._last = message
        self._bus.publish(f"{app}.message", author=contact.display_name, content=content, contact=contact.name)
        if read_aloud:
            self._speak(text)
        return text

    def last(self, max_age: float = 30 * 60) -> IncomingMessage | None:
        """Ostatnia wiadomość, jeśli przyszła niedawno (starsza nie jest już kontekstem rozmowy)."""
        with self._lock:
            message = self._last
        if message and self._clock() - message.received_at <= max_age:
            return message
        return None

    def last_app_of(self, contact_name: str) -> str | None:
        """Komunikator, którym kontakt ostatnio pisał – tam domyślnie odpowiadamy."""
        with self._lock:
            message = self._last
        return message.app if message and message.contact == contact_name else None
