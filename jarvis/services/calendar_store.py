"""Kalendarz zapisany w pliku JSON.

Wydarzenie:
    {"id": "uuid", "type": "spotkanie", "desc": "Fryzjer",
     "date": "2025-11-04" | null,           # wydarzenie jednorazowe
     "days": ["Monday", "Friday"],          # albo cykliczne w dni tygodnia
     "start": "15:00" | null, "end": "16:00" | null}
"""

import re
import threading
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from jarvis.events import EventBus
from jarvis.jsonfile import read_json, write_json

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAYS_PL = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
_WEEKDAY_ALIASES = {
    **{d.lower(): d for d in WEEKDAYS},
    **{pl: en for pl, en in zip(WEEKDAYS_PL, WEEKDAYS, strict=True)},
    "sroda": "Wednesday",
    "piatek": "Friday",
    "poniedzialek": "Monday",
}
MONTHS_GENITIVE_PL = [
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
]


class CalendarError(ValueError):
    """Błąd walidacji wydarzenia – komunikat po polsku, do pokazania użytkownikowi."""


def _parse_time(value: Any, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    m = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", str(value))
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        raise CalendarError(f"Nieprawidłowa godzina ({field_name}): {value}. Użyj formatu GG:MM.")
    return f"{int(m[1]):02d}:{m[2]}"


def _parse_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        raise CalendarError(f"Nieprawidłowa data: {value}. Użyj formatu RRRR-MM-DD.") from None


def _parse_days(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = value.split(",")
    days = []
    for item in value:
        key = str(item).strip().lower()
        if not key:
            continue
        if key not in _WEEKDAY_ALIASES:
            raise CalendarError(f"Nieznany dzień tygodnia: {item}.")
        day = _WEEKDAY_ALIASES[key]
        if day not in days:
            days.append(day)
    return sorted(days, key=WEEKDAYS.index)


def normalize_event(data: dict[str, Any], event_id: str | None = None) -> dict[str, Any]:
    """Waliduje i porządkuje dane wydarzenia. Rzuca CalendarError."""
    event_type = str(data.get("type") or "").strip()
    desc = str(data.get("desc") or "").strip() or event_type
    if not desc:
        raise CalendarError("Wydarzenie musi mieć opis.")
    event_date = _parse_date(data.get("date"))
    days = _parse_days(data.get("days"))
    if not event_date and not days:
        raise CalendarError("Podaj datę albo dni tygodnia, w które wydarzenie się powtarza.")
    if event_date and days:
        days = []  # konkretna data ma pierwszeństwo
    start = _parse_time(data.get("start"), "początek")
    end = _parse_time(data.get("end"), "koniec")
    if end and not start:
        raise CalendarError("Podaj godzinę rozpoczęcia, jeśli podajesz godzinę zakończenia.")
    if start and end and end <= start:
        raise CalendarError("Godzina zakończenia musi być późniejsza niż rozpoczęcia.")
    return {
        "id": event_id or str(data.get("id") or uuid.uuid4()),
        "type": event_type,
        "desc": desc,
        "date": event_date,
        "days": days,
        "start": start,
        "end": end,
    }


@dataclass(frozen=True)
class Occurrence:
    event: dict[str, Any]
    day: date

    @property
    def start_dt(self) -> datetime | None:
        start = self.event.get("start")
        return datetime.combine(self.day, time.fromisoformat(start)) if start else None

    @property
    def key(self) -> str:
        return f"{self.event['id']}|{self.day.isoformat()}"

    def to_dict(self) -> dict[str, Any]:
        return {**self.event, "occurrence_date": self.day.isoformat()}


class CalendarStore:
    def __init__(self, path: Path, bus: EventBus | None = None):
        self._path = path
        self._bus = bus
        self._lock = threading.RLock()
        self._events: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        raw = read_json(self._path, [])
        events = []
        for item in raw if isinstance(raw, list) else []:
            try:
                events.append(normalize_event(item))
            except (CalendarError, AttributeError):
                continue  # pomijamy uszkodzone wpisy zamiast wywalać całą aplikację
        self._events = events

    def _save(self) -> None:
        write_json(self._path, self._events)
        if self._bus:
            self._bus.publish("calendar.changed")

    def all_events(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(e) for e in self._events]

    def get(self, event_id: str) -> dict[str, Any] | None:
        with self._lock:
            return next((dict(e) for e in self._events if e["id"] == event_id), None)

    def add(self, data: dict[str, Any]) -> dict[str, Any]:
        event = normalize_event({k: v for k, v in data.items() if k != "id"})
        with self._lock:
            self._events.append(event)
            self._save()
        return dict(event)

    def update(self, event_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            for i, current in enumerate(self._events):
                if current["id"] == event_id:
                    event = normalize_event({**current, **data}, event_id=event_id)
                    self._events[i] = event
                    self._save()
                    return dict(event)
        return None

    def remove(self, event_id: str) -> bool:
        with self._lock:
            before = len(self._events)
            self._events = [e for e in self._events if e["id"] != event_id]
            if len(self._events) == before:
                return False
            self._save()
            return True

    def occurrences(self, start: date, end: date) -> list[Occurrence]:
        """Wszystkie wystąpienia wydarzeń w dniach od `start` do `end` włącznie."""
        with self._lock:
            events = [dict(e) for e in self._events]
        result = []
        day = start
        while day <= end:
            weekday = WEEKDAYS[day.weekday()]
            for e in events:
                if e["date"] == day.isoformat() or weekday in e["days"]:
                    result.append(Occurrence(e, day))
            day += timedelta(days=1)
        return sorted(result, key=lambda o: (o.day, o.event.get("start") or "", o.event["desc"]))


def describe_day(day: date, today: date) -> str:
    """„dziś”, „jutro”, „w poniedziałek” albo „5 listopada”."""
    delta = (day - today).days
    if delta == 0:
        return "dziś"
    if delta == 1:
        return "jutro"
    if delta == 2:
        return "pojutrze"
    if 2 < delta < 7:
        return _WEEKDAYS_PL_ON[day.weekday()]
    return f"{day.day} {MONTHS_GENITIVE_PL[day.month - 1]}"


_WEEKDAYS_PL_ON = ["w poniedziałek", "we wtorek", "w środę", "w czwartek", "w piątek", "w sobotę", "w niedzielę"]


def describe_occurrence(occ: Occurrence, today: date) -> str:
    text = f"{occ.event['desc']} {describe_day(occ.day, today)}"
    if occ.event.get("start"):
        text += f" o {occ.event['start']}"
        if occ.event.get("end"):
            text += f" do {occ.event['end']}"
    return text
