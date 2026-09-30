import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from jarvis.app import JarvisApp
from jarvis.services.domownik_client import DomownikError
from jarvis.web.server import create_app


class FakeLLM:
    configured = True

    def chat(self, messages, tools=None, **kwargs):
        return {"content": f"Odpowiedź na: {messages[-1]['content'].split(chr(10))[-1]}"}

    def list_models(self):
        return ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("DISCORD_USER_TOKEN", raising=False)
    monkeypatch.delenv("USER_TOKEN", raising=False)
    return JarvisApp(data_dir=tmp_path / "data", env_file=tmp_path / ".env", voice=False, llm=FakeLLM())


LOCAL = "http://127.0.0.1:8765"
WS = "ws://127.0.0.1:8765/ws"  # klient WebSocket w testach nie bierze adresu z base_url


@pytest.fixture
def client(app):
    with TestClient(create_app(app), base_url=LOCAL) as c:
        yield c


def test_only_the_jarvis_window_may_talk_to_the_api(client):
    # obca strona w przeglądarce (Origin) i podmiana DNS na 127.0.0.1 (obcy Host) – odmowa
    evil = {"origin": "https://zla-strona.example"}
    assert client.post("/api/command", json={"text": "cześć"}, headers=evil).status_code == 403
    assert client.get("/api/status", headers={"host": "zla-strona.example:8765"}).status_code == 403
    assert client.post("/api/command", json={"text": "cześć"}, headers={"origin": LOCAL}).status_code == 200
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(WS, headers=evil) as ws:
        ws.receive_json()
    with client.websocket_connect(WS, headers={"origin": LOCAL}) as ws:
        assert ws.receive_json()["topic"] == "hello"


def test_status_and_static_index(client):
    status = client.get("/api/status").json()
    assert status["voice"]["available"] is False and status["llm_configured"] is True
    assert status["state"] == "idle"
    assert client.get("/").status_code == 200


def test_command_returns_reply(client):
    assert client.post("/api/command", json={"text": "cześć"}).json() == {"reply": "Odpowiedź na: cześć"}
    assert client.post("/api/command", json={"text": " "}).status_code == 400


def test_domownik_status(client, app, domownik):
    app.domownik = domownik  # bez sieci – prawdziwy Domownik może akurat działać na tym komputerze
    # wbudowany serwer nie wystartował (app.start() nie było) – nie ufamy temu, co odpowiada na porcie
    status = client.get("/api/domownik/status").json()
    assert status["ok"] is False and status["serve"] is True and "uruchamia" in status["error"]
    assert app.status()["domownik"]["url"] == "http://127.0.0.1:8080"

    app.settings.update({"domownik": {"serve": False, "url": "http://domownik.test"}})
    status = client.get("/api/domownik/status").json()
    assert status["ok"] is True and status["url"] == "http://domownik.test" and status["error"] is None
    domownik.error = DomownikError("Domownik nie odpowiada.")
    assert client.get("/api/domownik/status").json() == {**status, "ok": False, "error": "Domownik nie odpowiada."}


def test_messenger_endpoints_when_disabled(client):
    assert client.get("/api/messenger/status").json() == {"enabled": False, "state": "off", "error": ""}
    assert client.get("/api/status").json()["messenger"]["state"] == "off"
    threads = client.get("/api/messenger/threads")
    assert threads.status_code == 409 and "wyłączony" in threads.json()["detail"]
    assert client.post("/api/messenger/window", json={"visible": True}).status_code == 409


def test_settings_validation_and_secrets(client, app):
    ok = client.put("/api/settings", json={"voice": {"tts_rate": 15}})
    assert ok.json()["settings"]["voice"]["tts_rate"] == 15
    bad = client.put("/api/settings", json={"contacts": [{"name": "A", "channel_id": "x"}]})
    assert bad.status_code == 400 and bad.json()["errors"]

    secrets = client.put("/api/secrets", json={"DISCORD_USER_TOKEN": "token-123456789", "GROQ_API_KEY": ""})
    assert secrets.json()["secrets"]["DISCORD_USER_TOKEN"] == {"set": True, "hint": "…6789"}
    assert client.put("/api/secrets", json={"PATH": "x"}).status_code == 400
    assert client.get("/api/settings").json()["secrets"]["DISCORD_USER_TOKEN"]["set"] is True


def test_models_and_voice_endpoints_without_audio(client):
    assert client.get("/api/llm/models").json()["models"] == ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]
    assert client.post("/api/tts/preview", json={"voice": "pl-PL-MarekNeural"}).status_code == 409


def test_websocket_hello_command_and_events(client):
    with client.websocket_connect(WS) as ws:
        hello = ws.receive_json()
        assert hello["topic"] == "hello" and hello["data"]["state"] == "idle"
        ws.send_json({"type": "command", "text": "która godzina"})
        topics = []
        while "reply" not in topics:
            message = ws.receive_json()
            topics.append(message["topic"])
        assert topics.index("transcript") < topics.index("reply")
        assert "state" in topics  # thinking → idle

    # historia trafia do nowego połączenia
    with client.websocket_connect(WS) as ws:
        history = ws.receive_json()["data"]["history"]
        assert [m["topic"] for m in history][-2:] == ["transcript", "reply"]


def test_window_show_for_second_instance(client, app):
    shown = []
    app.bus.subscribe(lambda e: shown.append(e.topic), {"ui.show"})
    assert client.post("/api/window/show").json() == {"shown": True}
    assert shown == ["ui.show"]


def test_autostart_endpoints(client, monkeypatch):
    from jarvis import autostart

    state = {"enabled": False}  # zamiast prawdziwego rejestru
    monkeypatch.setattr(autostart, "supported", lambda: True)
    monkeypatch.setattr(autostart, "is_enabled", lambda: state["enabled"])
    monkeypatch.setattr(autostart, "set_enabled", lambda enabled: state.update(enabled=enabled))
    assert client.get("/api/autostart").json() == {"supported": True, "enabled": False}
    assert client.put("/api/autostart", json={"enabled": True}).json() == {"supported": True, "enabled": True}
    monkeypatch.setattr(autostart, "supported", lambda: False)
    assert client.put("/api/autostart", json={"enabled": False}).status_code == 409


def test_confirm_endpoint_only_for_a_pending_command(client):
    assert client.post("/api/confirm", json={"id": "nie-ma", "accept": True}).status_code == 409
    evil = {"origin": "https://zla-strona.example"}
    assert client.post("/api/confirm", json={"id": "x", "accept": True}, headers=evil).status_code == 403


def test_timers_set_in_the_orb_to_the_second(client):
    timer = client.post("/api/timers", json={"seconds": 95, "label": "jajka"}).json()["timers"][0]
    assert timer["label"] == "jajka" and timer["total"] == 95 and not timer["paused"]
    with client.websocket_connect(WS) as ws:  # nowe okno od razu widzi odliczanie
        assert ws.receive_json()["data"]["timers"][0]["id"] == timer["id"]
    url = f"/api/timers/{timer['id']}"
    assert client.post(url, json={"action": "pause"}).json()["timers"][0]["paused"] is True
    assert client.post(url, json={"action": "add", "seconds": 60}).json()["timers"][0]["total"] == 155
    assert client.post(url, json={"action": "explode"}).status_code == 400
    assert client.post(url, json={"action": "cancel"}).json() == {"timers": []}
    assert client.post(url, json={"action": "resume"}).status_code == 404
    assert client.post("/api/timers", json={"seconds": 0}).status_code == 400
    assert client.post("/api/timers", json={"seconds": "pięć"}).status_code == 400


def test_reminders_in_hello_and_ack(app, client):
    app.reminders._pending = [{"key": "k", "title": "Dentysta", "text": "Przypomnienie: Dentysta o 15:00."}]
    with client.websocket_connect(WS) as ws:
        assert ws.receive_json()["data"]["reminders"][0]["title"] == "Dentysta"
    assert client.get("/api/reminders").json()["pending"][0]["key"] == "k"
    assert client.post("/api/reminders/ack").json() == {"pending": []}
