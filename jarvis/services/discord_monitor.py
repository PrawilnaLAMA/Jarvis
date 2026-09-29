"""Nasłuchiwanie nowych wiadomości w kanałach kontaktów (polling REST)."""

import logging
import threading
import time
from collections.abc import Callable

from jarvis.events import EventBus
from jarvis.services.discord_client import DiscordClient, DiscordError
from jarvis.services.inbox import Inbox
from jarvis.settings import SettingsStore

log = logging.getLogger(__name__)

# Discord co jakiś czas odpowiada 503 albo zrywa połączenie, a chwilę później działa – takie czkawki
# ponawiamy po cichu. Komunikat pokazujemy dopiero, gdy nie odpowiada dłużej niż tyle sekund.
OUTAGE_SECONDS = 120
MAX_BACKOFF_SECONDS = 60
# zwykłe wiadomości i odpowiedzi; reszta (połączenia, przypięcia, dołączenia) to wpisy systemowe
USER_MESSAGE_TYPES = {0, 19}


class DiscordMonitor:
    def __init__(
        self,
        client: DiscordClient,
        settings: SettingsStore,
        bus: EventBus,
        inbox: Inbox,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._client = client
        self._settings = settings
        self._bus = bus
        self._inbox = inbox
        self._clock = clock
        self._last_ids: dict[str, str | None] = {}
        self._last_authors: dict[str, str | None] = {}  # kto napisał ostatnią wiadomość w kanale
        self._last_error = ""  # trwały błąd (np. zły token) zgłoszony już raz
        self._failures = 0  # kolejne chwilowe błędy z rzędu
        self._failing_since: float | None = None
        self._outage_reported = False

    def poll_once(self) -> list[str]:
        """Sprawdza każdy kanał raz; zwraca teksty ogłoszeń (jedno na ciąg wiadomości jednej osoby)."""
        settings = self._settings.get()
        my_id = self._client.me()["id"]
        announced = []
        for contact in settings.contacts:
            channel_id = contact.channel_id.strip()
            if not channel_id:
                continue  # kontakt tylko z Messengera
            if channel_id not in self._last_ids:
                # pierwszy odczyt kanału – zapamiętujemy stan bez ogłaszania starych wiadomości
                message = self._client.latest_message(channel_id)
                self._last_ids[channel_id] = message["id"] if message else None
                self._last_authors[channel_id] = message["author"]["id"] if message else None
                continue
            messages = self._client.messages_after(channel_id, self._last_ids[channel_id])
            if not messages:
                continue
            self._last_ids[channel_id] = messages[-1]["id"]
            # kilka wiadomości szybko po sobie czytamy wszystkie, po kolei; imię tylko, gdy zmienia się piszący
            runs: list[tuple[str, list[str]]] = []  # (autor, treści) – kolejne wiadomości jednej osoby
            for message in messages:
                if message.get("type", 0) not in USER_MESSAGE_TYPES:
                    continue
                author, content = message["author"]["id"], message.get("content", "")
                if runs and runs[-1][0] == author:
                    runs[-1][1].append(content)
                else:
                    runs.append((author, [content]))
            for author, contents in runs:
                if author != self._last_authors.get(channel_id):
                    self._inbox.end_run()  # odpisał użytkownik albo (w grupie) napisał ktoś inny
                self._last_authors[channel_id] = author
                if author != my_id:
                    announced.append(
                        self._inbox.receive_many("discord", contact, contents, settings.discord.read_aloud)
                    )
        return announced

    def check(self) -> float:
        """Jedno odpytanie z obsługą błędów; zwraca, ile sekund czekać do następnego."""
        settings = self._settings.get()
        interval = settings.discord.poll_seconds
        if not (self._client.configured and any(c.channel_id.strip() for c in settings.contacts)):
            return interval
        try:
            self.poll_once()
        except DiscordError as e:
            return self._failed(e, interval)
        except Exception:
            log.exception("Błąd monitorowania Discorda")
            return interval
        if self._outage_reported:
            self._bus.notice("Discord znów odpowiada.", "info")
        self._failures, self._failing_since, self._outage_reported, self._last_error = 0, None, False, ""
        return interval

    def _failed(self, error: DiscordError, interval: float) -> float:
        if not error.temporary:
            if str(error) != self._last_error:  # ten sam trwały błąd zgłaszamy tylko raz
                self._last_error = str(error)
                self._bus.notice(f"Discord: {error}", "warning")
            return interval
        now = self._clock()
        if self._failing_since is None:
            self._failing_since = now
        self._failures += 1
        log.info("Discord chwilowo nie odpowiada (%s) – próba %d", error, self._failures)
        down = now - self._failing_since
        if not self._outage_reported and down >= OUTAGE_SECONDS:
            self._outage_reported = True
            self._bus.notice(f"Discord nie odpowiada od {down / 60:.0f} min ({error}) – sprawdzam dalej.", "warning")
        return min(interval * 2**self._failures, MAX_BACKOFF_SECONDS)

    def run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            stop.wait(self.check())
