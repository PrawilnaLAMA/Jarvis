"""Nasłuchiwanie nowych wiadomości w kanałach kontaktów (polling REST)."""

import logging
import threading

from jarvis.events import EventBus
from jarvis.services.discord_client import DiscordClient, DiscordError
from jarvis.services.inbox import Inbox
from jarvis.settings import SettingsStore

log = logging.getLogger(__name__)


class DiscordMonitor:
    def __init__(self, client: DiscordClient, settings: SettingsStore, bus: EventBus, inbox: Inbox):
        self._client = client
        self._settings = settings
        self._bus = bus
        self._inbox = inbox
        self._last_ids: dict[str, str | None] = {}
        self._last_error = ""

    def poll_once(self) -> list[str]:
        """Sprawdza każdy kanał raz; zwraca teksty ogłoszonych wiadomości."""
        settings = self._settings.get()
        my_id = self._client.me()["id"]
        announced = []
        for contact in settings.contacts:
            channel_id = contact.channel_id.strip()
            if not channel_id:
                continue  # kontakt tylko z Messengera
            message = self._client.latest_message(channel_id)
            msg_id = message["id"] if message else None
            if channel_id not in self._last_ids:
                # pierwszy odczyt kanału – zapamiętujemy stan bez ogłaszania starych wiadomości
                self._last_ids[channel_id] = msg_id
                continue
            if not message or msg_id == self._last_ids[channel_id]:
                continue
            self._last_ids[channel_id] = msg_id
            if message["author"]["id"] == my_id:
                continue
            content = message.get("content", "")
            announced.append(self._inbox.receive("discord", contact, content, settings.discord.read_aloud))
        return announced

    def run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            settings = self._settings.get()
            if self._client.configured and any(c.channel_id.strip() for c in settings.contacts):
                try:
                    self.poll_once()
                    self._last_error = ""
                except DiscordError as e:
                    # ten sam błąd zgłaszamy tylko raz, żeby nie zasypać UI
                    if str(e) != self._last_error:
                        self._last_error = str(e)
                        self._bus.notice(f"Discord: {e}", "warning")
                except Exception:
                    log.exception("Błąd monitorowania Discorda")
            stop.wait(settings.discord.poll_seconds)
