"""Tekst do czytania na głos: godziny i skróty zamieniane na to, jak się je mówi po polsku.

„Dodałem trening o 18:00” → „Dodałem trening o osiemnastej” (a nie „osiemnasta zero zero”).
"""

import re

# godzina jako liczebnik porządkowy w rodzaju żeńskim: (dopełniacz/miejscownik, biernik, mianownik)
_STEMS = [
    "zer", "pierwsz", "drug", "trzec", "czwart", "piąt", "szóst", "siódm", "ósm", "dziewiąt", "dziesiąt",
    "jedenast", "dwunast", "trzynast", "czternast", "piętnast", "szesnast", "siedemnast", "osiemnast",
    "dziewiętnast", "dwudziest",
]
_ENDINGS = {"gen": "ej", "acc": "ą", "nom": "a"}


def _ordinal(n: int, case: str) -> str:
    def form(stem: str) -> str:
        ending = _ENDINGS[case]
        if stem == "trzec":  # trzeciej / trzecią / trzecia
            ending = {"gen": "iej", "acc": "ią", "nom": "ia"}[case]
        elif stem in ("drug", "zer") and case == "gen":
            ending = "iej" if stem == "drug" else "owej"
        elif stem == "zer":
            ending = {"acc": "ową", "nom": "owa"}[case]
        return stem + ending

    if n <= 20:
        return form(_STEMS[n])
    return f"{form('dwudziest')} {form(_STEMS[n - 20])}"


_TIME = re.compile(r"(?<![\d:])(?:(\w+)\s+)?([01]?\d|2[0-3]):([0-5]\d)(?![\d:])")


def _time(match: re.Match) -> str:
    before, hour, minute = match.group(1), int(match.group(2)), int(match.group(3))
    word = (before or "").lower()
    case = "acc" if word in ("na", "za") else "nom" if word in ("godzina", "jest", "była", "będzie") else "gen"
    spoken = _ordinal(hour, case)
    if minute:
        spoken += f" {minute}"  # minuty syntezator czyta sam („trzydzieści”)
    return f"{before} {spoken}" if before else spoken


_ABBREVIATIONS = [
    (re.compile(r"\bnp\.", re.IGNORECASE), "na przykład"),
    (re.compile(r"\bitd\.", re.IGNORECASE), "i tak dalej"),
    (re.compile(r"\bitp\.", re.IGNORECASE), "i tym podobne"),
    (re.compile(r"\btzn\.", re.IGNORECASE), "to znaczy"),
    (re.compile(r"\btj\.", re.IGNORECASE), "to jest"),
    (re.compile(r"\b(\d{4})\s*r\.(?=\s|$)"), r"\1 roku"),
    (re.compile(r"\bgodz\.\s*", re.IGNORECASE), "godzina "),
]


def speakable(text: str) -> str:
    for pattern, replacement in _ABBREVIATIONS:
        text = pattern.sub(replacement, text)
    return _TIME.sub(_time, text)
