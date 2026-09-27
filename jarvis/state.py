"""Jeden stan asystenta dla UI, wyliczany z kilku niezależnych źródeł.

Nasłuch (voice loop), transkrypcja, myślenie (LLM) i mówienie (TTS) dzieją się w różnych
wątkach; tutaj składamy je w jeden stan według priorytetu i publikujemy tylko zmiany.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from jarvis.events import EventBus

LISTENER_STATES = ("idle", "listening", "follow_up", "muted", "offline")


class StatusTracker:
    def __init__(self, bus: EventBus):
        self._bus = bus
        self._lock = threading.Lock()
        self._listener = "offline"
        self._transcribing = False
        self._thinking = 0
        self._speaking = False
        self._state = "offline"

    @property
    def state(self) -> str:
        return self._state

    def set_listener(self, state: str) -> None:
        assert state in LISTENER_STATES, state
        with self._lock:
            self._listener = state
        self._publish()

    def set_transcribing(self, value: bool) -> None:
        with self._lock:
            self._transcribing = value
        self._publish()

    def set_speaking(self, value: bool) -> None:
        with self._lock:
            self._speaking = value
        self._publish()

    @contextmanager
    def thinking(self) -> Iterator[None]:
        with self._lock:
            self._thinking += 1
        self._publish()
        try:
            yield
        finally:
            with self._lock:
                self._thinking -= 1
            self._publish()

    def _compute(self) -> str:
        if self._speaking:
            return "speaking"
        if self._thinking:
            return "thinking"
        if self._transcribing:
            return "transcribing"
        return self._listener

    def _publish(self) -> None:
        with self._lock:
            state = self._compute()
            if state == self._state:
                return
            self._state = state
        self._bus.publish("state", state=state)
