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


class FakeDomownik:
    """Atrapa klienta Domownika: dane w pamięci, format odpowiedzi jak w prawdziwym API."""

    url = "http://domownik.test"

    def __init__(self):
        self.agenda_data = {"days": [], "overdue": [], "grafik": {}}
        self.chores_data: list[dict] = []
        self.items: list[dict] = []
        self.added: list[dict] = []
        self.done_calls: list[tuple] = []
        self.deleted: list[str] = []
        self.error = None

    def _check(self):
        if self.error:
            raise self.error

    def ping(self):
        self._check()

    def agenda(self, start, days):
        self._check()
        self.agenda_args = (start, days)
        return self.agenda_data

    def chores(self):
        self._check()
        return self.chores_data

    def add_chore(self, payload):
        self._check()
        self.added.append(payload)
        return {**payload, "id": "new"}

    def delete_chore(self, chore_id):
        self._check()
        self.deleted.append(chore_id)

    def set_done(self, chore_id, day, done=True):
        self._check()
        self.done_calls.append((chore_id, day.isoformat(), done))

    def shopping(self):
        self._check()
        return [dict(i) for i in self.items]

    def add_item(self, title, qty=""):
        self._check()
        item = {"id": f"i{len(self.items)}", "title": title, "qty": qty, "done": False}
        self.items.append(item)
        return item

    def update_item(self, item_id, payload):
        for i in self.items:
            if i["id"] == item_id:
                i.update(payload)
                return i

    def delete_item(self, item_id):
        self.items = [i for i in self.items if i["id"] != item_id]

    def clear_bought(self):
        before = len(self.items)
        self.items = [i for i in self.items if not i["done"]]
        return before - len(self.items)


@pytest.fixture
def domownik() -> FakeDomownik:
    return FakeDomownik()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def recorder(bus: EventBus) -> Recorder:
    return Recorder(bus)
