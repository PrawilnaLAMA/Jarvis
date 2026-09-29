"""Minutniki co do sekundy – odliczają w tle, a interfejs pokazuje je w kuli Jarvisa.

Każda zmiana (nowy minutnik, pauza, dodany czas, koniec) publikuje całą listę jako `timers`, więc interfejs
niczego nie składa sam. Koniec czasu to dodatkowo `timer.ring` i komunikat czytany na głos. Czas liczymy
zegarem monotonicznym, a do interfejsu idzie „ile zostało” – strona odlicza dalej sama, bez zegara systemu.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from jarvis.events import EventBus

MAX_SECONDS = 24 * 3600

# (sekundy, wywołanie) → obiekt z cancel(); w testach atrapa zamiast wątku
Schedule = Callable[[float, Callable[[], None]], Any]


def _schedule(seconds: float, fn: Callable[[], None]) -> threading.Timer:
    handle = threading.Timer(seconds, fn)
    handle.daemon = True
    handle.start()
    return handle


@dataclass
class Timer:
    id: int
    label: str
    total: float  # nastawiony czas razem z dodanym, s
    left: float  # ile zostało w chwili pauzy (albo ostatniego startu)
    due: float | None = None  # koniec na zegarze monotonicznym; None = wstrzymany
    handle: Any = None
    token: object = field(default_factory=object)  # który z zaplanowanych końców jest aktualny

    @property
    def paused(self) -> bool:
        return self.due is None

    def remaining(self, now: float) -> float:
        return self.left if self.due is None else max(0.0, self.due - now)


class Timers:
    def __init__(
        self,
        bus: EventBus,
        announce: Callable[[str], None] = lambda text: None,
        clock: Callable[[], float] = time.monotonic,
        schedule: Schedule = _schedule,
    ):
        self._bus = bus
        self._announce = announce
        self._clock = clock
        self._schedule = schedule
        self._lock = threading.RLock()
        self._timers: dict[int, Timer] = {}
        self._next_id = 1

    # --- odczyt ---

    def all(self) -> list[Timer]:
        """Najpierw odliczające (najbliższy koniec pierwszy), potem wstrzymane."""
        now = self._clock()
        with self._lock:
            return sorted(self._timers.values(), key=lambda t: (t.paused, t.remaining(now), t.id))

    def remaining(self, timer: Timer) -> float:
        return timer.remaining(self._clock())

    def snapshot(self) -> list[dict[str, Any]]:
        now = self._clock()
        return [
            {"id": t.id, "label": t.label, "total": round(t.total, 3), "remaining": round(t.remaining(now), 3),
             "paused": t.paused}
            for t in self.all()
        ]

    # --- zmiany ---

    def start(self, seconds: float, label: str = "") -> Timer:
        seconds = float(seconds)
        if not 1 <= seconds <= MAX_SECONDS:
            raise ValueError("Minutnik: od 1 sekundy do 24 godzin.")
        with self._lock:
            timer = Timer(self._next_id, label.strip(), seconds, seconds)
            self._next_id += 1
            self._timers[timer.id] = timer
            self._run(timer)
        self._publish()
        return timer

    def pause(self, timer_id: int) -> bool:
        with self._lock:
            timer = self._timers.get(timer_id)
            if timer is None:
                return False
            if not timer.paused:
                timer.left = timer.remaining(self._clock())
                timer.due = None
                self._stop(timer)
        self._publish()
        return True

    def resume(self, timer_id: int) -> bool:
        with self._lock:
            timer = self._timers.get(timer_id)
            if timer is None:
                return False
            if timer.paused:
                self._run(timer)
        self._publish()
        return True

    def add(self, timer_id: int, seconds: float) -> bool:
        """Dodaje (albo odejmuje, gdy ujemne) czas; zostaje co najmniej sekunda."""
        with self._lock:
            timer = self._timers.get(timer_id)
            if timer is None:
                return False
            left = timer.remaining(self._clock())
            new_left = min(MAX_SECONDS, max(1.0, left + seconds))
            timer.total = max(new_left, timer.total + (new_left - left))
            timer.left = new_left
            if not timer.paused:
                self._stop(timer)
                self._run(timer)
        self._publish()
        return True

    def cancel(self, timer_id: int) -> bool:
        with self._lock:
            timer = self._timers.pop(timer_id, None)
            if timer is None:
                return False
            self._stop(timer)
        self._publish()
        return True

    # --- wnętrze ---

    def _run(self, timer: Timer) -> None:
        timer.due = self._clock() + timer.left
        token = timer.token = object()
        timer.handle = self._schedule(timer.left, lambda: self._ring(timer.id, token))

    @staticmethod
    def _stop(timer: Timer) -> None:
        if timer.handle is not None:
            timer.handle.cancel()
            timer.handle = None
        timer.token = object()  # spóźniony koniec (wątek już wystartował) niczego nie zadzwoni

    def _ring(self, timer_id: int, token: object) -> None:
        with self._lock:
            timer = self._timers.get(timer_id)
            if timer is None or timer.token is not token:
                return
            del self._timers[timer_id]
        text = f"Minął czas: {timer.label}." if timer.label else "Minął czas na minutniku."
        self._bus.publish("timer.ring", id=timer.id, label=timer.label, total=timer.total)
        self._publish()
        self._bus.notice(text, "info")
        self._announce(text)

    def _publish(self) -> None:
        self._bus.publish("timers", timers=self.snapshot())
