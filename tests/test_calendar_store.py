import json
from datetime import date

import pytest

from jarvis.services.calendar_store import (
    CalendarError,
    CalendarStore,
    describe_day,
    describe_occurrence,
    normalize_event,
)


@pytest.fixture
def store(tmp_path, bus):
    return CalendarStore(tmp_path / "events.json", bus)


def test_normalize_accepts_polish_days_and_short_times():
    e = normalize_event({"desc": "Siłownia", "days": "środa, poniedziałek", "start": "7:05"})
    assert e["days"] == ["Monday", "Wednesday"]
    assert e["start"] == "07:05"
    assert e["date"] is None


@pytest.mark.parametrize(
    "data, fragment",
    [
        ({"desc": "x"}, "datę albo dni"),
        ({"desc": "x", "date": "2025-13-01"}, "Nieprawidłowa data"),
        ({"desc": "x", "date": "2025-01-01", "start": "25:00"}, "godzina"),
        ({"desc": "x", "date": "2025-01-01", "start": "10:00", "end": "09:00"}, "późniejsza"),
        ({"desc": "x", "days": ["funday"]}, "Nieznany dzień"),
        ({"date": "2025-01-01"}, "opis"),
    ],
)
def test_normalize_rejects_invalid(data, fragment):
    with pytest.raises(CalendarError, match=fragment):
        normalize_event(data)


def test_type_used_as_description_for_legacy_events():
    assert normalize_event({"type": "praca", "desc": "", "days": ["Monday"]})["desc"] == "praca"


def test_crud_persists_and_publishes(store, tmp_path, recorder):
    e = store.add({"desc": "Fryzjer", "date": "2025-11-04", "start": "15:00", "id": "ignored"})
    assert e["id"] != "ignored"
    assert store.update(e["id"], {"start": "16:00"})["start"] == "16:00"
    assert store.update("missing", {"start": "16:00"}) is None
    saved = json.loads((tmp_path / "events.json").read_text(encoding="utf-8"))
    assert saved[0]["start"] == "16:00"
    assert store.remove(e["id"]) is True
    assert store.remove(e["id"]) is False
    assert recorder.topics().count("calendar.changed") == 3


def test_load_skips_broken_entries(tmp_path):
    path = tmp_path / "events.json"
    path.write_text(json.dumps([{"desc": "ok", "date": "2025-01-01"}, {"desc": "zła"}, "śmieć"]), encoding="utf-8")
    assert [e["desc"] for e in CalendarStore(path).all_events()] == ["ok"]


def test_occurrences_expand_recurring_and_sort(store):
    store.add({"desc": "Praca", "days": ["Monday", "Wednesday"], "start": "09:00"})
    store.add({"desc": "Lekarz", "date": "2025-11-03", "start": "08:00"})
    store.add({"desc": "Urodziny", "date": "2025-11-05"})
    occ = store.occurrences(date(2025, 11, 3), date(2025, 11, 9))  # pon–nd
    assert [(o.day.day, o.event["desc"]) for o in occ] == [(3, "Lekarz"), (3, "Praca"), (5, "Urodziny"), (5, "Praca")]
    assert occ[0].start_dt.hour == 8
    assert occ[2].start_dt is None


def test_describe_day():
    today = date(2025, 11, 3)  # poniedziałek
    assert describe_day(today, today) == "dziś"
    assert describe_day(date(2025, 11, 4), today) == "jutro"
    assert describe_day(date(2025, 11, 5), today) == "pojutrze"
    assert describe_day(date(2025, 11, 6), today) == "w czwartek"
    assert describe_day(date(2025, 11, 11), date(2025, 11, 6)) == "we wtorek"
    assert describe_day(date(2025, 11, 11), today) == "11 listopada"
    assert describe_day(date(2025, 12, 24), today) == "24 grudnia"


def test_describe_occurrence(store):
    store.add({"desc": "Spotkanie", "date": "2025-11-04", "start": "10:00", "end": "11:30"})
    occ = store.occurrences(date(2025, 11, 4), date(2025, 11, 4))[0]
    assert describe_occurrence(occ, date(2025, 11, 3)) == "Spotkanie jutro o 10:00 do 11:30"
