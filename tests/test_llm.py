import pytest
import requests

from jarvis.llm import LLMClient, LLMError, Provider, providers_from
from jarvis.settings import Secrets, Settings


class Resp:
    def __init__(self, status, payload=None, text="", headers=None):
        self.status_code = status
        self._payload = payload or {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append((url, json))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def get(self, url, headers=None, timeout=None):
        return self.responses.pop(0)


OK = Resp(200, {"choices": [{"message": {"role": "assistant", "content": "cześć"}}]})
GROQ = Provider("Groq", "https://groq", "k1", "openai/gpt-oss-120b")
CEREBRAS = Provider("Cerebras", "https://cerebras", "k2", "gpt-oss-120b")


def test_success_sends_reasoning_effort_for_gpt_oss():
    session = Session(OK)
    msg = LLMClient(lambda: [GROQ], session).chat([{"role": "user", "content": "hej"}], tools=[{"x": 1}])
    assert msg["content"] == "cześć"
    body = session.calls[0][1]
    assert body["reasoning_effort"] == "low" and body["tools"] == [{"x": 1}]


def test_rate_limit_falls_back_to_second_provider():
    session = Session(Resp(429), OK)
    LLMClient(lambda: [GROQ, CEREBRAS], session).chat([])
    assert [c[0] for c in session.calls] == ["https://groq/chat/completions", "https://cerebras/chat/completions"]


def test_short_rate_limit_waits_and_retries(monkeypatch):
    slept = []
    monkeypatch.setattr("jarvis.llm.time.sleep", slept.append)
    session = Session(Resp(429, headers={"retry-after": "2"}), OK)
    assert LLMClient(lambda: [GROQ], session).chat([])["content"] == "cześć"
    assert slept == [2.0]
    # długi limit – nie czekamy, od razu błąd
    with pytest.raises(LLMError, match="limit"):
        LLMClient(lambda: [GROQ], Session(Resp(429, headers={"retry-after": "60"}))).chat([])


def test_retries_tool_use_failed_and_server_errors():
    session = Session(Resp(400, text='{"error":{"code":"tool_use_failed"}}'), OK)
    assert LLMClient(lambda: [GROQ], session).chat([])["content"] == "cześć"


def test_errors_are_polish():
    with pytest.raises(LLMError, match="Brak klucza"):
        LLMClient(lambda: []).chat([])
    with pytest.raises(LLMError, match="nieprawidłowy"):
        LLMClient(lambda: [GROQ], Session(Resp(401))).chat([])
    with pytest.raises(LLMError, match="internet"):
        LLMClient(lambda: [GROQ], Session(requests.ConnectionError(), requests.ConnectionError())).chat([])


def test_list_models_filters_non_chat():
    payload = {"data": [{"id": "whisper-large-v3"}, {"id": "openai/gpt-oss-120b"}, {"id": "qwen/qwen3.8-27b"},
                        {"id": "meta-llama/llama-prompt-guard-2-86m"}]}
    client = LLMClient(lambda: [GROQ], Session(Resp(200, payload)))
    assert client.list_models() == ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]


def test_providers_from_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    secrets = Secrets(tmp_path / ".env")
    assert [p.name for p in providers_from(Settings(), secrets)] == ["Groq"]
    monkeypatch.setenv("CEREBRAS_API_KEY", "c")
    assert [p.name for p in providers_from(Settings(), secrets)] == ["Groq", "Cerebras"]
