import pytest
from fastapi.testclient import TestClient

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


@pytest.fixture
def client(app):
    with TestClient(create_app(app)) as c:
        yield c


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
    assert client.get("/api/domownik/status").json() == {"url": "http://domownik.test", "ok": True, "error": None}
    domownik.error = DomownikError("Domownik nie odpowiada.")
    assert client.get("/api/domownik/status").json()["ok"] is False
    assert app.status()["domownik_url"] == "http://127.0.0.1:8080"


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
    with client.websocket_connect("/ws") as ws:
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
    with client.websocket_connect("/ws") as ws:
        history = ws.receive_json()["data"]["history"]
        assert [m["topic"] for m in history][-2:] == ["transcript", "reply"]
