"""Aplikacja Domownika (Flask) na pliku tymczasowym – bez sieci i bez prawdziwych danych."""

import json
import re
from datetime import date

import pytest

from jarvis.domownik import chores as core
from jarvis.domownik import create_app, shopping

DAY = "2026-09-28"


@pytest.fixture
def data_file(tmp_path):
    return tmp_path / "domownik" / "chores.json"


@pytest.fixture
def client(data_file):
    return create_app(data_file).test_client()


def test_pages_have_jarvis_look(client):
    for path in ("/", "/kalendarz", "/zakupy", "/obowiazki"):
        html = client.get(path).get_data(as_text=True)
        assert '<use href="#i-calendar"/>' in html  # ikony SVG w zakładkach
        assert 'name="color-scheme" content="dark"' in html and "themeToggle" not in html
    missing = client.get("/nie-ma")
    assert missing.status_code == 404 and "Nie ma takiej strony" in missing.get_data(as_text=True)
    assert client.get("/api/nie-ma").get_json() == {"error": "Nie ma takiego zasobu."}


def test_today_is_split_into_person_lanes(client):
    html = client.get("/").get_data(as_text=True)
    lanes = [html.index(f'data-lane="{key}"') for key in ("leon", "wspolne", "natalia")]
    assert lanes == sorted(lanes)  # Leon | Wspólne | Natalia
    assert 'id="domLanes"' in html and "Wspólne" in html


def test_pwa_routes(client):
    worker = client.get("/sw.js")
    assert worker.headers["Service-Worker-Allowed"] == "/" and worker.headers["Cache-Control"] == "no-cache"
    manifest = client.get("/manifest.webmanifest")
    assert manifest.mimetype == "application/manifest+json"
    assert json.loads(manifest.data)["theme_color"] == "#05070d"


def test_examples_are_seeded_only_once(data_file):
    first = create_app(data_file).test_client().get("/api/obowiazki").get_json()["chores"]
    assert first
    again = create_app(data_file).test_client().get("/api/obowiazki").get_json()["chores"]
    assert len(again) == len(first)


def test_chore_lifecycle(client):
    created = client.post(
        "/api/obowiazki",
        json={"title": "Wynieść śmieci", "start_date": DAY, "repeat": {"type": "codziennie"}, "assignees": ["leon"]},
    )
    assert created.status_code == 201
    chore_id = created.get_json()["id"]

    def item():
        agenda = client.get(f"/api/agenda?od={DAY}&dni=1&dzis={DAY}").get_json()
        return next(i for i in agenda["days"][0]["items"] if i["id"] == chore_id)

    assert item()["kto"] == "leon" and item()["done"] is False
    assert client.post("/api/odhacz", json={"id": chore_id, "date": DAY}).get_json()["done"] is True
    assert item()["done"] is True

    empty = client.post("/api/obowiazki", json={"title": ""})
    assert empty.status_code == 400 and "pusta" in empty.get_json()["error"]
    assert client.delete(f"/api/obowiazki/{chore_id}").status_code == 200
    assert client.delete(f"/api/obowiazki/{chore_id}").status_code == 404


def test_day_is_ordered_by_time(client):
    for title, time in (("Pranie", None), ("Dentysta", "15:00"), ("Śniadanie", "8:30"), ("Obiad", "13")):
        body = {"title": title, "start_date": DAY, "time": time, "assignees": ["leon"]}
        assert client.post("/api/obowiazki", json=body).status_code == 201
    done_id = next(c["id"] for c in client.get("/api/obowiazki").get_json()["chores"] if c["title"] == "Śniadanie")
    client.post("/api/odhacz", json={"id": done_id, "date": DAY})

    agenda = client.get(f"/api/agenda?od={DAY}&dni=1&dzis={DAY}").get_json()
    items = [(i["time"], i["title"]) for i in agenda["days"][0]["items"] if i["title"] != "Pozmywać naczynia"]
    # z godziną chronologicznie (także zrobione), bez godziny na końcu
    assert items[:3] == [("08:30", "Śniadanie"), ("13:00", "Obiad"), ("15:00", "Dentysta")]
    assert all(time == "" for time, _ in items[3:]) and ("", "Pranie") in items[3:]

    bad = client.post("/api/obowiazki", json={"title": "x", "time": "25:00"})
    assert bad.status_code == 400 and "godzina" in bad.get_json()["error"]


def test_reminder_needs_time_and_range(client):
    ok = client.post("/api/obowiazki", json={"title": "Dentysta", "start_date": DAY, "time": "15:00",
                                             "remind_before": 30})
    assert ok.status_code == 201 and ok.get_json()["remind_before"] == 30
    item = client.get(f"/api/agenda?od={DAY}&dni=1&dzis={DAY}").get_json()["days"][0]["items"]
    assert next(i for i in item if i["title"] == "Dentysta")["remind_label"] == "30 min przed"
    no_time = client.post("/api/obowiazki", json={"title": "x", "remind_before": 10})
    assert no_time.status_code == 400 and "godziny" in no_time.get_json()["error"]
    too_far = client.post("/api/obowiazki", json={"title": "x", "time": "9:00", "remind_before": 5000})
    assert too_far.status_code == 400
    # PUT tylko z przypomnieniem zostawia resztę
    chore_id = ok.get_json()["id"]
    changed = client.put(f"/api/obowiazki/{chore_id}", json={"remind_before": None}).get_json()
    assert changed["remind_before"] is None and changed["time"] == "15:00"


def test_repeat_rules():
    def chore(repeat, start="2026-01-31"):
        return core.normalize_chore({"title": "x", "start_date": start, "repeat": repeat})

    every3 = chore({"type": "co_x_dni", "interval": 3}, "2026-09-01")
    assert [core.occurs_on(every3, date(2026, 9, d)) for d in (1, 2, 3, 4)] == [True, False, False, True]
    weekly = chore({"type": "tygodniowo", "weekdays": [0]}, "2026-09-01")  # poniedziałki
    assert core.occurs_on(weekly, date(2026, 9, 28)) and not core.occurs_on(weekly, date(2026, 9, 29))
    monthly = chore({"type": "miesiecznie", "day_of_month": 31})
    assert core.occurs_on(monthly, date(2026, 2, 28))  # krótszy miesiąc → ostatni dzień


def test_dictionaries_keep_shop_order(client):
    # działy idą tak, jak się idzie przez sklep – sortowanie kluczy wyłączone w API i w |tojson
    assert list(client.get("/api/slowniki").get_json()["categories"]) == list(core.CATEGORIES)
    html = client.get("/zakupy").get_data(as_text=True)
    embedded = re.search(r'id="shopCategories">(.*?)</script>', html, re.S).group(1)
    assert list(json.loads(embedded)) == list(shopping.CATEGORIES)


def test_shopping_list(client):
    milk = client.post("/api/zakupy", json={"title": "mleko", "qty": "2"}).get_json()
    client.post("/api/zakupy", json={"title": "papier toaletowy"})
    assert milk["category"] == "nabial"
    assert client.put(f"/api/zakupy/{milk['id']}", json={"done": True}).get_json()["done"] is True
    assert client.post("/api/zakupy/wyczysc").get_json()["usuniete"] == 1
    assert [i["title"] for i in client.get("/api/zakupy").get_json()["items"]] == ["papier toaletowy"]


def test_export_import_roundtrip(client, tmp_path):
    exported = client.get("/api/eksport")
    assert exported.headers["Content-Disposition"].startswith("attachment")
    other = create_app(tmp_path / "inny" / "chores.json").test_client()
    count = len(json.loads(exported.data)["chores"])
    assert other.post("/api/import", json=json.loads(exported.data)).get_json() == {"ok": True, "chores": count}
    assert other.post("/api/import", json=[1, 2]).status_code == 400
