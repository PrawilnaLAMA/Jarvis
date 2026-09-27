from datetime import datetime

import pytest

from jarvis.services.calendar_store import CalendarStore
from jarvis.services.reminders import ReminderService
from jarvis.settings import SettingsStore


class Clock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def env(tmp_path, bus):
    calendar = CalendarStore(tmp_path / "events.json", bus)
    settings = SettingsStore(tmp_path / "settings.json")
    settings.update({"reminders": {"lead_minutes": 30, "all_day_hour": 8}})
    spoken: list[str] = []
    clock = Clock(datetime(2025, 11, 3, 9, 0))  # poniedziałek

    def make() -> ReminderService:
        return ReminderService(calendar, settings, bus, spoken.append, tmp_path / "state.json", clock)

    return calendar, spoken, clock, make


def test_reminds_once_within_lead_window(env):
    calendar, spoken, clock, make = env
    calendar.add({"desc": "Fryzjer", "date": "2025-11-03", "start": "10:00"})
    service = make()
    assert service.check() == []  # 9:00 – za wcześnie (wyprzedzenie 30 min)
    clock.now = datetime(2025, 11, 3, 9, 35)
    assert service.check() == ["Przypomnienie: Fryzjer dziś o 10:00."]
    assert service.check() == []
    assert spoken == ["Przypomnienie: Fryzjer dziś o 10:00."]


def test_state_survives_restart(env):
    calendar, spoken, clock, make = env
    calendar.add({"desc": "Fryzjer", "date": "2025-11-03", "start": "09:20"})
    make().check()
    assert make().check() == []
    assert len(spoken) == 1


def test_recurring_event_reminds_every_week(env):
    calendar, spoken, clock, make = env
    calendar.add({"desc": "Trening", "days": ["Monday"], "start": "09:10"})
    service = make()
    service.check()
    clock.now = datetime(2025, 11, 10, 9, 0)
    service.check()
    assert spoken == ["Przypomnienie: Trening dziś o 09:10."] * 2


def test_all_day_event_reminds_in_the_morning(env):
    calendar, spoken, clock, make = env
    calendar.add({"desc": "urodziny Asi", "date": "2025-11-03"})
    clock.now = datetime(2025, 11, 3, 7, 59)
    service = make()
    assert service.check() == []
    clock.now = datetime(2025, 11, 3, 8, 0)
    assert service.check() == ["Przypomnienie: dziś urodziny Asi."]


def test_lead_crossing_midnight_says_tomorrow(env):
    calendar, spoken, clock, make = env
    calendar.add({"desc": "Pociąg", "date": "2025-11-04", "start": "00:10"})
    clock.now = datetime(2025, 11, 3, 23, 50)
    assert make().check() == ["Przypomnienie: Pociąg jutro o 00:10."]


def test_past_events_are_not_reminded(env):
    calendar, spoken, clock, make = env
    calendar.add({"desc": "Stare", "date": "2025-11-03", "start": "08:00"})
    assert make().check() == []
