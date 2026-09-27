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
from jarvis.services.calendar_store import CalendarStore
from jarvis.services.discord_client import DiscordClient
from jarvis.services.discord_monitor import DiscordMonitor
from jarvis.services.reminders import ReminderService
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
        self.calendar = CalendarStore(data_dir / "events.json", self.bus)
        self.conversation = Conversation(
            data_dir / "conversation.json", lambda: self.settings.get().llm.history_messages
        )
        self.discord = DiscordClient(lambda: self.secrets.discord_token)
        self.llm = llm or LLMClient(
            lambda: providers_from(self.settings.get(), self.secrets),
            on_limit_wait=lambda s: self.bus.notice(f"Limit zapytań do modelu – czekam {s:.0f} s…", "warning"),
        )
        tool_context = ToolContext(self.settings, self.bus, self.calendar, self.discord, self.conversation)
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

        self.reminders = ReminderService(
            self.calendar, self.settings, self.bus, self.announce, data_dir / "reminders_state.json"
        )
        self.discord_monitor = DiscordMonitor(self.discord, self.settings, self.bus, self.announce)
        self.bus.subscribe(lambda _: self.publish_status(), {"voice.status", "settings.changed"})

    # --- cykl życia ---

    def start(self) -> None:
        if self.voice:
            self.voice.start(self.stop_event)
        for name, target in (("reminders", self.reminders.run), ("discord", self.discord_monitor.run)):
            threading.Thread(target=target, args=(self.stop_event,), name=name, daemon=True).start()
        if not self.llm.configured:
            self.bus.notice("Brak klucza GROQ_API_KEY – dodaj go w Ustawieniach, żeby Jarvis mógł odpowiadać.",
                            "warning")

    def shutdown(self) -> None:
        self.stop_event.set()
        if self.voice:
            self.voice.close()

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

    def _respond_voice(self, text: str, barge_in: Any) -> None:
        # w wątku głosowym mówimy synchronicznie – pętla wie, kiedy odpowiedź się skończyła
        self.respond(text, "voice", barge_in, speak_async=False)

    def announce(self, text: str) -> None:
        """Komunikat systemowy (przypomnienie, wiadomość z Discorda) – czytany na głos, jeśli jest dźwięk."""
        if self.voice:
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
        }

    def publish_status(self) -> None:
        self.bus.publish("status", **self.status())
