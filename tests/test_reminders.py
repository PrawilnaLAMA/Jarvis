"""Przypomnienia z kalendarza: okno odpalenia, jednokrotność (także po restarcie) i odbiór klikiem."""

from datetime import datetime

from jarvis.services.domownik_client import DomownikError
from jarvis.services.reminders import Reminders, reminder_text


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def agenda(*items, day="2025-11-03"):
    return {"days": [{"date": day, "items": list(items)}], "overdue": []}


def item(title="Dentysta", time="15:00", before=30, done=False, id_="d1"):
    return {"id": id_, "title": title, "time": time, "remind_before": before, "done": done}


def make(tmp_path, domownik, bus, now):
    alerts = []
    clock = Clock(now)
    reminders = Reminders(bus, domownik, tmp_path / "reminders.json", alerts.append, clock)
    return reminders, alerts, clock


def test_fires_once_in_window(tmp_path, domownik, bus, recorder):
    domownik.agenda_data = agenda(item(), item("Bez godziny", time="", id_="x"), item("Bez przyp.", before=None))
    reminders, alerts, clock = make(tmp_path, domownik, bus, datetime(2025, 11, 3, 14, 20))
    assert reminders.check() == 0  # za wcześnie (przypomnienie o 14:30)
    clock.now = datetime(2025, 11, 3, 14, 31)
    assert reminders.check() == 1
    assert alerts == ["Przypomnienie: Dentysta o 15:00, za 29 minut."]
    assert reminders.check() == 0  # drugi raz nie
    assert [r["title"] for r in reminders.pending()] == ["Dentysta"]
    assert recorder.of("reminders")[-1]["pending"][0]["time"] == "15:00"
    assert recorder.of("reminder")[0]["text"] == alerts[0]


def test_after_start_or_done_is_skipped(tmp_path, domownik, bus):
    domownik.agenda_data = agenda(item(), item("Zrobione", done=True, id_="z"))
    reminders, alerts, _ = make(tmp_path, domownik, bus, datetime(2025, 11, 3, 15, 1))
    assert reminders.check() == 0 and alerts == []


def test_on_time_has_grace(tmp_path, domownik, bus):
    domownik.agenda_data = agenda(item(before=0))
    reminders, alerts, _ = make(tmp_path, domownik, bus, datetime(2025, 11, 3, 15, 2))
    assert reminders.check() == 1 and alerts == ["Przypomnienie: Dentysta o 15:00."]


def test_restart_keeps_state_and_ack_clears(tmp_path, domownik, bus, recorder):
    domownik.agenda_data = agenda(item())
    first, _, _ = make(tmp_path, domownik, bus, datetime(2025, 11, 3, 14, 45))
    first.check()
    again, alerts, _ = make(tmp_path, domownik, bus, datetime(2025, 11, 3, 14, 46))
    assert again.check() == 0 and alerts == []  # po restarcie nie powtarza
    assert len(again.pending()) == 1  # a kula dalej czerwona
    again.ack()
    assert again.pending() == [] and recorder.of("reminders")[-1]["pending"] == []
    assert make(tmp_path, domownik, bus, datetime(2025, 11, 3, 14, 47))[0].pending() == []


def test_changed_time_rearms(tmp_path, domownik, bus):
    domownik.agenda_data = agenda(item())
    reminders, alerts, clock = make(tmp_path, domownik, bus, datetime(2025, 11, 3, 14, 40))
    reminders.check()
    domownik.agenda_data = agenda(item(time="15:05"))
    clock.now = datetime(2025, 11, 3, 14, 41)
    assert reminders.check() == 1 and len(alerts) == 2


def test_unreachable_domownik_is_quiet(tmp_path, domownik, bus):
    domownik.error = DomownikError("Domownik nie odpowiada")
    reminders, alerts, _ = make(tmp_path, domownik, bus, datetime(2025, 11, 3, 14, 40))
    assert reminders.check() == 0 and alerts == []


def test_reminder_text_for_tomorrow_and_hours():
    now = datetime(2025, 11, 3, 20, 0)
    assert reminder_text("Pociąg", datetime(2025, 11, 4, 7, 30), now) == \
        "Przypomnienie: Pociąg jutro o 7:30, za 11 godzin i 30 minut."
