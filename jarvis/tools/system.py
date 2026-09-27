"""Narzędzia systemowe: wyłączanie komputera, milczenie, czyszczenie pamięci rozmowy."""

import subprocess
import sys
from typing import Any

from jarvis.tools.base import Tool, ToolContext, ToolError, params


def shutdown_computer(ctx: ToolContext, args: dict[str, Any]) -> str:
    # opóźnienie chroni przed skutkami pomyłki w rozpoznaniu mowy – można jeszcze anulować
    delay = int(min(max(args.get("delay_seconds") or 30, 10), 3600))
    if sys.platform == "win32":
        command = ["shutdown", "/s", "/t", str(delay)]
        when = f"{delay} sekund"
    else:
        minutes = max(1, round(delay / 60))
        command = ["sudo", "-n", "shutdown", "-h", f"+{minutes}"]
        when = "minutę" if minutes == 1 else f"{minutes} minut"
    try:
        ctx.run_command(command)
    except (OSError, subprocess.SubprocessError) as e:
        raise ToolError("Nie udało się zaplanować wyłączenia komputera.") from e
    return f"Wyłączę komputer za {when}. Powiedz „anuluj wyłączenie”, żeby przerwać."


def cancel_shutdown(ctx: ToolContext, args: dict[str, Any]) -> str:
    command = ["shutdown", "/a"] if sys.platform == "win32" else ["sudo", "-n", "shutdown", "-c"]
    try:
        ctx.run_command(command)
    except (OSError, subprocess.SubprocessError) as e:
        raise ToolError("Nie było zaplanowanego wyłączenia albo nie udało się go anulować.") from e
    return "Anulowałem wyłączenie komputera."


def stay_silent(ctx: ToolContext, args: dict[str, Any]) -> str:
    return ""


def clear_conversation(ctx: ToolContext, args: dict[str, Any]) -> str:
    ctx.conversation.clear()
    return "Dobrze, zapomniałem naszą rozmowę."


def tools() -> list[Tool]:
    return [
        Tool(
            "shutdown_computer",
            "Wyłącza komputer z opóźnieniem, które można anulować.",
            params({"delay_seconds": {"type": "integer"}}),
            shutdown_computer,
        ),
        Tool("cancel_shutdown", "Anuluje zaplanowane wyłączenie komputera.", params(), cancel_shutdown),
        Tool(
            "stay_silent",
            "Nic nie mów – gdy użytkownik każe przestać („stop”, „cisza”) albo mówi nie do ciebie.",
            params(),
            stay_silent,
        ),
        Tool("clear_conversation", "Czyści pamięć rozmowy.", params(), clear_conversation),
    ]
