"""Wyszukiwanie w Google i odtwarzanie z YouTube."""

import re
from typing import Any
from urllib.parse import quote_plus

import requests

from jarvis.tools.base import Tool, ToolContext, ToolError, params


def search_web(ctx: ToolContext, args: dict[str, Any]) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("Nie usłyszałem, czego mam szukać.")
    ctx.open_url(f"https://www.google.com/search?q={quote_plus(query)}")
    return f"Otwieram wyniki wyszukiwania: {query}."


def play_youtube(ctx: ToolContext, args: dict[str, Any]) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("Nie usłyszałem, co mam puścić.")
    try:
        html = ctx.http_get(f"https://www.youtube.com/results?search_query={quote_plus(query)}")
    except requests.RequestException as e:
        raise ToolError("Nie udało się połączyć z YouTube.") from e
    ids = re.findall(r'"videoId":"([\w-]{11})"', html) or re.findall(r"watch\?v=([\w-]{11})", html)
    if not ids:
        raise ToolError(f"Nie znalazłem na YouTube: {query}.")
    ctx.open_url(f"https://www.youtube.com/watch?v={ids[0]}")
    return f"Puszczam na YouTube: {query}."


def tools() -> list[Tool]:
    return [
        Tool(
            "search_web",
            "Otwiera w przeglądarce wyniki wyszukiwania Google.",
            params({"query": {"type": "string"}}, ["query"]),
            search_web,
        ),
        Tool(
            "play_youtube",
            "Puszcza piosenkę lub film na YouTube.",
            params({"query": {"type": "string", "description": "Tytuł i/lub wykonawca."}}, ["query"]),
            play_youtube,
        ),
    ]
