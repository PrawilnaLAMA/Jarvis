"""Rejestr narzędzi udostępnianych modelowi językowemu.

Nowe narzędzie: funkcja `handler(ctx, args) -> str` + wpis `Tool(...)` w jednym z modułów
i dopisanie modułu poniżej. Zwrócony tekst jest wypowiadany (albo wraca do modelu, gdy
`speak_directly=False`).
"""

import sys

from jarvis.settings import Settings
from jarvis.tools import computer, console, domownik, messaging, system, web
from jarvis.tools.base import Tool, ToolContext, ToolError

__all__ = ["Tool", "ToolContext", "ToolError", "build_tools"]


def build_tools(settings: Settings) -> list[Tool]:
    tools = [*web.tools(), *messaging.tools(settings), *domownik.tools(), *system.tools(), *computer.tools()]
    if sys.platform == "win32":
        tools += console.tools()  # PowerShell – każde polecenie po zgodzie użytkownika
    return tools
