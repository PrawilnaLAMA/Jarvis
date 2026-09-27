import pytest

from jarvis.events import EventBus


class Recorder:
    """Zbiera zdarzenia z szyny – do asercji w testach."""

    def __init__(self, bus: EventBus):
        self.events = []
        bus.subscribe(self.events.append)

    def topics(self) -> list[str]:
        return [e.topic for e in self.events]

    def of(self, topic: str) -> list[dict]:
        return [e.data for e in self.events if e.topic == topic]


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def recorder(bus: EventBus) -> Recorder:
    return Recorder(bus)
