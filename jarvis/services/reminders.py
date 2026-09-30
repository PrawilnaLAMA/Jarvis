"""Przypomnienia o wpisach z kalendarza Domownika (godzina + „ile minut wcześniej”).

Co `INTERVAL` sekund czytamy agendę na dziś i jutro (przez HTTP, jak narzędzia – Domownik może żyć na innym
komputerze). Wpis z godziną i `remind_before` odpala raz: od chwili „godzina − remind_before” do godziny
wydarzenia (przy „o czasie” jeszcze `ON_TIME_GRACE` po). Odpalenie to dźwięk i komunikat głosowy
(`alert`), zdarzenie `reminder` oraz lista oczekujących `reminders` – kula świeci na czerwono, dopóki
użytkownik jej nie kliknie (`ack`). Odpalone i oczekujące leżą w pliku, więc restart ani nie powtarza
przypomnienia, ani nie gasi czerwonej kuli.
"""

import logging
import threading
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from jarvis.events import EventBus
from jarvis.jsonfile import read_json, write_json
from jarvis.polish import duration_pl
from jarvis.services.domownik_client import DomownikClient, DomownikError

log = logging.getLogger(__name__)

INTERVAL = 30.0  # s
ON_TIME_GRACE = timedelta(minutes=5)  # „o czasie” – jeszcze tyle po godzinie wydarzenia
KEEP = timedelta(days=2)  # tyle pamiętamy odpalone przypomnienia


class Reminders:
    def __init__(
        self,
        bus: EventBus,
        client: DomownikClient,
        path: Path,
        alert: Callable[[str], None] = lambda text: None,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self._bus = bus
        self._client = client
        self._path = path
        self._alert = alert
        self._clock = clock
        self._lock = threading.Lock()
        data = read_json(path, {})
        self._fired: dict[str, str] = dict(data.get("fired") or {})
        self._pending: list[dict[str, Any]] = list(data.get("pending") or [])

    # --- odczyt ---

    def pending(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._pending)

    # --- pętla ---

    def run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            self.check()
            stop.wait(INTERVAL)

    def check(self) -> int:
        """Odpala przypomnienia, których pora właśnie trwa; zwraca, ile odpaliło."""
        now = self._clock()
        try:
            agenda = self._client.agenda(now.date(), 2)
        except DomownikError as e:
            log.debug("Przypomnienia: %s", e)
            return 0
        fired = 0
        for day in agenda.get("days") or []:
            for item in day.get("items") or []:
                start = _start(day.get("date"), item)
                if start is None or item.get("done"):
                    continue
                before = int(item["remind_before"])
                due = start - timedelta(minutes=before)
                end = start if before else start + ON_TIME_GRACE
                key = f"{item.get('id')}|{day['date']}|{item['time']}|{before}"  # zmiana godziny = nowe przypomnienie
                if due <= now < end and key not in self._fired:
                    self._fire(key, item, start, now)
                    fired += 1
        return fired

    # --- zmiany ---

    def ack(self) -> None:
        """Użytkownik zobaczył przypomnienia (klik w kulę) – kula wraca do zwykłego koloru."""
        with self._lock:
            if not self._pending:
                return
            self._pending = []
            self._save()
        self._publish()

    # --- wnętrze ---

    def _fire(self, key: str, item: dict[str, Any], start: datetime, now: datetime) -> None:
        text = reminder_text(item["title"], start, now)
        entry = {"key": key, "id": item.get("id"), "title": item["title"], "date": start.date().isoformat(),
                 "time": item["time"], "text": text, "at": now.isoformat(timespec="seconds")}
        with self._lock:
            self._fired[key] = entry["at"]
            limit = now - KEEP
            self._fired = {k: at for k, at in self._fired.items() if datetime.fromisoformat(at) >= limit}
            self._pending.append(entry)
            self._save()
        log.info("Przypomnienie: %s", text)
        self._bus.publish("reminder", **entry)
        self._publish()
        self._bus.notice(text, "info")
        self._alert(text)

    def _save(self) -> None:
        write_json(self._path, {"fired": self._fired, "pending": self._pending})

    def _publish(self) -> None:
        self._bus.publish("reminders", pending=self.pending())


def _start(day: Any, item: dict[str, Any]) -> datetime | None:
    """Początek wpisu z przypomnieniem albo None (bez godziny/przypomnienia, złe dane)."""
    if not item.get("time") or item.get("remind_before") is None or not item.get("title"):
        return None
    try:
        hh, mm = (int(p) for p in str(item["time"]).split(":"))
        return datetime.combine(date.fromisoformat(str(day)), time(hh, mm))
    except (TypeError, ValueError):
        return None


def reminder_text(title: str, start: datetime, now: datetime) -> str:
    """„Przypomnienie: Dentysta o 15:00, za 30 minut.” – przy „o czasie” bez „za…”."""
    when = "jutro o" if start.date() > now.date() else "o"
    text = f"Przypomnienie: {title} {when} {start.hour}:{start:%M}"
    minutes = round((start - now).total_seconds() / 60)
    if minutes > 0:
        text += f", za {duration_pl(minutes * 60)}"
    return text + "."
