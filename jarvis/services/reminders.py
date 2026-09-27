"""Przypomnienia o wydarzeniach z kalendarza.

Stan „przypomniano” trzymamy per wystąpienie (id wydarzenia + data), dzięki czemu
wydarzenia cykliczne przypominają się w każdym tygodniu, a nie tylko raz.
"""

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from jarvis.events import EventBus
from jarvis.jsonfile import read_json, write_json
from jarvis.services.calendar_store import CalendarStore, Occurrence, describe_day
from jarvis.settings import SettingsStore

log = logging.getLogger(__name__)


class ReminderService:
    def __init__(
        self,
        calendar: CalendarStore,
        settings: SettingsStore,
        bus: EventBus,
        speak: Callable[[str], None],
        state_path: Path,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self._calendar = calendar
        self._settings = settings
        self._bus = bus
        self._speak = speak
        self._state_path = state_path
        self._clock = clock
        self._sent: set[str] = set(read_json(state_path, []))

    def _remind_at(self, occ: Occurrence, lead: timedelta, all_day_hour: int) -> tuple[datetime, datetime]:
        """Zwraca (od kiedy przypominać, do kiedy przypomnienie ma sens)."""
        if occ.start_dt:
            return occ.start_dt - lead, occ.start_dt
        start_of_day = datetime.combine(occ.day, datetime.min.time())
        return start_of_day.replace(hour=all_day_hour), start_of_day + timedelta(days=1)

    @staticmethod
    def message(occ: Occurrence, now: datetime) -> str:
        when = describe_day(occ.day, now.date())
        if occ.event.get("start"):
            return f"Przypomnienie: {occ.event['desc']} {when} o {occ.event['start']}."
        return f"Przypomnienie: {when} {occ.event['desc']}."

    def check(self) -> list[str]:
        """Jedno sprawdzenie; zwraca wypowiedziane przypomnienia."""
        now = self._clock()
        cfg = self._settings.get().reminders
        lead = timedelta(minutes=cfg.lead_minutes)
        horizon = (now + lead).date()
        messages = []
        for occ in self._calendar.occurrences(now.date(), horizon):
            if occ.key in self._sent:
                continue
            remind_from, until = self._remind_at(occ, lead, cfg.all_day_hour)
            if remind_from <= now < until:
                self._sent.add(occ.key)
                text = self.message(occ, now)
                messages.append(text)
                self._bus.publish("reminder", text=text, event_id=occ.event["id"])
                self._speak(text)
        if messages:
            self._prune(now)
            write_json(self._state_path, sorted(self._sent))
        return messages

    def _prune(self, now: datetime) -> None:
        cutoff = (now - timedelta(days=2)).date().isoformat()
        self._sent = {k for k in self._sent if k.rsplit("|", 1)[-1] >= cutoff}

    def run(self, stop: threading.Event, interval: float = 30.0) -> None:
        while not stop.is_set():
            try:
                self.check()
            except Exception:
                log.exception("Błąd sprawdzania przypomnień")
            stop.wait(interval)
