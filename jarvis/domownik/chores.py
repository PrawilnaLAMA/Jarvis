"""Logika obowiazkow: kategorie, powtarzalnosc, plan dnia, statystyki."""

from __future__ import annotations

import calendar
import re
import uuid
from datetime import date, datetime, timedelta

# --------------------------------------------------------------- slowniki --

WEEKDAYS = [
    "poniedziałek",
    "wtorek",
    "środa",
    "czwartek",
    "piątek",
    "sobota",
    "niedziela",
]
WEEKDAYS_SHORT = ["pon", "wt", "śr", "czw", "pt", "sob", "ndz"]
MONTHS_GEN = [
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
]
MONTHS_NOM = [
    "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
    "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
]

CATEGORIES = {
    "sprzatanie": {"label": "Sprzątanie", "icon": "🧹", "color": "#7fa8d6"},
    "kuchnia": {"label": "Kuchnia", "icon": "🍽️", "color": "#e59b6a"},
    "pranie": {"label": "Pranie", "icon": "🧺", "color": "#9d8ec7"},
    "zakupy": {"label": "Zakupy", "icon": "🛒", "color": "#6fb08a"},
    "rosliny": {"label": "Rośliny", "icon": "🪴", "color": "#7fbb64"},
    "zwierzaki": {"label": "Zwierzaki", "icon": "🐶", "color": "#d99a3f"},
    "naprawy": {"label": "Naprawy", "icon": "🔧", "color": "#8d99a6"},
    "rachunki": {"label": "Rachunki", "icon": "💸", "color": "#d4738a"},
    "inne": {"label": "Inne", "icon": "📌", "color": "#a89484"},
}
DEFAULT_CATEGORY = "inne"

PRIORITIES = {
    "niski": {"label": "Niski", "rank": 2},
    "normalny": {"label": "Normalny", "rank": 1},
    "wysoki": {"label": "Ważne", "rank": 0},
}
DEFAULT_PRIORITY = "normalny"

# Osoby domownikow - kolor decyduje o akcencie obowiazku w calym UI
# (nadpisuje kolor kategorii, gdy obowiazek jest komus przypisany).
# KOLEJNOSC MA ZNACZENIE: obowiazek z dwiema osobami chodzi na zmiane wlasnie
# w tej kolejnosci, wiec pierwsza ture bierze Leon.
PEOPLE = {
    "leon": {"label": "Leon", "initial": "L", "color": "#5b8ee0"},
    "natalia": {"label": "Natalia", "initial": "N", "color": "#e0699e"},
}

REPEAT_TYPES = ("brak", "codziennie", "co_x_dni", "tygodniowo", "miesiecznie")


class ValidationError(ValueError):
    """Blad danych wejsciowych - zamieniany na HTTP 400."""


# ------------------------------------------------------------ formatowanie --


def parse_date(value, field: str = "data") -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValidationError(f"Nieprawidłowa {field}: {value!r} (oczekiwano RRRR-MM-DD).") from None


def parse_time(value) -> str | None:
    """Godzina 'GG:MM' albo None (obowiazek bez godziny). Przyjmuje tez '15', '9:05', '15.30'."""
    if value is None or str(value).strip() == "":
        return None
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?(?::\d{2})?", str(value).strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2) or 0) > 59:
        raise ValidationError(f"Nieprawidłowa godzina: {value!r} (oczekiwano GG:MM).")
    return f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}"


MAX_REMIND_MINUTES = 24 * 60


def parse_remind(value, time: str | None) -> int | None:
    """Ile minut przed godzina przypomniec: None = bez przypomnienia, 0 = o czasie, max doba."""
    if value is None or str(value).strip() == "":
        return None
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        raise ValidationError("Przypomnienie musi być liczbą minut.") from None
    if not 0 <= minutes <= MAX_REMIND_MINUTES:
        raise ValidationError("Przypomnienie: od 0 minut do doby wcześniej.")
    if not time:
        raise ValidationError("Przypomnienie wymaga godziny.")
    return minutes


def remind_label(minutes: int | None) -> str:
    """'' / 'o czasie' / '15 min przed' / '2 h przed' / 'dzień przed'."""
    if minutes is None:
        return ""
    if minutes == 0:
        return "o czasie"
    if minutes == MAX_REMIND_MINUTES:
        return "dzień przed"
    if minutes % 60 == 0:
        return f"{minutes // 60} h przed"
    return f"{minutes} min przed"


def format_long(day: date) -> str:
    return f"{day.day} {MONTHS_GEN[day.month - 1]} {day.year}"


def day_label(day: date, today: date) -> str:
    delta = (day - today).days
    if delta == 0:
        return "dzisiaj"
    if delta == 1:
        return "jutro"
    if delta == 2:
        return "pojutrze"
    if delta == -1:
        return "wczoraj"
    return WEEKDAYS[day.weekday()]


def repeat_label(chore: dict) -> str:
    rep = chore.get("repeat") or {}
    kind = rep.get("type", "brak")
    if kind == "codziennie":
        return "codziennie"
    if kind == "co_x_dni":
        n = int(rep.get("interval", 2))
        if n == 1:
            return "codziennie"
        if n == 7:
            return "co tydzień"
        return f"co {n} dni"
    if kind == "tygodniowo":
        days = rep.get("weekdays") or []
        if len(days) == 7:
            return "codziennie"
        names = ", ".join(WEEKDAYS_SHORT[d] for d in sorted(days))
        return f"co tydzień: {names}" if names else "co tydzień"
    if kind == "miesiecznie":
        return f"{rep.get('day_of_month', 1)}. dnia miesiąca"
    return "jednorazowo"


# ------------------------------------------------------------- walidacja ----


def normalize_chore(payload: dict, existing: dict | None = None) -> dict:
    """Sprawdza i porzadkuje dane obowiazku przychodzace z formularza."""
    if not isinstance(payload, dict):
        raise ValidationError("Oczekiwano obiektu JSON.")

    base = dict(existing) if existing else {}

    title = str(payload.get("title", base.get("title", ""))).strip()
    if not title:
        raise ValidationError("Nazwa obowiązku nie może być pusta.")
    if len(title) > 120:
        raise ValidationError("Nazwa obowiązku jest za długa (max 120 znaków).")

    category = str(payload.get("category", base.get("category", DEFAULT_CATEGORY)))
    if category not in CATEGORIES:
        category = DEFAULT_CATEGORY

    priority = str(payload.get("priority", base.get("priority", DEFAULT_PRIORITY)))
    if priority not in PRIORITIES:
        priority = DEFAULT_PRIORITY

    # "assignee" (jedna osoba) przyjmujemy dalej, bo tak wygladaly stare pliki
    # i starsze wersje aplikacji - zapisujemy juz zawsze jako liste
    if "assignees" in payload:
        assignees = _normalize_assignees(payload.get("assignees"))
    elif "assignee" in payload:
        assignees = _normalize_assignees(payload.get("assignee"))
    else:
        assignees = _normalize_assignees(base.get("assignees", base.get("assignee")))

    icon = str(payload.get("icon") or base.get("icon") or CATEGORIES[category]["icon"])[:4]

    start = parse_date(
        payload.get("start_date", base.get("start_date", date.today().isoformat())),
        "data startu",
    )

    end_raw = payload.get("end_date", base.get("end_date"))
    end = parse_date(end_raw, "data końca") if end_raw else None
    if end and end < start:
        raise ValidationError("Data końca nie może być wcześniejsza niż data startu.")

    chore = {
        "id": base.get("id") or uuid.uuid4().hex[:10],
        "title": title,
        "notes": str(payload.get("notes", base.get("notes", "")) or "").strip()[:500],
        "category": category,
        "icon": icon,
        "priority": priority,
        "assignees": assignees,
        "start_date": start.isoformat(),
        "end_date": end.isoformat() if end else None,
        "time": parse_time(payload.get("time", base.get("time"))),
        "remind_before": None,
        "repeat": _normalize_repeat(payload.get("repeat", base.get("repeat")), start),
        "archived": bool(payload.get("archived", base.get("archived", False))),
        "created_at": base.get("created_at") or datetime.now().isoformat(timespec="seconds"),
    }
    chore["remind_before"] = parse_remind(payload.get("remind_before", base.get("remind_before")), chore["time"])
    return chore


def _normalize_assignees(raw) -> list[str]:
    """Kto robi obowiazek: pusto = wspolne, jedna osoba = jej, dwie = na zmiane.

    Wynik zawsze w kolejnosci z PEOPLE, bo od niej zalezy, kto zaczyna kolejke -
    inaczej ten sam obowiazek zmienialby wlasciciela po kazdym zapisie formularza."""
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw] if raw else []
    if not isinstance(raw, (list, tuple, set)):
        raise ValidationError("Lista osób musi być listą.")
    wybrane = {str(osoba) for osoba in raw if osoba}
    nieznane = wybrane - set(PEOPLE)
    if nieznane:
        raise ValidationError(f"Nie znam domownika: {', '.join(sorted(nieznane))}.")
    return [klucz for klucz in PEOPLE if klucz in wybrane]


def _normalize_repeat(repeat, start: date) -> dict:
    if not isinstance(repeat, dict):
        repeat = {}
    kind = str(repeat.get("type", "brak"))
    if kind not in REPEAT_TYPES:
        raise ValidationError(f"Nieznany typ powtarzania: {kind!r}.")

    out: dict = {"type": kind}

    if kind == "co_x_dni":
        try:
            interval = int(repeat.get("interval", 2))
        except (TypeError, ValueError):
            raise ValidationError("Odstęp w dniach musi być liczbą.") from None
        if not 1 <= interval <= 365:
            raise ValidationError("Odstęp musi mieścić się w zakresie 1-365 dni.")
        out["interval"] = interval

    elif kind == "tygodniowo":
        # brak klucza -> bierzemy dzien tygodnia z daty startu,
        # ale jawnie pusta lista to blad formularza
        raw = repeat.get("weekdays")
        if raw is None:
            raw = [start.weekday()]
        try:
            days = sorted({int(d) for d in raw})
        except (TypeError, ValueError):
            raise ValidationError("Dni tygodnia muszą być liczbami 0-6.") from None
        if not days or any(d < 0 or d > 6 for d in days):
            raise ValidationError("Wybierz przynajmniej jeden poprawny dzień tygodnia.")
        out["weekdays"] = days

    elif kind == "miesiecznie":
        try:
            dom = int(repeat.get("day_of_month", start.day))
        except (TypeError, ValueError):
            raise ValidationError("Dzień miesiąca musi być liczbą.") from None
        if not 1 <= dom <= 31:
            raise ValidationError("Dzień miesiąca musi mieścić się w zakresie 1-31.")
        out["day_of_month"] = dom

    return out


# ---------------------------------------------------------- powtarzalnosc --


def occurs_on(chore: dict, day: date) -> bool:
    """Czy dany obowiazek wypada w tym dniu?"""
    if chore.get("archived"):
        return False

    start = parse_date(chore["start_date"])
    if day < start:
        return False

    end = chore.get("end_date")
    if end and day > parse_date(end):
        return False

    rep = chore.get("repeat") or {}
    kind = rep.get("type", "brak")

    if kind == "brak":
        return day == start
    if kind == "codziennie":
        return True
    if kind == "co_x_dni":
        interval = max(1, int(rep.get("interval", 1)))
        return (day - start).days % interval == 0
    if kind == "tygodniowo":
        return day.weekday() in (rep.get("weekdays") or [start.weekday()])
    if kind == "miesiecznie":
        wanted = int(rep.get("day_of_month", start.day))
        last_day = calendar.monthrange(day.year, day.month)[1]
        # 31. dnia miesiaca -> w lutym wypada ostatniego dnia
        return day.day == min(wanted, last_day)
    return False


def is_done(state: dict, chore_id: str, day: date) -> bool:
    return day.isoformat() in state.get("completions", {}).get(chore_id, [])


def set_done(state: dict, chore_id: str, day: date, done: bool) -> bool:
    completions = state.setdefault("completions", {})
    entries = set(completions.get(chore_id, []))
    key = day.isoformat()
    if done:
        entries.add(key)
    else:
        entries.discard(key)
    if entries:
        completions[chore_id] = sorted(entries)
    else:
        completions.pop(chore_id, None)
    return done


def find_chore(state: dict, chore_id: str) -> dict | None:
    return next((c for c in state.get("chores", []) if c["id"] == chore_id), None)


# ------------------------------------------------------------ widok danych --


def assignees_of(chore: dict) -> list[str]:
    """Osoby przypisane do obowiazku - takze ze starego pola 'assignee'."""
    raw = chore.get("assignees")
    if raw is None:
        raw = chore.get("assignee")
    if isinstance(raw, str):
        raw = [raw] if raw else []
    return [klucz for klucz in PEOPLE if klucz in set(raw or ())]


def display_color(chore: dict, kto: str = "") -> str:
    """Kolor akcentu: osoba ma pierwszenstwo przed kategoria.

    'kto' to osoba, ktora naprawde robi obowiazek tego dnia (z planera). Bez niej
    kolor osoby dajemy tylko przy jednym wlascicielu - obowiazek chodzacy na zmiane
    nie ma stalego koloru, wiec na liscie obowiazkow swieci kolorem kategorii."""
    person = PEOPLE.get(kto or "")
    if person is None:
        przypisane = assignees_of(chore)
        person = PEOPLE[przypisane[0]] if len(przypisane) == 1 else None
    if person:
        return person["color"]
    cat = CATEGORIES.get(chore.get("category", DEFAULT_CATEGORY), CATEGORIES[DEFAULT_CATEGORY])
    return cat["color"]


def assignees_label(assignees: list[str]) -> str:
    """'' / 'Natalia' / 'Leon i Natalia na zmianę'."""
    nazwy = [PEOPLE[a]["label"] for a in assignees if a in PEOPLE]
    if not nazwy:
        return ""
    if len(nazwy) == 1:
        return nazwy[0]
    return " i ".join(nazwy) + " na zmianę"


def chore_view(chore: dict, state: dict, day: date, decyzja: dict | None = None) -> dict:
    """Obowiazek przygotowany dla frontendu, w kontekscie konkretnego dnia.

    'decyzja' pochodzi z planer.rozklad() i mowi, kto ten obowiazek robi tego dnia
    oraz czy zostal przeniesiony. Bez niej widok wyglada tak jak przed planerem."""
    cat = CATEGORIES.get(chore.get("category", DEFAULT_CATEGORY), CATEGORIES[DEFAULT_CATEGORY])
    decyzja = decyzja or {}
    przypisane = assignees_of(chore)
    kto = decyzja.get("kto") or (przypisane[0] if len(przypisane) == 1 else "")
    person = PEOPLE.get(kto)
    return {
        "id": chore["id"],
        "title": chore["title"],
        "notes": chore.get("notes", ""),
        "icon": chore.get("icon") or cat["icon"],
        "category": chore.get("category", DEFAULT_CATEGORY),
        "category_label": cat["label"],
        "color": display_color(chore, kto),
        "assignees": przypisane,
        "assignees_label": assignees_label(przypisane),
        "na_zmiane": len(przypisane) > 1,
        "kto": kto,
        "kto_label": person["label"] if person else "",
        "kto_initial": person["initial"] if person else "",
        "powod": decyzja.get("powod", ""),
        "przeniesiony_z": decyzja.get("z_dnia"),
        "priority": chore.get("priority", DEFAULT_PRIORITY),
        "repeat_label": repeat_label(chore),
        "repeat_type": (chore.get("repeat") or {}).get("type", "brak"),
        "date": day.isoformat(),
        "time": chore.get("time") or "",
        "remind_before": chore.get("remind_before"),
        "remind_label": remind_label(chore.get("remind_before")),
        "done": is_done(state, chore["id"], day),
    }


def _sort_key(item: dict) -> tuple:
    """Najpierw wpisy z godzina, chronologicznie (takze zrobione - to plan dnia),
    potem obowiazki bez godziny: niezrobione, waznosc, nazwa."""
    time = item.get("time") or ""
    return (
        not time,
        time,
        item["done"],
        PRIORITIES.get(item["priority"], PRIORITIES[DEFAULT_PRIORITY])["rank"],
        item["title"].lower(),
    )


def items_for_day(state: dict, day: date, plan: dict | None = None) -> list[dict]:
    """Obowiazki na dany dzien.

    Z planem (planer.rozklad) bierzemy jego rozstrzygniecia: kto robi i co zostalo
    przeniesione. Bez planu - albo dla dnia spoza jego zakresu - liczy sie sama
    regula powtarzania, dokladnie jak przed planerem."""
    decyzje = _decyzje_planu(plan, day)
    if decyzje is None:
        items = [chore_view(c, state, day) for c in state.get("chores", []) if occurs_on(c, day)]
    else:
        items = [
            chore_view(chore, state, day, decyzje[chore["id"]])
            for chore in state.get("chores", [])
            if chore["id"] in decyzje
        ]
    return sorted(items, key=_sort_key)


def _decyzje_planu(plan: dict | None, day: date) -> dict | None:
    if not plan:
        return None
    if not (plan["od"] <= day.isoformat() <= plan["do"]):
        return None  # dzien spoza okna planu - lepiej surowa regula niz pustka
    return plan["dni"].get(day.isoformat(), {})


def day_summary(state: dict, day: date, today: date, plan: dict | None = None) -> dict:
    items = items_for_day(state, day, plan)
    done = sum(1 for i in items if i["done"])
    return {
        "date": day.isoformat(),
        "label": day_label(day, today),
        "weekday": WEEKDAYS[day.weekday()],
        "weekday_short": WEEKDAYS_SHORT[day.weekday()],
        "day": day.day,
        "month_name": MONTHS_GEN[day.month - 1],
        "long": format_long(day),
        "is_today": day == today,
        "is_weekend": day.weekday() >= 5,
        "items": items,
        "done": done,
        "total": len(items),
    }


def overdue_items(state: dict, today: date, days_back: int = 21, plan: dict | None = None) -> list[dict]:
    """Nieodhaczone obowiazki z ostatnich tygodni (bez dnia dzisiejszego)."""
    out: list[dict] = []
    for offset in range(days_back, 0, -1):
        day = today - timedelta(days=offset)
        for item in items_for_day(state, day, plan):
            if not item["done"]:
                item["days_late"] = offset
                out.append(item)
    return out


def agenda(state: dict, start: date, days: int, today: date, plan: dict | None = None) -> dict:
    return {
        "today": today.isoformat(),
        "today_long": f"{WEEKDAYS[today.weekday()]}, {format_long(today)}",
        "days": [day_summary(state, start + timedelta(days=i), today, plan) for i in range(days)],
        "overdue": overdue_items(state, today, plan=plan),
    }


def month_range(year: int, month: int) -> tuple[date, date]:
    """Pierwszy i ostatni dzien siatki miesiaca (6 x 7 od poniedzialku)."""
    first = date(year, month, 1)
    grid_start = first - timedelta(days=first.weekday())
    return grid_start, grid_start + timedelta(days=41)


def month_grid(state: dict, year: int, month: int, today: date, plan: dict | None = None) -> dict:
    """Siatka miesiaca 6x7 (od poniedzialku) z obowiazkami w kazdym dniu."""
    first = date(year, month, 1)
    grid_start, _ = month_range(year, month)
    cells = []
    total = done_total = 0
    for i in range(42):
        day = grid_start + timedelta(days=i)
        summary = day_summary(state, day, today, plan)
        summary["in_month"] = day.month == month and day.year == year
        cells.append(summary)
        if summary["in_month"]:
            total += summary["total"]
            done_total += summary["done"]

    prev_month = first - timedelta(days=1)
    next_month = date(year, month, calendar.monthrange(year, month)[1]) + timedelta(days=1)

    return {
        "year": year,
        "month": month,
        "month_name": MONTHS_NOM[month - 1],
        "weekday_names": WEEKDAYS_SHORT,
        "cells": cells,
        "total": total,
        "done": done_total,
        "prev": {"year": prev_month.year, "month": prev_month.month},
        "next": {"year": next_month.year, "month": next_month.month},
        "today": today.isoformat(),
    }


def stats(state: dict, today: date) -> dict:
    """Pasek postepu na dzis, seria dni bez zaleglosci, liczba obowiazkow."""
    today_items = items_for_day(state, today)
    done_today = sum(1 for i in today_items if i["done"])

    streak = 0
    for offset in range(1, 366):
        day = today - timedelta(days=offset)
        items = items_for_day(state, day)
        if not items:
            continue  # dzien bez obowiazkow nie przerywa serii
        if all(i["done"] for i in items):
            streak += 1
        else:
            break

    week_done = 0
    for offset in range(7):
        day = today - timedelta(days=offset)
        week_done += sum(1 for i in items_for_day(state, day) if i["done"])

    active = [c for c in state.get("chores", []) if not c.get("archived")]
    return {
        "today_done": done_today,
        "today_total": len(today_items),
        "percent": round(done_today / len(today_items) * 100) if today_items else 0,
        "streak": streak,
        "week_done": week_done,
        "active_chores": len(active),
        "overdue": len(overdue_items(state, today)),
    }


# ----------------------------------------------------------- dane startowe --


def seed_examples(today: date) -> list[dict]:
    """Kilka przykladowych obowiazkow przy pierwszym uruchomieniu."""
    samples = [
        ("Wynieść śmieci", "sprzatanie", {"type": "co_x_dni", "interval": 2}, "normalny", ""),
        ("Pozmywać naczynia", "kuchnia", {"type": "codziennie"}, "normalny", ""),
        ("Odkurzyć mieszkanie", "sprzatanie", {"type": "tygodniowo", "weekdays": [5]}, "normalny", ""),
        ("Nastawić pranie", "pranie", {"type": "co_x_dni", "interval": 3}, "normalny", ""),
        ("Podlać kwiatki", "rosliny", {"type": "co_x_dni", "interval": 4}, "niski",
         "Te na parapecie lubią mniej wody."),
        ("Duże zakupy", "zakupy", {"type": "tygodniowo", "weekdays": [5]}, "wysoki", ""),
        ("Zapłacić rachunki", "rachunki", {"type": "miesiecznie", "day_of_month": 10}, "wysoki", ""),
        ("Wyprowadzić psa na dłuższy spacer", "zwierzaki", {"type": "codziennie"}, "wysoki", ""),
    ]
    return [
        normalize_chore(
            {
                "title": title,
                "category": category,
                "repeat": repeat,
                "priority": priority,
                "notes": notes,
                "start_date": today.isoformat(),
            }
        )
        for title, category, repeat, priority, notes in samples
    ]
