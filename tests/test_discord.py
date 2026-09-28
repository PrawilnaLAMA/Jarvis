import pytest

from jarvis.services.discord_client import DiscordClient, DiscordError
from jarvis.services.discord_monitor import DiscordMonitor
from jarvis.settings import SettingsStore


class FakeResponse:
    def __init__(self, status: int, payload=None):
        self.status_code = status
        self._payload = payload
        self.content = b"x" if payload is not None else b""

    def json(self):
        return self._payload


class FakeSession:
    """Udaje Discorda: kanały z listą wiadomości (najnowsza pierwsza)."""

    def __init__(self):
        self.channels: dict[str, list[dict]] = {}
        self.sent: list[tuple[str, str]] = []
        self.status = 200

    def request(self, method, url, headers=None, timeout=None, params=None, json=None):
        assert headers == {"authorization": "tok"}
        if self.status != 200:
            return FakeResponse(self.status, {})
        if url.endswith("/users/@me"):
            return FakeResponse(200, {"id": "me"})
        channel = url.split("/channels/")[1].split("/")[0]
        if method == "POST":
            self.sent.append((channel, json["content"]))
            return FakeResponse(200, {"id": "new"})
        return FakeResponse(200, self.channels.get(channel, [])[:1])


def msg(msg_id: str, author: str, content: str) -> dict:
    return {"id": msg_id, "author": {"id": author}, "content": content}


@pytest.fixture
def session():
    return FakeSession()


@pytest.fixture
def client(session):
    return DiscordClient(lambda: "tok", session=session)


def test_client_errors_are_polish(session, client):
    session.status = 401
    with pytest.raises(DiscordError, match="nieprawidłowy"):
        client.send_message("1", "hej")
    with pytest.raises(DiscordError, match="Brak tokenu"):
        DiscordClient(lambda: None, session=session).me()
    session.status = 503
    with pytest.raises(DiscordError, match="chwilowo") as err:
        client.send_message("1", "hej")
    assert err.value.temporary is True


def test_monitor_retries_hiccups_quietly(tmp_path, bus, recorder, session, client, inbox):
    settings = SettingsStore(tmp_path / "s.json")
    settings.update({"contacts": [{"name": "PIOTREK", "channel_id": "111111"}], "discord": {"poll_seconds": 3}})
    now = [0.0]
    monitor = DiscordMonitor(client, settings, bus, inbox, clock=lambda: now[0])
    session.status = 503

    delays = []
    for _ in range(4):  # pojedyncze 503 i kilkadziesiąt sekund przerwy – bez komunikatu, coraz rzadziej
        delays.append(monitor.check())
        now[0] += delays[-1]
    assert delays == [6, 12, 24, 48] and recorder.of("notice") == []

    now[0] += 60  # dłuższa awaria – jeden komunikat, potem cisza
    assert monitor.check() == 60
    monitor.check()
    notices = [n["text"] for n in recorder.of("notice")]
    assert len(notices) == 1 and "nie odpowiada od" in notices[0]

    session.status = 200
    assert monitor.check() == 3
    assert recorder.of("notice")[-1]["text"] == "Discord znów odpowiada."

    session.status = 503  # kolejna pojedyncza czkawka po powrocie – znowu cicho
    monitor.check()
    assert len(recorder.of("notice")) == 2


def test_monitor_reports_permanent_error_once(tmp_path, bus, recorder, session, client, inbox):
    settings = SettingsStore(tmp_path / "s.json")
    settings.update({"contacts": [{"name": "PIOTREK", "channel_id": "111111"}]})
    monitor = DiscordMonitor(client, settings, bus, inbox)
    session.status = 401
    monitor.check()
    monitor.check()
    assert [n["text"] for n in recorder.of("notice")] == ["Discord: Token Discorda jest nieprawidłowy."]


def test_monitor_announces_only_new_foreign_messages(tmp_path, bus, recorder, session, client, inbox, spoken):
    settings = SettingsStore(tmp_path / "s.json")
    settings.update({"contacts": [{"name": "PIOTREK", "channel_id": "111111"},
                                  {"name": "NATALIA", "messenger": "123456789"}]})  # bez Discorda – pomijana
    monitor = DiscordMonitor(client, settings, bus, inbox)
    session.channels["111111"] = [msg("1", "other", "stara wiadomość")]
    assert monitor.poll_once() == []  # pierwszy odczyt tylko zapamiętuje stan

    session.channels["111111"].insert(0, msg("2", "other", "gramy?"))
    assert monitor.poll_once() == ["Piotrek pisze: gramy?"]
    assert monitor.poll_once() == []

    session.channels["111111"].insert(0, msg("3", "me", "moja odpowiedź"))
    assert monitor.poll_once() == []

    session.channels["111111"].insert(0, msg("4", "other", ""))
    settings.update({"discord": {"read_aloud": False}})
    assert monitor.poll_once() == ["Piotrek przesyła załącznik."]
    assert spoken == ["Piotrek pisze: gramy?"]
    assert len(recorder.of("discord.message")) == 2
    assert inbox.last().contact == "PIOTREK" and inbox.last_app_of("PIOTREK") == "discord"
