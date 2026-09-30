"""Składanie aplikacji: serwisy, wątki w tle i reakcja na polecenia."""

import logging
import threading
import time
from pathlib import Path
from typing import Any

from jarvis import __version__, paths
from jarvis.assistant import Assistant, Interruption
from jarvis.conversation import Conversation
from jarvis.events import EventBus
from jarvis.llm import LLMClient, providers_from
from jarvis.migration import migrate_legacy_data
from jarvis.services.discord_client import DiscordClient
from jarvis.services.discord_monitor import DiscordMonitor
from jarvis.services.domownik_client import DomownikClient
from jarvis.services.domownik_server import DomownikServer
from jarvis.services.inbox import Inbox
from jarvis.services.messenger import MessengerService
from jarvis.services.reminders import Reminders
from jarvis.services.timers import Timers
from jarvis.settings import Secrets, SettingsStore
from jarvis.state import StatusTracker
from jarvis.tools import ToolContext

log = logging.getLogger(__name__)


class JarvisApp:
    def __init__(
        self,
        data_dir: Path = paths.DATA_DIR,
        env_file: Path = paths.ENV_FILE,
        voice: bool = True,
        llm: LLMClient | None = None,
    ):
        data_dir.mkdir(parents=True, exist_ok=True)
        if data_dir == paths.DATA_DIR:
            migrate_legacy_data()
        self.bus = EventBus()
        self.secrets = Secrets(env_file)
        self.settings = SettingsStore(
            data_dir / "settings.json", on_change=lambda _: self.bus.publish("settings.changed")
        )
        self.tracker = StatusTracker(self.bus)
        # Domownik (obowiązki, zakupy, grafik) działa w Jarvisie na własnym porcie; narzędzia rozmawiają z nim
        # przez HTTP, więc tak samo obsłużą Domownika z innego komputera (adres czytany przy każdym zapytaniu)
        self.domownik_server = DomownikServer(self.settings, self.bus, data_dir / "domownik" / "chores.json")
        self.domownik = DomownikClient(lambda: self.settings.get().domownik.base_url)
        self.conversation = Conversation(
            data_dir / "conversation.json", lambda: self.settings.get().llm.history_messages
        )
        self.discord = DiscordClient(lambda: self.secrets.discord_token)
        self.inbox = Inbox(self.bus, self.announce)
        # profil przeglądarki z zalogowanym Messengerem – jak dane użytkownika, poza repozytorium
        self.messenger = MessengerService(self.settings, self.bus, self.inbox, data_dir / "messenger")
        self.llm = llm or LLMClient(
            lambda: providers_from(self.settings.get(), self.secrets),
            on_limit_wait=lambda s: self.bus.notice(f"Limit zapytań do modelu – czekam {s:.0f} s…", "warning"),
        )
        self.timers = Timers(self.bus, self.announce)  # odliczanie w kuli; mówi, gdy minie czas
        # przypomnienia z kalendarza: dźwięk, głos i czerwona kula aż do kliknięcia
        self.reminders = Reminders(self.bus, self.domownik, data_dir / "reminders.json", self.alert)
        tool_context = ToolContext(
            settings=self.settings,
            bus=self.bus,
            domownik=self.domownik,
            discord=self.discord,
            messenger=self.messenger,
            inbox=self.inbox,
            conversation=self.conversation,
            announce=self.announce,
            timers=self.timers,
        )
        self.assistant = Assistant(self.llm, tool_context, self.settings, self.bus, self.conversation)
        self.stop_event = threading.Event()

        self.voice = None
        if voice:
            from jarvis.audio.service import VoiceService  # import opóźniony: bez głosu nie potrzeba sounddevice

            self.voice = VoiceService(
                self.settings, self.secrets, self.bus, self.tracker, data_dir / "models", self._respond_voice
            )
        else:
            self.tracker.set_listener("idle")

        self.discord_monitor = DiscordMonitor(self.discord, self.settings, self.bus, self.inbox)
        status_topics = {"voice.status", "messenger.status", "domownik.status", "settings.changed"}
        self.bus.subscribe(lambda _: self.publish_status(), status_topics)

    # --- cykl życia ---

    def start(self) -> None:
        self.domownik_server.start()
        if self.voice:
            self.voice.start(self.stop_event)
        threading.Thread(target=self.discord_monitor.run, args=(self.stop_event,), name="discord", daemon=True).start()
        threading.Thread(target=self.reminders.run, args=(self.stop_event,), name="reminders", daemon=True).start()
        self.messenger.start(self.stop_event)
        if not self.llm.configured:
            self.bus.notice("Brak klucza GROQ_API_KEY – dodaj go w Ustawieniach, żeby Jarvis mógł odpowiadać.",
                            "warning")

    def shutdown(self) -> None:
        self.stop_event.set()
        self.messenger.join(5)  # zamknięcie przeglądarki, żeby nie została w tle
        if self.voice:
            self.voice.close()
        self.domownik_server.close()

    # --- polecenia ---

    def respond(self, text: str, source: str = "text", barge_in: Any = None, speak_async: bool = True) -> str | None:
        """Obsługuje polecenie (głosowe lub wpisane) i – jeśli trzeba – wypowiada odpowiedź."""
        if barge_in is not None and barge_in.kind == "reply":
            self.conversation.mark_interrupted(barge_in.spoken)
        interruption = Interruption(barge_in.spoken) if barge_in is not None else None
        started = time.monotonic()
        with self.tracker.thinking():
            reply = self.assistant.handle(text, source, interruption)
        log.info("Odpowiedź po %.0f ms: %s", (time.monotonic() - started) * 1000, reply)
        if reply and self.voice and (source == "voice" or self.settings.get().voice.speak_text_replies):
            if speak_async:
                self.voice.speaker.say_async(reply, "reply")
            else:
                self.voice.speaker.say(reply, "reply")
        return reply

    def confirm_command(self, command_id: str, accept: bool) -> str | None:
        """Przycisk w czacie przy poleceniu konsoli; None = polecenie wygasło albo zostało zastąpione."""
        reply = self.assistant.resolve_command(command_id, accept)
        if reply and self.voice and self.settings.get().voice.speak_text_replies:
            self.voice.speaker.say_async(reply, "reply")
        return reply

    def _respond_voice(self, text: str, barge_in: Any) -> None:
        # w wątku głosowym mówimy synchronicznie – pętla wie, kiedy odpowiedź się skończyła
        self.respond(text, "voice", barge_in, speak_async=False)

    def announce(self, text: str) -> None:
        """Komunikat systemowy (np. wiadomość z Discorda) – czytany na głos, jeśli jest dźwięk."""
        if self.voice:
            self.voice.say(text, "notice")

    def alert(self, text: str) -> None:
        """Przypomnienie: sygnał dźwiękowy, potem komunikat głosem."""
        if self.voice:
            from jarvis.audio.chime import REMINDER

            self.voice.player.play_effect(REMINDER)
            self.voice.say(text, "notice")

    # --- stan ---

    def status(self) -> dict[str, Any]:
        voice = (
            self.voice.status()
            if self.voice
            else {"available": False, "listening": False, "muted": False, "error": "Dźwięk wyłączony (--no-voice)."}
        )
        return {
            "version": __version__,
            "state": self.tracker.state,
            "voice": voice,
            "llm_configured": self.llm.configured,
            "discord_configured": self.discord.configured,
            "messenger": self.messenger.status(),
            "domownik": self.domownik_server.status(),
        }

    def publish_status(self) -> None:
        self.bus.publish("status", **self.status())
