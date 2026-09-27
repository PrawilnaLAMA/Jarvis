"""Obróbka transkrypcji: usuwanie słowa wywołania, filtr halucynacji Whispera, wykrywanie echa."""

import re
from difflib import SequenceMatcher

# „hej jarvis”, „hey jarvis”, „ej dżarwis”… – różne zapisy, które zwraca Whisper
_WAKE = re.compile(
    r"(?:\b(?:hej|hey|hei|ej|hi|halo)\b[\s,.!-]*)?\b(?:jarvis\w*|dżarvis\w*|dżarwis\w*|jarwis\w*|jervis\w*|dżerwis\w*)\b"
    r"[\s,.!?:-]*",
    re.IGNORECASE,
)

# typowe halucynacje Whispera na ciszy/szumie (napisy z filmów, na których był trenowany)
_HALLUCINATIONS = (
    "dziękuję",
    "dziękuję za uwagę",
    "dzięki za obejrzenie",
    "dziękuję za obejrzenie",
    "do zobaczenia",
    "subskrybuj",
    "zapraszam do subskrypcji",
    "thank you",
    "thanks for watching",
)
_HALLUCINATION_MARKERS = ("amara.org", "napisy stworzone", "napisy wykonane", "napisy przygotowane", "tłumaczenie:")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def has_wake_phrase(text: str) -> bool:
    return _WAKE.search(text) is not None


def strip_wake_phrase(text: str) -> str:
    """Zwraca polecenie po ostatnim wystąpieniu słowa wywołania (albo cały tekst, gdy go brak)."""
    matches = list(_WAKE.finditer(text))
    if not matches:
        return text.strip()
    return text[matches[-1].end() :].strip()


def is_hallucination(text: str, prompt: str = "") -> bool:
    norm = normalize(text)
    if not norm:
        return True
    if norm in _HALLUCINATIONS or any(marker in text.lower() for marker in _HALLUCINATION_MARKERS):
        return True
    # na ciszy Whisper potrafi zwrócić po prostu podpowiedź (słownik)
    return bool(prompt) and norm in normalize(prompt)


def clean_transcript(text: str, prompt: str = "") -> str:
    """Tekst polecenia gotowy dla asystenta albo pusty napis, gdy nie ma czego obsłużyć."""
    if is_hallucination(text, prompt):
        return ""
    command = strip_wake_phrase(text)
    return "" if is_hallucination(command, prompt) else command


def echo_similarity(transcript: str, reference: str) -> float:
    """Jak bardzo transkrypcja przypomina fragment tego, co mówił Jarvis (0..1)."""
    heard = normalize(transcript).split()
    said = normalize(reference).split()
    if not heard or not said:
        return 0.0
    n = len(heard)
    best = 0.0
    for start in range(0, max(1, len(said) - n + 1)):
        window = " ".join(said[start : start + n + 2])
        best = max(best, SequenceMatcher(None, " ".join(heard), window).ratio())
    return best


def is_echo(transcript: str, reference: str, threshold: float = 0.6) -> bool:
    return echo_similarity(transcript, reference) >= threshold
