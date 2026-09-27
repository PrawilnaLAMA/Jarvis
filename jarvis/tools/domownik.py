"""Narzędzia Domownika – kalendarza Jarvisa: obowiązki domowe, lista zakupów i grafik pracy Natalii."""

import os
import re
from datetime import date
from difflib import SequenceMatcher
from typing import Any

from jarvis.polish import EVERY_WEEKDAY_PL, WEEKDAYS, describe_day, join_pl
from jarvis.services.domownik_client import DomownikError
from jarvis.tools.base import Tool, ToolContext, ToolError, params

USER = "leon"  # „ja” w poleceniach to Leon
REPEAT_TYPES = ["brak", "codziennie", "co_x_dni", "tygodniowo", "miesiecznie"]
CATEGORIES = ["sprzatanie", "kuchnia", "pranie", "zakupy", "rosliny", "zwierzaki", "naprawy", "rachunki", "inne"]
WHO = {"ja": ["leon"], "natalia": ["natalia"], "na_zmiane": ["leon", "natalia"], "wspolne": []}
_WHO_TEXT = {"ja": "dla ciebie", "natalia": "dla Natalii", "na_zmiane": "na zmianę z Natalią", "wspolne": "wspólne"}
_DATE = {"type": "string", "description": "RRRR-MM-DD"}
_ASCII = str.maketrans("ąćęłńóśźż", "acelnoszz")  # Whisper nie zawsze stawia polskie znaki


def _call(fn, *args, **kwargs):
    """Wywołanie API z błędem zrozumiałym dla użytkownika."""
    try:
        return fn(*args, **kwargs)
    except DomownikError as e:
        raise ToolError(str(e)) from e


def _parse_day(value: Any, default: date) -> date:
    if not value:
        return default
    try:
        return date.fromisoformat(str(value))
    except ValueError as e:
        raise ToolError("Nie rozumiem podanej daty.") from e


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", text.lower().translate(_ASCII)) if len(w) > 2]


def _word_score(a: str, b: str) -> float:
    # odmiana zmienia głównie końcówki („mleka” – „mleko”), więc liczy się wspólny początek;
    # samo podobieństwo liter łączyłoby „odkurzanie” z „pranie” przez wspólne „-anie”
    prefix = len(os.path.commonprefix([a, b]))
    if prefix >= 4 or prefix == min(len(a), len(b)):
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    return ratio if ratio > 0.8 else 0.0  # literówki z rozpoznawania mowy


def _score(query: str, title: str) -> float:
    q, t = _words(query), _words(title)
    if not q or not t:
        return 0.0
    if f" {' '.join(q)} " in f" {' '.join(t)} " or f" {' '.join(t)} " in f" {' '.join(q)} ":
        return 1.0
    return sum(max(_word_score(w, x) for x in t) for w in q) / len(q)


def _best_matches(query: str, items: list[dict[str, Any]], threshold: float = 0.6) -> list[dict[str, Any]]:
    scored = [(item, _score(query, item.get("title", ""))) for item in items]
    scored = [(item, s) for item, s in scored if s >= threshold]
    if not scored:
        return []
    top = max(s for _, s in scored)
    return [item for item, s in scored if s == top]


def _person(item: dict[str, Any]) -> str:
    """Czyja kolej: „twoje” dla Leona, imię dla Natalii, „wspólne”. Model mylił „Leon” z „ja”
    i czytał obowiązki Natalii jako „masz”, dlatego dane dla niego są pogrupowane według osoby."""
    assignees = item.get("assignees") or []
    if not assignees:
        return "wspólne"
    if item.get("kto", assignees[0] if len(assignees) == 1 else None) == USER:
        return "twoje"
    return item.get("kto_label") or item.get("assignees_label") or "?"


def _item_text(item: dict[str, Any]) -> str:
    notes = []
    if item.get("na_zmiane"):
        notes.append("na zmianę")
    if item.get("done"):
        notes.append("zrobione")
    if item.get("przeniesiony_z"):
        notes.append(f"przeniesione z {item['przeniesiony_z']}")
    return f"{item['title']} ({', '.join(notes)})" if notes else item["title"]


def _by_person(groups: dict[str, list[str]]) -> str:
    """„twoje: a, b; Natalia: c; wspólne: d” – „twoje” zawsze pierwsze, także gdy puste."""
    groups = {"twoje": groups.pop("twoje", []), **groups}
    return "; ".join(f"{who}: {', '.join(texts) or 'nic'}" for who, texts in groups.items())


# --- obowiązki ---


def house_agenda(ctx: ToolContext, args: dict[str, Any]) -> str:
    today = ctx.clock().date()
    start = _parse_day(args.get("start_date"), today)
    days = max(1, min(14, int(args.get("days") or 1)))
    data = _call(ctx.domownik.agenda, start, days)
    lines = []
    for day in data.get("days", []):
        groups: dict[str, list[str]] = {}
        for item in day.get("items", []):
            groups.setdefault(_person(item), []).append(_item_text(item))
        line = f"{day.get('weekday', '')} {day['date']} – {_by_person(groups) if groups else 'brak obowiązków'}"
        schedule = [g.get("opis", "") for g in (data.get("grafik") or {}).get(day["date"], []) if g.get("opis")]
        if schedule:
            line += f". Grafik: {'; '.join(schedule)}"
        lines.append(line)
    overdue = data.get("overdue") or []
    if overdue and start <= today:
        lines.append(f"Zaległe – {_overdue_summary(overdue)}")
    return "\n".join(lines) or "Brak danych w Domowniku."


def _overdue_summary(overdue: list[dict[str, Any]]) -> str:
    """Zaległości zgrupowane po osobie i nazwie – po kilku tygodniach bywa ich kilkadziesiąt (limit tokenów Groq)."""
    dates: dict[str, dict[str, list[str]]] = {}
    for item in overdue:
        dates.setdefault(_person(item), {}).setdefault(item.get("title", "?"), []).append(str(item.get("date", "?")))
    groups = {
        who: [f"{title} {len(d)}× od {min(d)}" if len(d) > 1 else f"{title} z {d[0]}" for title, d in titles.items()]
        for who, titles in dates.items()
    }
    return _by_person(groups)


def chore_done(ctx: ToolContext, args: dict[str, Any]) -> str:
    today = ctx.clock().date()
    day = _parse_day(args.get("date"), today)
    done = args.get("done", True) is not False
    data = _call(ctx.domownik.agenda, day, 1)
    candidates = [dict(i, date=day.isoformat()) for i in (data.get("days") or [{}])[0].get("items", [])]
    if day == today:  # „zrobiłem pranie” może dotyczyć zaległości z poprzednich dni
        candidates += list(data.get("overdue") or [])
    matches = _best_matches(str(args.get("query", "")), candidates)
    if not matches:
        titles = list(dict.fromkeys(i["title"] for i in candidates))[:5]
        hint = f" Są: {join_pl(titles)}." if titles else ""
        when = describe_day(day, today)
        raise ToolError(f"{when[0].upper()}{when[1:]} nie widzę takiego obowiązku.{hint}")
    # wśród równie pasujących: najpierw te, które trzeba zmienić, a z nich najnowsze (dzisiejsze przed zaległymi)
    matches.sort(key=lambda i: i.get("date", ""), reverse=True)
    matches.sort(key=lambda i: i.get("done") == done)
    item = matches[0]
    _call(ctx.domownik.set_done, item["id"], date.fromisoformat(item["date"]), done)
    return f"{'Odhaczyłem' if done else 'Odznaczyłem'}: {item['title']}."


def _repeat_payload(args: dict[str, Any], start: date) -> tuple[dict[str, Any], str]:
    kind = args.get("repeat") or "brak"
    if kind not in REPEAT_TYPES:
        kind = "brak"
    if kind == "codziennie":
        return {"type": kind}, "codziennie"
    if kind == "co_x_dni":
        interval = max(1, min(365, int(args.get("interval") or 2)))
        return {"type": kind, "interval": interval}, f"co {interval} dni"
    if kind == "tygodniowo":
        names = [d for d in args.get("weekdays") or [] if d in WEEKDAYS] or [WEEKDAYS[start.weekday()]]
        indexes = sorted({WEEKDAYS.index(d) for d in names})
        return {"type": kind, "weekdays": indexes}, join_pl([EVERY_WEEKDAY_PL[i] for i in indexes])
    if kind == "miesiecznie":
        dom = max(1, min(31, int(args.get("day_of_month") or start.day)))
        return {"type": kind, "day_of_month": dom}, f"co miesiąc, {dom}. dnia"
    return {"type": "brak"}, ""


def chore_add(ctx: ToolContext, args: dict[str, Any]) -> str:
    title = str(args.get("title", "")).strip()
    if not title:
        raise ToolError("Nie wiem, co mam dodać.")
    today = ctx.clock().date()
    start = _parse_day(args.get("start_date"), today)
    repeat, repeat_text = _repeat_payload(args, start)
    who = args.get("who") if args.get("who") in WHO else "wspolne"
    payload = {
        "title": title,
        "start_date": start.isoformat(),
        "repeat": repeat,
        "assignees": WHO[who],
        "category": args.get("category") if args.get("category") in CATEGORIES else "inne",
        "notes": str(args.get("notes") or ""),
    }
    _call(ctx.domownik.add_chore, payload)
    when = repeat_text or describe_day(start, today)
    if repeat_text and start > today:
        when += f", od {describe_day(start, today)}"
    return f"Dodałem do kalendarza: {title}, {when}, {_WHO_TEXT[who]}."


def _find_chore(ctx: ToolContext, query: str) -> dict[str, Any]:
    chores = [c for c in _call(ctx.domownik.chores) if not c.get("archived")]
    matches = _best_matches(query, chores)
    if not matches:
        raise ToolError("Nie znalazłem takiego obowiązku w kalendarzu.")
    if len(matches) > 1:
        options = join_pl([f"{c['title']} ({c.get('repeat_label', '')})" for c in matches[:4]])
        raise ToolError(f"Pasuje kilka obowiązków: {options}. Powiedz, o który chodzi.")
    return matches[0]


def chore_delete(ctx: ToolContext, args: dict[str, Any]) -> str:
    chore = _find_chore(ctx, str(args.get("query", "")))
    _call(ctx.domownik.delete_chore, chore["id"])
    return f"Usunąłem z kalendarza: {chore['title']}."


def chore_info(ctx: ToolContext, args: dict[str, Any]) -> str:
    c = _find_chore(ctx, str(args.get("query", "")))
    who = c.get("assignees_label") or "wspólne"
    if c.get("na_zmiane"):
        who += " (na zmianę)"
    return (f"{c['title']}: {c.get('repeat_label', '')}, {who}, następny raz {c.get('next_date') or 'brak'}, "
            f"zrobione {c.get('done_count', 0)} razy.")


def open_calendar(ctx: ToolContext, args: dict[str, Any]) -> str:
    ctx.bus.publish("ui.navigate", view="calendar")
    return "Otwieram kalendarz."


# --- zakupy ---


def shopping_list(ctx: ToolContext, args: dict[str, Any]) -> str:
    items = _call(ctx.domownik.shopping)

    def text(i: dict[str, Any]) -> str:
        return f"{i['title']} ({i['qty']})" if i.get("qty") else i["title"]

    todo = [text(i) for i in items if not i.get("done")]
    bought = [text(i) for i in items if i.get("done")]
    if not items:
        return "Lista zakupów jest pusta."
    out = f"Do kupienia: {', '.join(todo)}." if todo else "Wszystko kupione."
    return out + (f" Kupione: {', '.join(bought)}." if bought else "")


def shopping_update(ctx: ToolContext, args: dict[str, Any]) -> str:
    action = args.get("action")
    entries = [e for e in args.get("items") or [] if isinstance(e, dict) and str(e.get("title", "")).strip()]
    if action == "clear_bought":
        removed = _call(ctx.domownik.clear_bought)
        return f"Usunąłem z listy kupione rzeczy ({removed})." if removed else "Nie było kupionych rzeczy do usunięcia."
    if not entries:
        raise ToolError("Nie usłyszałem, o jakie rzeczy chodzi.")
    if action == "add":
        for e in entries:
            _call(ctx.domownik.add_item, str(e["title"]).strip(), str(e.get("qty") or "").strip())
        return f"Dodałem do zakupów: {join_pl([str(e['title']).strip() for e in entries])}."

    items = _call(ctx.domownik.shopping)
    done_titles, missing = [], []
    for e in entries:
        pool = [i for i in items if not i.get("done")] if action == "bought" else items
        matches = _best_matches(str(e["title"]), pool)
        if not matches:
            missing.append(str(e["title"]))
            continue
        item = matches[0]
        if action == "bought":
            _call(ctx.domownik.update_item, item["id"], {"done": True})
        else:
            _call(ctx.domownik.delete_item, item["id"])
        done_titles.append(item["title"])
    parts = []
    if done_titles:
        verb = "Odhaczyłem jako kupione" if action == "bought" else "Usunąłem z listy"
        parts.append(f"{verb}: {join_pl(done_titles)}.")
    if missing:
        parts.append(f"Nie ma na liście: {join_pl(missing)}.")
    return " ".join(parts)


def tools() -> list[Tool]:
    return [
        Tool(
            "house_agenda",
            "Kalendarz domu (Domownik): obowiązki kto/co/zrobione, zaległości i grafik pracy Natalii na dni.",
            params({"start_date": _DATE, "days": {"type": "integer", "description": "1–14"}}),
            house_agenda,
            speak_directly=False,
        ),
        Tool(
            "chore_done",
            "Odhacza obowiązek jako zrobiony (albo cofa odhaczenie: done=false).",
            params({"query": {"type": "string"}, "date": _DATE, "done": {"type": "boolean"}}, ["query"]),
            chore_done,
        ),
        Tool(
            "chore_add",
            "Dodaje obowiązek/wydarzenie do kalendarza.",
            params(
                {
                    "title": {"type": "string", "description": "z godziną, jeśli padła, np. „Trening 18:00”"},
                    "start_date": _DATE,
                    "repeat": {"type": "string", "enum": REPEAT_TYPES},
                    "interval": {"type": "integer", "description": "dla co_x_dni"},
                    "weekdays": {"type": "array", "items": {"type": "string", "enum": WEEKDAYS}},
                    "day_of_month": {"type": "integer"},
                    "who": {"type": "string", "enum": list(WHO)},
                    "category": {"type": "string", "enum": CATEGORIES},
                },
                ["title"],
            ),
            chore_add,
        ),
        Tool("chore_delete", "Usuwa obowiązek z kalendarza.", params({"query": {"type": "string"}}, ["query"]),
             chore_delete),
        Tool(
            "chore_info",
            "Szczegóły obowiązku: jak często, czyj, kiedy następny raz.",
            params({"query": {"type": "string"}}, ["query"]),
            chore_info,
            speak_directly=False,
        ),
        Tool("open_calendar", "Pokazuje kalendarz na ekranie.", params(), open_calendar),
        Tool("shopping_list", "Czyta listę zakupów.", params(), shopping_list, speak_directly=False),
        Tool(
            "shopping_update",
            "Zmienia listę zakupów: add – dodaj, bought – kupione, remove – usuń, clear_bought – wyczyść kupione.",
            params(
                {
                    "action": {"type": "string", "enum": ["add", "bought", "remove", "clear_bought"]},
                    "items": {
                        "type": "array",
                        "items": params({"title": {"type": "string"}, "qty": {"type": "string"}}, ["title"]),
                    },
                },
                ["action"],
            ),
            shopping_update,
        ),
    ]
