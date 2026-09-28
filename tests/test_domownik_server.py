"""Wbudowany serwer Domownika – prawdziwy waitress na wolnym porcie 127.0.0.1 (nigdy w sieci)."""

import socket
import threading
import time

import pytest
import requests

from jarvis.events import EventBus
from jarvis.services import domownik_server
from jarvis.services.domownik_server import DomownikServer
from jarvis.settings import SettingsStore


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(condition, timeout=10.0):
    deadline = time.time() + timeout
    while not condition():
        assert time.time() < deadline, "nie doczekałem się"
        time.sleep(0.02)


@pytest.fixture
def setup(tmp_path):
    bus = EventBus()
    notices = []
    bus.subscribe(lambda e: notices.append(e.data["text"]), {"notice"})
    settings = SettingsStore(tmp_path / "settings.json", on_change=lambda _: bus.publish("settings.changed"))
    settings.update({"domownik": {"lan": False, "port": free_port()}})
    server = DomownikServer(settings, bus, tmp_path / "domownik" / "chores.json")
    yield server, settings, notices
    server.close()


def test_settings_changes_before_start_do_nothing(setup):
    server, settings, _ = setup
    settings.update({"domownik": {"port": free_port()}})
    time.sleep(0.2)
    assert server.status()["state"] == "off"
    assert not any(t.name == "domownik" for t in threading.enumerate())


def test_serves_live_changes_and_restarts_on_new_port(setup):
    server, settings, _ = setup
    server.start()
    wait_for(lambda: server.status()["state"] == "running")
    url = server.status()["url"]

    stream = requests.get(f"{url}/api/zmiany", stream=True, timeout=5)
    lines = stream.iter_lines(decode_unicode=True)
    first = next(lines)
    assert first.startswith("data: ")
    requests.post(f"{url}/api/zakupy", json={"title": "mleko"}, timeout=5)
    next(lines)  # pusta linia kończąca pierwszy pakiet
    assert next(lines) != first  # zapis budzi strumień od razu

    settings.update({"domownik": {"port": free_port()}})
    wait_for(lambda: server.status()["url"] != url and server.status()["state"] == "running")
    items = requests.get(f"{server.status()['url']}/api/zakupy", timeout=5).json()["items"]
    assert [i["title"] for i in items] == ["mleko"]  # te same dane pod nowym portem
    with pytest.raises(requests.ConnectionError):
        requests.get(f"{url}/api/wersja", timeout=2)


def test_busy_port_reports_error_and_recovers(setup, monkeypatch):
    server, settings, notices = setup
    monkeypatch.setattr(domownik_server, "RETRY_SECONDS", 0.2)
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", settings.get().domownik.port))
    blocker.listen()
    server.start()
    wait_for(lambda: server.status()["state"] == "error")
    assert "zajęty" in server.status()["error"] and len(notices) == 1
    blocker.close()
    wait_for(lambda: server.status()["state"] == "running")
    server.close()
    assert server.status()["state"] == "off"
    assert not any(t.name.startswith("waitress") for t in threading.enumerate())
