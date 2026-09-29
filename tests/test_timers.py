"""Minutniki co do sekundy – na atrapie zegara i planowania, bez wątków i czekania."""

import pytest

from jarvis.conversation import Conversation
from jarvis.services.timers import Timers
from jarvis.settings import SettingsStore
from jarvis.tools import ToolContext, ToolError, computer


class FakeClock:
    """Zegar monotoniczny i planowanie końców minutników – czas płynie tylko w pass_time."""

    def __init__(self):
        self.now = 1000.0
        self.planned = []

    def __call__(self):
        return self.now

    def schedule(self, seconds, fn):
        plan = Plan(self.now + seconds, fn)
        self.planned.append(plan)
        return plan

    def pass_time(self, seconds):
        """Przesuwa czas i odpala to, co w nim wypada (jak prawdziwe wątki)."""
        self.now += seconds
        for plan in list(self.planned):
            if not plan.cancelled and not plan.fired and plan.at <= self.now:
                plan.fired = True
                plan.fn()


class Plan:
    def __init__(self, at, fn):
        self.at, self.fn, self.cancelled, self.fired = at, fn, False, False

    def cancel(self):
        self.cancelled = True


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def timers(bus, clock, spoken):
    return Timers(bus, spoken.append, clock=clock, schedule=clock.schedule)


def test_counts_down_to_the_second_and_rings(timers, clock, recorder, spoken):
    timer = timers.start(95, "makaron")
    assert recorder.of("timers")[-1]["timers"] == [
        {"id": 1, "label": "makaron", "total": 95.0, "remaining": 95.0, "paused": False}]
    clock.pass_time(94)
    assert timers.snapshot()[0]["remaining"] == 1.0
    clock.pass_time(1)
    assert recorder.of("timer.ring") == [{"id": timer.id, "label": "makaron", "total": 95.0}]
    assert timers.snapshot() == [] and recorder.of("timers")[-1]["timers"] == []
    assert spoken == ["Minął czas: makaron."] and recorder.of("notice")[-1]["text"] == "Minął czas: makaron."


def test_pause_resume_and_add_keep_exact_time(timers, clock, recorder, spoken):
    timer = timers.start(60)
    clock.pass_time(20)
    timers.pause(timer.id)
    clock.pass_time(500)  # wstrzymany nie odlicza i nie dzwoni
    assert timers.snapshot()[0] == {"id": 1, "label": "", "total": 60.0, "remaining": 40.0, "paused": True}
    timers.add(timer.id, 30)
    assert timers.snapshot()[0]["remaining"] == 70.0 and timers.snapshot()[0]["total"] == 90.0
    timers.resume(timer.id)
    clock.pass_time(69)
    assert not recorder.of("timer.ring")
    timers.add(timer.id, -3600)  # odejmowanie zostawia co najmniej sekundę
    assert timers.snapshot()[0]["remaining"] == 1.0
    clock.pass_time(1)
    assert len(recorder.of("timer.ring")) == 1 and spoken == ["Minął czas na minutniku."]


def test_cancelled_or_rescheduled_timer_never_rings_twice(timers, clock, recorder):
    first = timers.start(10)
    second = timers.start(5, "herbata")
    assert [t["id"] for t in timers.snapshot()] == [second.id, first.id]  # najbliższy koniec pierwszy
    timers.add(first.id, 5)  # stary koniec za 10 s jest już nieaktualny
    timers.cancel(second.id)
    clock.pass_time(10)
    assert not recorder.of("timer.ring")
    clock.pass_time(5)
    assert [e["id"] for e in recorder.of("timer.ring")] == [first.id]
    assert not timers.cancel(first.id) and not timers.pause(99)
    with pytest.raises(ValueError):
        timers.start(0)


@pytest.fixture
def ctx(tmp_path, bus, domownik, messenger, inbox, timers):
    return ToolContext(
        settings=SettingsStore(tmp_path / "s.json"), bus=bus, domownik=domownik, discord=None, messenger=messenger,
        inbox=inbox, conversation=Conversation(tmp_path / "c.json", lambda: 12), timers=timers,
    )


def test_tool_sets_timer_to_the_second(ctx, timers):
    assert computer.timer(ctx, {"action": "set", "minutes": 2, "seconds": 30, "label": "jajka"}) == (
        "Minutnik na 2 minuty i 30 sekund: jajka.")
    assert computer.timer(ctx, {"action": "set", "hours": 1, "minutes": 5, "seconds": 3}) == (
        "Minutnik na 1 godzinę, 5 minut i 3 sekundy.")
    assert computer.timer(ctx, {"minutes": 0.5, "label": "minutnik"}) == "Minutnik na 30 sekund."  # to nie nazwa
    assert [t["total"] for t in timers.snapshot()] == [30.0, 150.0, 3903.0]
    with pytest.raises(ToolError, match="Na ile"):
        computer.timer(ctx, {"action": "set"})
    with pytest.raises(ToolError, match="24 godziny"):
        computer.timer(ctx, {"action": "set", "hours": 30})


def test_tool_finds_timer_by_label_and_speaks_what_is_left(ctx, timers, clock):
    computer.timer(ctx, {"action": "set", "minutes": 10, "label": "makaron"})
    computer.timer(ctx, {"action": "set", "minutes": 3, "label": "herbata"})
    clock.pass_time(59)
    assert computer.timer(ctx, {"action": "list"}) == (
        "Herbata – do końca 2 minuty i 1 sekunda; makaron – do końca 9 minut i 1 sekunda.")
    assert computer.timer(ctx, {"action": "add", "minutes": 1, "label": "makaronu"}) == (
        "Dodałem 1 minutę – do końca 10 minut i 1 sekunda.")
    assert computer.timer(ctx, {"action": "pause", "label": "herbatę"}) == "Wstrzymałem minutnik."
    assert "(wstrzymany)" in computer.timer(ctx, {"action": "list", "label": "herbata"})
    assert computer.timer(ctx, {"action": "resume"}).startswith("Wznawiam")
    with pytest.raises(ToolError, match="Nie ma takiego"):
        computer.timer(ctx, {"action": "cancel", "label": "pranie"})
    # „anuluj minutnik” przy dwóch – pytanie zamiast kasowania obu; „wszystkie” – oba
    with pytest.raises(ToolError, match="Który minutnik: herbata czy makaron"):
        computer.timer(ctx, {"action": "cancel", "label": "minutnik"})
    assert computer.timer(ctx, {"action": "cancel", "label": "wszystkie minutniki"}) == "Anulowałem minutniki: 2."
    assert computer.timer(ctx, {"action": "list"}) == "Nie ma nastawionych minutników."
    with pytest.raises(ToolError, match="Nie ma nastawionych"):
        computer.timer(ctx, {"action": "pause"})
