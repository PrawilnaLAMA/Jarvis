"""Rejestr narzędzi udostępnianych modelowi językowemu.

Nowe narzędzie: funkcja `handler(ctx, args) -> str` + wpis `Tool(...)` w jednym z modułów
i dopisanie modułu poniżej. Zwrócony tekst jest wypowiadany (albo wraca do modelu, gdy
`speak_directly=False`).
"""

from jarvis.settings import Settings
from jarvis.tools import calendar, discord, system, web
from jarvis.tools.base import Tool, ToolContext, ToolError

__all__ = ["Tool", "ToolContext", "ToolError", "build_tools"]


def build_tools(settings: Settings) -> list[Tool]:
    return [*web.tools(), *discord.tools(settings), *calendar.tools(), *system.tools()]
