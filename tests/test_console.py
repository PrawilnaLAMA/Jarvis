"""Konsola: każde polecenie dopiero po zgodzie użytkownika – na atrapie, nic się naprawdę nie uruchamia."""

import json
import subprocess

import pytest

from jarvis.assistant import Assistant
from jarvis.conversation import Conversation
from jarvis.settings import SettingsStore
from jarvis.tools import ToolContext, ToolError, console


class Shell:
    def __init__(self, output="Python 3.11.9"):
        self.output, self.error, self.ran = output, None, []

    def __call__(self, command):
        self.ran.append(command)
        if self.error:
            raise self.error
        return self.output


@pytest.fixture
def shell():
    return Shell()


@pytest.fixture
def ctx(tmp_path, bus, domownik, messenger, inbox, shell):
    return ToolContext(settings=SettingsStore(tmp_path / "s.json"), bus=bus, domownik=domownik, discord=None,
                       messenger=messenger, inbox=inbox, conversation=Conversation(tmp_path / "c.json", lambda: 12),
                       shell=shell)


def ask(ctx, command="python --version", description="Sprawdzę wersję Pythona"):
    return console.run_command(ctx, {"command": command, "description": description})


def test_command_waits_for_yes(ctx, shell, recorder):
    assert ask(ctx) == "Sprawdzę wersję Pythona. Mam to zrobić? Powiedz „tak” albo „nie” – polecenie jest w czacie."
    assert shell.ran == []  # nic bez zgody
    request = recorder.of("confirm.request")[-1]
    assert request["command"] == "python --version"
    assert console.answer_pending(ctx, "Jarvis, tak, zrób to.") == "Gotowe: Python 3.11.9"
    assert shell.ran == ["python --version"]
    assert recorder.of("confirm.done")[-1] == {"id": request["id"], "status": "done", "output": "Python 3.11.9"}
    assert console.answer_pending(ctx, "tak") is None  # drugi raz nic się nie wykona


def test_no_other_topic_or_timeout_runs_nothing(ctx, shell, recorder, monkeypatch):
    ask(ctx)
    assert console.answer_pending(ctx, "nie") == "Dobrze, nie robię tego."
    ask(ctx)
    assert console.answer_pending(ctx, "jaka jest pogoda") is None  # inny temat – prośba przepada
    assert console.answer_pending(ctx, "tak") is None
    ask(ctx)
    ctx.state["pending_command"]["at"] -= console.CONFIRM_SECONDS + 1
    assert console.answer_pending(ctx, "tak") is None
    assert shell.ran == []
    assert [d["status"] for d in recorder.of("confirm.done")] == ["cancelled", "expired", "expired"]


def test_button_needs_the_exact_pending_command(ctx, shell, recorder):
    ask(ctx, "Get-Date")
    first = recorder.of("confirm.request")[-1]["id"]
    ask(ctx, "Get-Process")  # nowa prośba zastępuje starą
    second = recorder.of("confirm.request")[-1]["id"]
    assert console.resolve(ctx, first, True) is None
    shell.output = "\n".join(f"proces {i}" for i in range(20))
    assert console.resolve(ctx, second, True) == "Gotowe – wynik jest w czacie."
    assert shell.ran == ["Get-Process"]


def test_failed_command_reports_details(ctx, shell, recorder):
    shell.error = subprocess.CalledProcessError(1, "powershell", b"", b"Nie znaleziono polecenia")
    ask(ctx, "Get-Cos")
    assert console.answer_pending(ctx, "tak") == "Nie udało się – szczegóły są w czacie."
    assert recorder.of("confirm.done")[-1]["output"] == "Nie znaleziono polecenia"
    with pytest.raises(ToolError):
        console.run_command(ctx, {"command": " "})


class ScriptedLLM:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), 0

    def chat(self, messages, tools=None, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


def test_assistant_answers_yes_without_the_model(tmp_path, ctx, shell, bus):
    call = {"id": "c1", "type": "function",
            "function": {"name": "run_command", "arguments": json.dumps({"command": "python --version",
                                                                         "description": "Sprawdzę wersję Pythona"})}}
    llm = ScriptedLLM({"tool_calls": [call]})
    assistant = Assistant(llm, ctx, ctx.settings, bus, ctx.conversation)
    assert "Mam to zrobić?" in assistant.handle("jaką mam wersję pythona")
    assert assistant.handle("tak") == "Gotowe: Python 3.11.9"
    assert llm.calls == 1 and shell.ran == ["python --version"]  # zgodę rozstrzygnął kod, nie model
