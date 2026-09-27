import itertools
import threading
import time

import pytest

from jarvis.services.messenger import MessengerError, MessengerService, Preview, PreviewTracker, parse_row
from jarvis.settings import SettingsStore

THREAD = "e2ee/t/123456789"


@pytest.mark.parametrize(("row", "expected"), [
    ("Natalia Kowalska\nKupisz mleko? · 5 min", Preview("Kupisz mleko?", False)),
    ("Natalia Kowalska\nTy: ok\n·\n2 godz.", Preview("ok", True)),
    ("Natalia\nYou: see you · 1h", Preview("see you", True)),
    ("Natalia\nAktywna teraz\nHej · pon.", Preview("Hej", False)),
    ("Natalia\nNatalia wysłała zdjęcie.\n·\n5 wrz", Preview("Natalia wysłała zdjęcie.", False)),
    ("Natalia\nHej\n3 min", Preview("Hej", False)),
    ("Natalia", None),
    ("Natalia\nWiadomości i rozmowy są chronione przy użyciu pełnego szyfrowania.\n·\n4 godz.", None),
])
def test_parse_row(row, expected):
    assert parse_row(row) == expected


@pytest.mark.parametrize(("row", "age"), [
    ("A\nhej\n·\nWłaśnie teraz", 0), ("A\nhej · 3 min", 3), ("A\nhej\n·\n2 godz.", 120),
    ("A\nhej\n·\npon.", 10_000), ("A\nhej\n·\n5 wrz", 10_000), ("A\nhej", None),
])
def test_parse_row_age(row, age):
    assert parse_row(row).age_minutes == age


def test_tracker_announces_only_new_foreign_messages():
    tracker = PreviewTracker()
    threads = ["t/1", "t/2"]
    assert tracker.update({"t/1": "A\nstara · 1 godz."}, threads) == []  # pierwszy odczyt: tylko stan
    assert tracker.update({"t/1": "A\nstara · 2 godz."}, threads) == []  # zmienił się tylko czas
    assert tracker.update({"t/1": "A\nTy: moja · 1 min"}, threads) == []  # własna wiadomość
    assert tracker.update({"t/1": "A\nnowa · 1 min"}, threads) == [("t/1", Preview("nowa", False))]
    assert tracker.update({}, threads) == []  # czat zniknął z listy…
    assert tracker.update({"t/1": "A\nnowa · 9 min"}, threads) == []  # …i wrócił bez zmian
    # czatu nie było na liście – pojawia się, bo przyszła wiadomość
    assert tracker.update({"t/2": "B\nhej · teraz"}, threads) == [("t/2", Preview("hej", False))]


def test_tracker_ignores_restored_history():
    tracker = PreviewTracker()
    placeholder = "A\nWiadomości i rozmowy są chronione przy użyciu pełnego szyfrowania.\n·\n4 godz."
    assert tracker.update({"t/1": placeholder}, ["t/1"]) == []
    # Messenger doczytał historię zaszyfrowanego czatu – stara wiadomość to nie nowa
    assert tracker.update({"t/1": "A\nstara wiadomość\n·\n4 godz."}, ["t/1"]) == []
    assert tracker.update({"t/1": "A\nnowa\n·\nWłaśnie teraz"}, ["t/1"]) == [("t/1", Preview("nowa", False))]


class FakeSession:
    def __init__(self):
        self.state_value = "login"
        self.row_texts: dict[str, str] = {}
        self.sent: list[tuple[str, str]] = []
        self.window: list[bool] = []
        self.closed_flag = False

    def state(self):
        return self.state_value

    def rows(self, threads):
        return {t: self.row_texts[t] for t in threads if t in self.row_texts}

    def send(self, thread, text):
        self.sent.append((thread, text))

    def recent_threads(self):
        return [{"thread": THREAD, "name": "Natalia"}]

    def set_window(self, visible):
        self.window.append(visible)

    def closed(self):
        return self.closed_flag

    def close(self):
        self.closed_flag = True


def wait_for(condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("warunek nie został spełniony")


def test_service_login_poll_send_and_disable(tmp_path, bus, recorder, inbox, spoken):
    settings = SettingsStore(tmp_path / "s.json")
    settings.update({"messenger": {"enabled": True},
                     "contacts": [{"name": "NATALIA", "messenger": f"https://www.messenger.com/{THREAD}/"}]})
    session = FakeSession()
    clock = itertools.count(step=10)  # każdy odczyt zegara to 10 s później – bez czekania na odświeżanie
    service = MessengerService(settings, bus, inbox, tmp_path / "m", launcher=lambda *_: session,
                               clock=lambda: float(next(clock)))
    service.tick = 0.005
    stop = threading.Event()
    service.start(stop)
    try:
        wait_for(lambda: service.status()["state"] == "login")
        assert session.window == [True]  # okno pokazane do logowania
        assert "zaloguj" in recorder.of("notice")[0]["text"]
        with pytest.raises(MessengerError, match="zaloguj"):
            service.send(THREAD, "hej")

        session.row_texts[THREAD] = "Natalia\nTy: ok · 5 min"
        session.state_value = "ready"
        wait_for(lambda: service.status()["state"] == "ready")
        time.sleep(0.05)  # pierwszy odczyt listy – zapamiętanie stanu
        session.row_texts[THREAD] = "Natalia\nKupisz mleko? · 1 min"
        wait_for(lambda: spoken)
        assert spoken == ["Natalia pisze: Kupisz mleko?"]

        service.send(THREAD, "Tak,\nkupię")
        assert session.sent == [(THREAD, "Tak, kupię")]
        assert service.recent_threads() == [{"thread": THREAD, "name": "Natalia"}]

        settings.update({"messenger": {"enabled": False}})
        wait_for(lambda: service.status()["state"] == "off")
        assert session.closed_flag
        with pytest.raises(MessengerError, match="wyłączony"):
            service.send(THREAD, "hej")
    finally:
        stop.set()
        service.join(2)


def test_service_restarts_closed_window(tmp_path, bus, inbox, monkeypatch):
    monkeypatch.setattr("jarvis.services.messenger.RETRY_SECONDS", 0.01)
    settings = SettingsStore(tmp_path / "s.json")
    settings.update({"messenger": {"enabled": True}})
    sessions = []

    def launch(*_):
        sessions.append(FakeSession())
        sessions[-1].state_value = "ready"
        return sessions[-1]

    service = MessengerService(settings, bus, inbox, tmp_path / "m", launcher=launch)
    service.tick = 0.005
    stop = threading.Event()
    service.start(stop)
    try:
        wait_for(lambda: service.status()["state"] == "ready")
        assert sessions[0].window == [False]  # zalogowany z poprzedniego razu – okno schowane
        sessions[0].closed_flag = True  # użytkownik zamknął okno
        wait_for(lambda: len(sessions) == 2 and service.status()["state"] == "ready")
    finally:
        stop.set()
        service.join(2)
