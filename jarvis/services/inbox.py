"""Wiadomości przychodzące z komunikatorów (Discord, Messenger).

Monitory komunikatorów zgłaszają tu nowe wiadomości od kontaktów. Skrzynka czyta je na głos,
wysyła zdarzenie do UI i pamięta ostatnią – dzięki temu „odpisz jej, że OK” trafia do właściwej
osoby i przez ten sam komunikator.

Kilka wiadomości tej samej osoby pod rząd to jeden ciąg: imię pada tylko na początku („Natalia pisze:
hej. Kupisz mleko?”), a kolejne, które doszły chwilę później, są czytane już bez niego. Ciąg kończy
wiadomość od kogoś innego, odpowiedź użytkownika (end_run) albo rozmowa z Jarvisem.
"""

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from jarvis.events import EventBus
from jarvis.settings import Contact

APP_NAMES = {"discord": "Discord", "messenger": "Messenger"}
APP_LOCATIVE = {"discord": "na Discordzie", "messenger": "na Messengerze"}
APP_GENITIVE = {"discord": "Discorda", "messenger": "Messengera"}

# po tylu sekundach ciszy kolejna wiadomość tej samej osoby znowu zaczyna się od imienia
CONTINUE_SECONDS = 120
_SENTENCE_END = re.compile(r"[.!?…:;]$")


@dataclass(frozen=True)
class IncomingMessage:
    app: str  # discord | messenger
    contact: str  # nazwa kontaktu z ustawień, np. "NATALIA"
    author: str  # nazwa do wyświetlenia, np. "Natalia"
    content: str  # cały bieżący ciąg wiadomości tej osoby
    received_at: float


def _join(parts: list[str]) -> str:
    """Skleja wiadomości w jedną wypowiedź – z kropką między nimi, żeby głos robił pauzę."""
    return " ".join(p if i == len(parts) - 1 or _SENTENCE_END.search(p) else f"{p}." for i, p in enumerate(parts))


class Inbox:
    def __init__(self, bus: EventBus, speak: Callable[[str], None], clock: Callable[[], float] = time.time):
        self._bus = bus
        self._speak = speak
        self._clock = clock
        self._last: IncomingMessage | None = None
        self._run_open = False  # ostatni ciąg wiadomości trwa – następna od tej osoby bez imienia
        self._lock = threading.Lock()
        # użytkownik mówi do Jarvisa albo Jarvis odpowiada – potem wiadomość znowu musi mówić, od kogo jest
        bus.subscribe(lambda _: self.end_run(), {"transcript", "reply"})

    def receive(self, app: str, contact: Contact, content: str, read_aloud: bool) -> str:
        """Ogłasza nową wiadomość; zwraca wypowiadany tekst."""
        return self.receive_many(app, contact, [content], read_aloud)

    def receive_many(self, app: str, contact: Contact, contents: list[str], read_aloud: bool) -> str:
        """Ogłasza kolejne wiadomości jednej osoby (od najstarszej) jednym komunikatem; zwraca jego tekst."""
        contents = [c.strip() for c in contents]
        now = self._clock()
        with self._lock:
            last = self._last
            continued = bool(
                self._run_open
                and last
                and (last.app, last.contact) == (app, contact.name)
                and now - last.received_at <= CONTINUE_SECONDS
            )
            # komunikator podajemy tylko wtedy, gdy kontakt jest w kilku – inaczej to zbędne słowa
            where = f" {APP_LOCATIVE[app]}" if len(contact.apps) > 1 else ""
            parts = []
            for content in contents:
                if parts or continued:
                    parts.append(content or "Do tego załącznik.")
                elif content:
                    parts.append(f"{contact.display_name} pisze{where}: {content}")
                else:
                    parts.append(f"{contact.display_name} przesyła załącznik{where}.")
            text = _join(parts)
            run = _join([c or "(załącznik)" for c in contents])
            if continued:
                run = _join([last.content, run])
            self._last = IncomingMessage(app, contact.name, contact.display_name, run, now)
            self._run_open = True
        for content in contents:
            self._bus.publish(f"{app}.message", author=contact.display_name, content=content, contact=contact.name)
        if read_aloud:
            self._speak(text)
        return text

    def end_run(self) -> None:
        """Następna wiadomość zacznie się od imienia (np. użytkownik właśnie odpisał)."""
        with self._lock:
            self._run_open = False

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
