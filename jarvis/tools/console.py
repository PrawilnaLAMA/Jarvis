"""Konsola PowerShell – do rzeczy, na które nie ma gotowego narzędzia.

Każde polecenie czeka na zgodę użytkownika: Jarvis mówi, co chce zrobić, polecenie pokazuje w czacie
(zdarzenie confirm.request) i wykonuje dopiero po „tak” (głosem albo z klawiatury) lub po przycisku
„Wykonaj”. Po tekście polecenia nie da się pewnie odróżnić nieszkodliwego od groźnego, a zgoda
użytkownika jest jedyną gwarancją, że wykona się tylko to, czego on chce.
"""

import re
import subprocess
import time
import uuid
from typing import Any

from jarvis.tools.base import Tool, ToolContext, ToolError, params

CONFIRM_SECONDS = 120  # potem prośba wygasa – „tak” za pięć minut nie powinno niczego uruchomić
MAX_OUTPUT = 4000  # tyle wyniku trafia do czatu
SPOKEN_OUTPUT = 160  # krótki wynik Jarvis czyta, dłuższy zostaje w czacie

_YES = {"tak", "wykonaj", "zrob to", "zrob", "rob", "dawaj", "potwierdzam", "jasne", "ok", "okej", "dobrze",
        "pewnie", "zgoda", "no tak"}
_YES_WORDS = {"tak", "zrob", "to", "wykonaj", "prosze", "jasne", "dawaj", "oczywiscie", "pewnie"}  # „tak, tak”
_NO = {"nie", "anuluj", "stop", "zostaw", "odwolaj"}
_ASCII = str.maketrans("ąćęłńóśźż", "acelnoszz")


def run_command(ctx: ToolContext, args: dict[str, Any]) -> str:
    command = str(args.get("command", "")).strip()
    if not command:
        raise ToolError("Nie wiem, jakie polecenie uruchomić.")
    description = str(args.get("description", "")).strip().rstrip(".") or "Uruchomię polecenie w konsoli"
    _drop(ctx, "expired")  # nowa prośba zastępuje starą
    pending = {"id": uuid.uuid4().hex, "command": command, "description": description, "at": time.monotonic()}
    ctx.state["pending_command"] = pending
    ctx.bus.publish("confirm.request", id=pending["id"], description=description, command=command)
    return f"{description}. Mam to zrobić? Powiedz „tak” albo „nie” – polecenie jest w czacie."


def answer_pending(ctx: ToolContext, text: str) -> str | None:
    """Odpowiedź na prośbę o zgodę („tak”/„nie”); None, gdy to nie odpowiedź – wtedy prośba przepada."""
    pending = _pending(ctx)
    if not pending:
        return None
    words = re.findall(r"[a-z]+", text.lower().translate(_ASCII))
    if words[:1] == ["jarvis"]:
        words = words[1:]
    phrase = " ".join(words)
    if phrase in _YES or (words[:1] == ["tak"] and set(words) <= _YES_WORDS):
        return resolve(ctx, pending["id"], True)
    if phrase in _NO or words[:1] == ["nie"]:  # „nie wiem” też odrzuca – w razie wątpliwości nic nie robimy
        return resolve(ctx, pending["id"], False)
    _drop(ctx, "expired")  # użytkownik mówi o czymś innym – nie trzymamy polecenia w zawieszeniu
    return None


def resolve(ctx: ToolContext, command_id: str, accept: bool) -> str | None:
    """Wykonuje albo odrzuca czekające polecenie; None, gdy nie ma już takiego (wygasło, zastąpione)."""
    pending = _pending(ctx)
    if not pending or pending["id"] != command_id:
        return None
    ctx.state.pop("pending_command", None)
    if not accept:
        ctx.bus.publish("confirm.done", id=command_id, status="cancelled", output="")
        return "Dobrze, nie robię tego."
    try:
        output, ok = ctx.shell(pending["command"]), True
    except subprocess.TimeoutExpired:
        output, ok = "Polecenie trwało za długo i zostało przerwane.", False
    except subprocess.CalledProcessError as e:
        output, ok = _text(e.stderr) or _text(e.output) or f"Kod wyjścia {e.returncode}.", False
    except OSError as e:
        output, ok = str(e), False
    output = output.strip()
    ctx.bus.publish("confirm.done", id=command_id, status="done" if ok else "failed", output=output[:MAX_OUTPUT])
    if not ok:
        return "Nie udało się – szczegóły są w czacie."
    if output and len(output) <= SPOKEN_OUTPUT and "\n" not in output:
        return f"Gotowe: {output}"
    return "Gotowe – wynik jest w czacie." if output else "Gotowe."


def _pending(ctx: ToolContext) -> dict[str, Any] | None:
    pending = ctx.state.get("pending_command")
    if pending and time.monotonic() - pending["at"] > CONFIRM_SECONDS:
        _drop(ctx, "expired")
        return None
    return pending


def _drop(ctx: ToolContext, status: str) -> None:
    pending = ctx.state.pop("pending_command", None)
    if pending:
        ctx.bus.publish("confirm.done", id=pending["id"], status=status, output="")


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value or "").strip()


def tools() -> list[Tool]:
    return [
        Tool(
            "run_command",
            "Polecenie PowerShell na komputerze użytkownika – tylko gdy nie ma gotowego narzędzia. "
            "Wykona się dopiero po zgodzie użytkownika.",
            params({
                "command": {"type": "string"},
                "description": {"type": "string", "description": "po polsku, co zrobi, np. „Sprawdzę wersję Pythona”"},
            }, ["command", "description"]),
            run_command,
        ),
    ]
