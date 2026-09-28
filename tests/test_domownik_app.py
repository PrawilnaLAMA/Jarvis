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
    assert missing.status_code == 404 and "Tu nic nie ma" in missing.get_data(as_text=True)
    assert client.get("/api/nie-ma").get_json() == {"error": "Nie ma takiego zasobu."}


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
