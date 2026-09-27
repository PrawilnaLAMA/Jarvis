"""Narzędzia kalendarza: dodawanie, przeglądanie, usuwanie i otwieranie widoku."""

from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import Any

from jarvis.services.calendar_store import (
    WEEKDAYS,
    WEEKDAYS_PL,
    CalendarError,
    describe_day,
    describe_occurrence,
)
from jarvis.tools.base import Tool, ToolContext, ToolError, params

_TIME = {"type": "string", "description": "GG:MM"}
_DATE = {"type": "string", "description": "RRRR-MM-DD"}


def _describe_new_event(event: dict[str, Any], today: date) -> str:
    if event["date"]:
        when = describe_day(date.fromisoformat(event["date"]), today)
    else:
        days = [WEEKDAYS_PL[WEEKDAYS.index(d)] for d in event["days"]]
        when = "co tydzień: " + ", ".join(days)
    text = f"{event['desc']} {when}"
    if event["start"]:
        text += f" o {event['start']}"
    return text


def add_calendar_event(ctx: ToolContext, args: dict[str, Any]) -> str:
    try:
        event = ctx.calendar.add(args)
    except CalendarError as e:
        raise ToolError(f"Nie dodałem wydarzenia. {e}") from e
    return f"Dodałem do kalendarza: {_describe_new_event(event, ctx.clock().date())}."


def list_calendar_events(ctx: ToolContext, args: dict[str, Any]) -> str:
    today = ctx.clock().date()
    try:
        start = date.fromisoformat(args.get("start_date") or today.isoformat())
        end = date.fromisoformat(args.get("end_date") or start.isoformat())
    except ValueError as e:
        raise ToolError("Nie rozumiem podanego zakresu dat.") from e
    if end < start:
        start, end = end, start
    end = min(end, start + timedelta(days=62))
    occurrences = ctx.calendar.occurrences(start, end)
    if not occurrences:
        return f"Brak wydarzeń od {start.isoformat()} do {end.isoformat()}."
    return "Wydarzenia:\n" + "\n".join(f"- {describe_occurrence(o, today)}" for o in occurrences)


def delete_calendar_event(ctx: ToolContext, args: dict[str, Any]) -> str:
    query = str(args.get("query", "")).strip().lower()
    if not query:
        raise ToolError("Nie wiem, które wydarzenie usunąć.")
    events = ctx.calendar.all_events()
    if args.get("date"):
        events = [e for e in events if e["date"] == args["date"]]

    def score(e: dict[str, Any]) -> float:
        desc = e["desc"].lower()
        return 1.0 if query in desc or desc in query else SequenceMatcher(None, query, desc).ratio()

    matches = sorted((e for e in events if score(e) >= 0.6), key=score, reverse=True)
    if not matches:
        raise ToolError("Nie znalazłem takiego wydarzenia w kalendarzu.")
    best = [e for e in matches if score(e) == score(matches[0])]
    if len(best) > 1:
        today = ctx.clock().date()
        options = "; ".join(_describe_new_event(e, today) for e in best[:4])
        return f"Pasuje kilka wydarzeń: {options}. Powiedz, które usunąć."
    ctx.calendar.remove(best[0]["id"])
    return f"Usunąłem z kalendarza: {_describe_new_event(best[0], ctx.clock().date())}."


def open_calendar(ctx: ToolContext, args: dict[str, Any]) -> str:
    ctx.bus.publish("ui.navigate", view="calendar")
    return "Otwieram kalendarz."


def tools() -> list[Tool]:
    return [
        Tool(
            "add_calendar_event",
            "Dodaje wydarzenie: date (jednorazowe) albo days (co tydzień).",
            params(
                {
                    "desc": {"type": "string", "description": "Krótki opis, np. „wizyta u fryzjera”."},
                    "date": _DATE,
                    "days": {"type": "array", "items": {"type": "string", "enum": WEEKDAYS}},
                    "start": _TIME,
                    "end": _TIME,
                    "type": {"type": "string", "description": "Kategoria jednym słowem (spotkanie, praca, nauka…)."},
                },
                ["desc"],
            ),
            add_calendar_event,
        ),
        Tool(
            "list_calendar_events",
            "Zwraca wydarzenia z kalendarza w zakresie dat.",
            params({"start_date": _DATE, "end_date": _DATE}, ["start_date"]),
            list_calendar_events,
            speak_directly=False,
        ),
        Tool(
            "delete_calendar_event",
            "Usuwa wydarzenie z kalendarza po opisie.",
            params({"query": {"type": "string"}, "date": _DATE}, ["query"]),
            delete_calendar_event,
        ),
        Tool("open_calendar", "Pokazuje kalendarz na ekranie.", params(), open_calendar),
    ]
