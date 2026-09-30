import json
from datetime import date, datetime

import pytest
import requests

from jarvis.services.domownik_client import DomownikClient, DomownikError
from jarvis.settings import SettingsStore
from jarvis.tools import ToolContext
from jarvis.tools.base import ToolError
from jarvis.tools.domownik import (
    _best_matches,
    chore_add,
    chore_done,
    house_agenda,
    open_domownik,
    shopping_list,
    shopping_update,
)

NOW = datetime(2025, 11, 3, 12, 0)  # poniedziałek


class FakeResponse:
    def __init__(self, status: int, data=None, raw: bytes | None = None):
        self.status_code = status
        self.content = raw if raw is not None else (json.dumps(data).encode() if data is not None else b"")

    def json(self):
        return json.loads(self.content)


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, timeout=None, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_client_builds_urls_and_maps_errors():
    session = FakeSession(
        FakeResponse(200, {"chores": [{"id": "a"}]}),
        FakeResponse(200, {"usuniete": 2}),
        FakeResponse(400, {"error": "Podaj nazwę obowiązku."}),
        FakeResponse(500, raw=b"<html>boom</html>"),
        requests.ConnectionError("refused"),
    )
    client = DomownikClient(lambda: "http://pi.local:8080/", session=session)
    assert client.chores() == [{"id": "a"}]
    assert session.calls[0][:2] == ("GET", "http://pi.local:8080/api/obowiazki")
    assert client.clear_bought() == 2
    with pytest.raises(DomownikError, match="Podaj nazwę"):
        client.add_chore({})
    with pytest.raises(DomownikError, match="błąd 500"):
        client.ping()
    with pytest.raises(DomownikError, match="nie odpowiada"):
        client.set_done("a", date(2025, 11, 3))
    assert session.calls[-1][2]["json"] == {"id": "a", "date": "2025-11-03", "done": True}


def test_agenda_days_are_clamped():
    session = FakeSession(FakeResponse(200, {"days": []}))
    DomownikClient(lambda: "http://x", session=session).agenda(date(2025, 11, 3), 100)
    assert session.calls[0][2]["params"] == {"od": "2025-11-03", "dni": 31}


@pytest.fixture
def ctx(tmp_path, bus, domownik, messenger, inbox):
    return ToolContext(settings=SettingsStore(tmp_path / "s.json"), bus=bus, domownik=domownik, discord=None,
                       messenger=messenger, inbox=inbox, conversation=None, clock=lambda: NOW)


def test_agenda_includes_schedule_and_overdue(ctx):
    ctx.domownik.agenda_data = {
        "days": [{"date": "2025-11-03", "weekday": "poniedziałek", "items": [
            {"title": "Pranie", "assignees": ["leon", "natalia"], "kto": "natalia", "kto_label": "Natalia",
             "na_zmiane": True},
            {"title": "Śmieci", "assignees": [], "done": True},
        ]}],
        "overdue": [{"title": "Kwiaty", "assignees": ["leon"], "kto_label": "Leon", "date": "2025-11-01"}],
        "grafik": {"2025-11-03": [{"opis": "Natalia pracuje 8–16"}]},
    }
    text = house_agenda(ctx, {})
    assert ctx.domownik.agenda_args == (date(2025, 11, 3), 1)
    assert text == (
        "poniedziałek 2025-11-03 – twoje: nic; Natalia: Pranie (na zmianę); wspólne: Śmieci (zrobione)."
        " Grafik: Natalia pracuje 8–16\nZaległe – twoje: Kwiaty z 2025-11-01"
    )


def test_overdue_is_grouped_by_title(ctx):
    dishes = [{"title": "Zmywanie", "assignees": ["leon", "natalia"], "kto": who.lower(), "kto_label": who,
               "date": f"2025-10-{d:02}"} for who, d in [("Leon", 20), ("Natalia", 21), ("Leon", 22)]]
    ctx.domownik.agenda_data = {"days": [], "grafik": {}, "overdue": [
        *dishes, {"title": "Rachunki", "assignees": ["leon"], "kto": "leon", "kto_label": "Leon", "date": "2025-10-25"},
    ]}
    assert house_agenda(ctx, {}) == (
        "Zaległe – twoje: Zmywanie 2× od 2025-10-20, Rachunki z 2025-10-25; Natalia: Zmywanie z 2025-10-21"
    )


def test_chore_done_prefers_undone_and_reaches_overdue(ctx):
    ctx.domownik.agenda_data = {
        "days": [{"date": "2025-11-03", "items": [{"id": "p1", "title": "Pranie", "done": True}]}],
        "overdue": [{"id": "p2", "title": "Pranie", "date": "2025-11-01", "done": False}],
    }
    assert chore_done(ctx, {"query": "pranie"}) == "Odhaczyłem: Pranie."
    assert ctx.domownik.done_calls == [("p2", "2025-11-01", True)]
    with pytest.raises(ToolError, match="^Jutro nie widzę takiego obowiązku. Są: Pranie.$"):
        chore_done(ctx, {"query": "odkurzanie", "date": "2025-11-04"})  # wspólne „-anie” to nie dopasowanie


@pytest.mark.parametrize(("query", "title", "match"), [
    ("mleka", "mleko", True),
    ("promotora", "Spotkanie z promotorem", True),
    ("podlac kwiaty", "Podlać kwiaty w salonie", True),
    ("odkurzanie", "Pranie", False),
    ("prasowanie", "Pranie", False),
    ("masło", "mleko", False),
])
def test_fuzzy_title_matching(query, title, match):
    assert bool(_best_matches(query, [{"title": title}])) is match


def test_shopping_add_bought_remove_and_clear(ctx):
    add = shopping_update(ctx, {"action": "add", "items": [{"title": "mleko", "qty": "2"}, {"title": "chleb"}]})
    assert add == "Dodałem do zakupów: mleko i chleb."
    assert shopping_list(ctx, {}) == "Do kupienia: mleko (2), chleb."
    reply = shopping_update(ctx, {"action": "bought", "items": [{"title": "Mleka"}, {"title": "masło"}]})
    assert reply == "Odhaczyłem jako kupione: mleko. Nie ma na liście: masło."
    assert shopping_update(ctx, {"action": "clear_bought"}) == "Usunąłem z listy kupione rzeczy (1)."
    assert shopping_update(ctx, {"action": "remove", "items": [{"title": "chleb"}]}) == "Usunąłem z listy: chleb."
    assert shopping_list(ctx, {}) == "Lista zakupów jest pusta."
    with pytest.raises(ToolError):
        shopping_update(ctx, {"action": "add", "items": []})


def test_open_domownik_opens_page(ctx, recorder):
    assert open_domownik(ctx, {"page": "zakupy"}) == "Otwieram listę zakupów."
    assert open_domownik(ctx, {}) == "Otwieram kalendarz."
    navigations = [e.data for e in recorder.events if e.topic == "ui.navigate"]
    assert navigations == [{"view": "dom", "path": "/zakupy"}, {"view": "dom", "path": "/kalendarz"}]


def test_chore_add_keeps_time_separately(ctx):
    reply = chore_add(ctx, {"title": "Spotkanie z Kasią", "time": "15"})
    assert reply == "Dodałem do kalendarza: Spotkanie z Kasią, dziś o 15:00, wspólne."
    assert ctx.domownik.added[-1]["time"] == "15:00" and ctx.domownik.added[-1]["start_date"] == "2025-11-03"
    # model wpisał godzinę do tytułu – przenosimy ją do pola
    chore_add(ctx, {"title": "Dentysta 14:30"})
    assert ctx.domownik.added[-1]["title"] == "Dentysta" and ctx.domownik.added[-1]["time"] == "14:30"
    chore_add(ctx, {"title": "Urodziny Asi 15.03"})  # to data, nie godzina
    assert ctx.domownik.added[-1]["title"] == "Urodziny Asi 15.03" and ctx.domownik.added[-1]["time"] is None
    with pytest.raises(ToolError, match="godziny"):
        chore_add(ctx, {"title": "X", "time": "później"})
