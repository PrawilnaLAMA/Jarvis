"""Polskie nazwy dni i miesięcy oraz opisy dat w mowie."""

from datetime import date

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAYS_PL = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
MONTHS_GENITIVE_PL = [
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
]
_WEEKDAYS_PL_ON = ["w poniedziałek", "we wtorek", "w środę", "w czwartek", "w piątek", "w sobotę", "w niedzielę"]
EVERY_WEEKDAY_PL = [
    "w każdy poniedziałek", "w każdy wtorek", "w każdą środę", "w każdy czwartek",
    "w każdy piątek", "w każdą sobotę", "w każdą niedzielę",
]


def join_pl(items: list[str]) -> str:
    """„a”, „a i b”, „a, b i c”."""
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " i " + items[-1]


def describe_day(day: date, today: date) -> str:
    """„dziś”, „jutro”, „w poniedziałek” albo „5 listopada”."""
    delta = (day - today).days
    if delta == 0:
        return "dziś"
    if delta == 1:
        return "jutro"
    if delta == -1:
        return "wczoraj"
    if delta == 2:
        return "pojutrze"
    if 2 < delta < 7:
        return _WEEKDAYS_PL_ON[day.weekday()]
    return f"{day.day} {MONTHS_GENITIVE_PL[day.month - 1]}"


# forma po „na” (biernik) i po „do końca” (mianownik), potem 2–4 i 5+
_UNITS = (
    (3600, ("godzinę", "godzina"), "godziny", "godzin"),
    (60, ("minutę", "minuta"), "minuty", "minut"),
    (1, ("sekundę", "sekunda"), "sekundy", "sekund"),
)


def duration_pl(seconds: float, nominative: bool = False) -> str:
    """„2 minuty i 30 sekund”, „1 godzinę, 5 minut i 3 sekundy” – co do sekundy."""
    rest = max(0, round(seconds))
    parts = []
    for size, one, few, many in _UNITS:
        n, rest = divmod(rest, size)
        if n:
            parts.append(f"{n} {plural_pl(n, one[nominative], few, many)}")
    return join_pl(parts) or "0 sekund"


def plural_pl(n: int, one: str, few: str, many: str) -> str:
    if n == 1:
        return one
    return few if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else many
