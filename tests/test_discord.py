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


def test_monitor_announces_only_new_foreign_messages(tmp_path, bus, recorder, session, client):
    settings = SettingsStore(tmp_path / "s.json")
    settings.update({"contacts": [{"name": "PIOTREK", "channel_id": "111111"}]})
    spoken = []
    monitor = DiscordMonitor(client, settings, bus, spoken.append)
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
