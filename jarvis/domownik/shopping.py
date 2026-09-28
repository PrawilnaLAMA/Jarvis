"""Lista zakupow: kategorie, zgadywanie kategorii z nazwy, porzadkowanie.

Osobno od chores.py, bo to inna dziedzina - obowiazek ma powtarzalnosc i kalendarz,
a rzecz na liscie zakupow ma tylko dwa stany: do kupienia albo kupione.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from .chores import ValidationError  # wspolny wyjatek -> HTTP 400 w app.py

# Kolejnosc ma znaczenie: lista grupuje sie wlasnie tak, mniej wiecej po kolei
# jak idzie sie przez sklep. "Inne" celowo na koncu.
CATEGORIES = {
    "warzywa": {"label": "Warzywa i owoce", "icon": "🥦", "color": "#7fbb64"},
    "pieczywo": {"label": "Pieczywo", "icon": "🥖", "color": "#e59b6a"},
    "nabial": {"label": "Nabiał", "icon": "🥛", "color": "#7fa8d6"},
    "mieso": {"label": "Mięso i ryby", "icon": "🍗", "color": "#d4738a"},
    "mrozone": {"label": "Mrożonki", "icon": "🧊", "color": "#8fc7d6"},
    "spizarnia": {"label": "Sypkie i konserwy", "icon": "🥫", "color": "#c9a227"},
    "napoje": {"label": "Napoje", "icon": "🧃", "color": "#6fb08a"},
    "chemia": {"label": "Chemia i higiena", "icon": "🧴", "color": "#9d8ec7"},
    "inne": {"label": "Inne", "icon": "🛒", "color": "#a89484"},
}
DEFAULT_CATEGORY = "inne"

# Slowa kluczowe pisane BEZ polskich znakow - nazwy wpisywane przez uzytkownika
# tez sprowadzamy do tej postaci, zeby "maslo" i "masło" trafialy tak samo.
KEYWORDS = {
    "warzywa": [
        "pomidor", "ogorek", "ogork", "ziemniak", "marchew", "cebul", "czosnek", "salat",
        "papryk", "brokul", "kalafior", "kapust", "por", "burak", "dyni", "cukini",
        "pieczark", "szpinak", "rzodkiew", "seler", "pietrusz", "koperek", "szczypior",
        "jablk", "banan", "cytryn", "pomarancz", "mandarynk", "truskaw", "malin",
        "borowk", "winogron", "gruszk", "arbuz", "melon", "brzoskwini", "sliwk",
        "awokado", "kiwi", "ananas", "mango", "limonk", "warzyw", "owoc", "sadzonk",
    ],
    "pieczywo": [
        "chleb", "bulk", "bagietk", "rogal", "croissant", "tortill", "pita", "chalk",
        "drozdzowk", "pieczywo", "bulecz", "grzank", "sucharki",
    ],
    "nabial": [
        "mleko", "mleka", "ser", "serek", "twarog", "jogurt", "smietan",
        "maslo", "kefir", "maslank", "jajk", "jaja", "jajec", "mozzarell", "feta",
        "mascarpone", "parmezan", "budyn", "nabial", "smietank", "margaryn",
    ],
    "mieso": [
        "mieso", "kurczak", "kurczaka", "indyk", "wolowin", "wieprzow", "schab",
        "karkow", "mielone", "kielbas", "szynk", "boczek", "parowk", "ryb",
        "losos", "tunczyk", "dorsz", "krewetk", "pasztet", "salami", "kabanos",
        "filet", "udk", "skrzydelk", "burger",
    ],
    "mrozone": ["mrozon", "mrozonk", "lody", "frytki", "pierogi"],
    "spizarnia": [
        "ryz", "makaron", "kasz", "platki", "cukier", "sol", "pieprz", "przypraw",
        "olej", "oliw", "ocet", "ketchup", "majonez", "musztard", "dzem", "miod",
        "orzech", "czekolad", "ciastk", "chipsy", "konserw", "groszek", "kukurydz",
        "passat", "koncentrat", "bulion", "maka", "drozdze", "kakao", "herbatnik",
        "musli", "kawa", "sos", "fasol", "soczewic", "ciecierzyc", "tunczyk w",
    ],
    "napoje": [
        "woda", "wody", "sok", "cola", "pepsi", "piwo", "wino", "herbat", "napoj",
        "lemoniad", "tonik", "energetyk", "syrop", "kompot", "mineraln", "sprite",
        "fant", "smoothie",
    ],
    "chemia": [
        "papier toaletowy", "recznik papierowy", "reczniki papierowe", "plyn", "proszek",
        "mydl", "szampon", "pasta do zebow", "szczoteczk", "chusteczk", "worki na smieci",
        "worki", "gabk", "odplamiacz", "dezodorant", "zel", "balsam", "podpask",
        "tampon", "pielusz", "pieluch", "chemia", "wybielacz", "kapsulk", "zmiekczacz",
        "serwetk", "folia", "papier do", "nici dentystyczne", "krem", "maszynk",
    ],
}

_TRANS = str.maketrans("ąćęłńóśźż", "acelnoszz")

# Dluzsze slowa sprawdzamy pierwsze, zeby "serwetki" nie wpadly do nabialu przez "ser",
# a "papier toaletowy" nie skonczyl jako zwykly "papier".
_INDEX = sorted(
    ((word, category) for category, words in KEYWORDS.items() for word in words),
    key=lambda pair: -len(pair[0]),
)


def fold(text: str) -> str:
    """Male litery bez polskich znakow - do porownywania nazw."""
    return str(text).lower().translate(_TRANS)


def _match(words: list[str]) -> str | None:
    """Pierwsze pasujace slowo kluczowe (dluzsze maja pierwszenstwo)."""
    for keyword, category in _INDEX:
        if " " in keyword:
            continue
        if any(word.startswith(keyword) for word in words):
            return category
    return None


def guess_category(title: str) -> str:
    """Zgaduje dzial sklepu po nazwie. Uzytkownik moze poprawic jednym klikniecim."""
    folded = fold(title)
    words = folded.split()
    if not words:
        return DEFAULT_CATEGORY

    # 1. nazwy zlozone sa najbardziej konkretne: "papier toaletowy" to nie zwykly papier
    for keyword, category in _INDEX:
        if " " in keyword and keyword in folded:
            return category

    # 2. pierwszy wyraz niesie najwiecej znaczenia: "sok pomaranczowy" to napoj, nie owoc,
    #    a "ser plesniowy" to nabial. Dopiero potem szukamy w reszcie nazwy, zeby zlapac
    #    takie przypadki jak "2 kg ziemniakow".
    return _match(words[:1]) or _match(words) or DEFAULT_CATEGORY


def normalize_item(payload: dict, existing: dict | None = None) -> dict:
    """Sprawdza i porzadkuje dane rzeczy z listy zakupow."""
    if not isinstance(payload, dict):
        raise ValidationError("Oczekiwano obiektu JSON.")

    base = dict(existing) if existing else {}

    title = str(payload.get("title", base.get("title", ""))).strip()
    if not title:
        raise ValidationError("Nazwa rzeczy nie może być pusta.")
    if len(title) > 80:
        raise ValidationError("Nazwa jest za długa (max 80 znaków).")

    qty = str(payload.get("qty", base.get("qty", "")) or "").strip()[:24]

    category = payload.get("category", base.get("category"))
    if category not in CATEGORIES:
        # brak kategorii (nowa rzecz) -> zgadujemy z nazwy
        category = guess_category(title)

    done = bool(payload.get("done", base.get("done", False)))
    done_at = base.get("done_at")
    if done and not done_at:
        done_at = datetime.now().isoformat(timespec="seconds")
    elif not done:
        done_at = None

    return {
        "id": base.get("id") or uuid.uuid4().hex[:10],
        "title": title,
        "qty": qty,
        "category": category,
        "done": done,
        "created_at": base.get("created_at") or datetime.now().isoformat(timespec="seconds"),
        "done_at": done_at,
    }


def item_view(item: dict) -> dict:
    """Rzecz przygotowana dla frontendu."""
    cat = CATEGORIES.get(item.get("category", DEFAULT_CATEGORY), CATEGORIES[DEFAULT_CATEGORY])
    return {
        **item,
        "category_label": cat["label"],
        "icon": cat["icon"],
        "color": cat["color"],
    }


_ORDER = list(CATEGORIES)


def sort_key(item: dict) -> tuple:
    """Do kupienia najpierw, potem dzialami sklepu, na koncu wg kolejnosci dodania."""
    category = item.get("category", DEFAULT_CATEGORY)
    order = _ORDER.index(category) if category in _ORDER else len(_ORDER)
    return (bool(item.get("done")), order, item.get("created_at", ""))


def items_view(state: dict) -> list[dict]:
    items = state.get("shopping", [])
    return [item_view(i) for i in sorted(items, key=sort_key)]


def find_item(state: dict, item_id: str) -> dict | None:
    return next((i for i in state.get("shopping", []) if i["id"] == item_id), None)


def stats(state: dict) -> dict:
    items = state.get("shopping", [])
    done = sum(1 for i in items if i.get("done"))
    return {
        "total": len(items),
        "done": done,
        "left": len(items) - done,
    }
