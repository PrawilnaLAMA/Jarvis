"""Mózg Jarvisa: rozumie polecenie przez LLM (function calling), wykonuje narzędzia, zwraca odpowiedź."""

import json
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from jarvis.conversation import Conversation
from jarvis.events import EventBus
from jarvis.llm import LLMClient, LLMError
from jarvis.services.calendar_store import MONTHS_GENITIVE_PL, WEEKDAYS_PL
from jarvis.settings import Settings, SettingsStore
from jarvis.tools import Tool, ToolContext, ToolError, build_tools

log = logging.getLogger(__name__)

MAX_ROUNDS = 3
FAILED_REPLY = "Przepraszam, coś poszło nie tak. Spróbuj jeszcze raz."


@dataclass(frozen=True)
class Interruption:
    """Użytkownik przerwał wypowiedź Jarvisa – `spoken` to fragment, który zdążył paść."""

    spoken: str


def build_system_prompt(settings: Settings) -> str:
    """Stała część promptu. Nie wstawiamy tu nic zmiennego (np. godziny), bo stały początek
    promptu (razem z definicjami narzędzi) trafia do cache Groq – szybciej i mniej zużywa limit."""
    lines = [
        "Jesteś Jarvis – osobisty asystent głosowy. Mówisz po polsku.",
        "- Odpowiadaj krótko (1–2 zdania), językiem mówionym, bez markdown, list i emotek – to jest czytane na głos.",
        "- Gdy prośba pasuje do narzędzia, wywołaj je (możesz kilka naraz); inaczej po prostu odpowiedz.",
        "- Narzędzia zmieniające coś (kalendarz, wiadomości, wyłączanie) wywołuj tylko na wyraźną prośbę "
        "z ostatniej wypowiedzi.",
        "- Daty względne („jutro”, „w piątek”) bierz z listy dni w <kontekst>, nie licz sam; „w piątek” = najbliższy.",
        "- Tekst pochodzi z rozpoznawania mowy i może mieć błędy – domyśl się sensu, a gdy nie wiesz, dopytaj.",
        "- Nie zgaduj zawartości kalendarza – sprawdź narzędziem.",
        "- <kontekst> dodaje system, użytkownik go nie widzi.",
    ]
    aliases = [f"{c.name} = {', '.join(c.aliases)}" for c in settings.contacts if c.aliases]
    if aliases:
        lines.append(f"Inne nazwy kontaktów: {'; '.join(aliases)}.")
    return "\n".join(lines)


def build_context(now: datetime, source: str, interruption: Interruption | None, days_ahead: int = 14) -> str:
    """Zmienna część promptu dołączana do bieżącej wiadomości użytkownika."""
    upcoming = []
    for i in range(1, days_ahead + 1):
        day = (now + timedelta(days=i)).date()
        label = " (jutro)" if i == 1 else " (pojutrze)" if i == 2 else ""
        upcoming.append(f"{WEEKDAYS_PL[day.weekday()]} {day.isoformat()}{label}")
    lines = [
        f"Teraz: {WEEKDAYS_PL[now.weekday()]} {now:%Y-%m-%d}, godz. {now:%H:%M} "
        f"({now.day} {MONTHS_GENITIVE_PL[now.month - 1]}).",
        "Najbliższe dni: " + ", ".join(upcoming) + ".",
    ]
    if source == "text":
        lines.append("Użytkownik tym razem pisze na klawiaturze.")
    if interruption:
        lines.append(
            f"Użytkownik przerwał twoją poprzednią wypowiedź – zdążyłeś powiedzieć tylko: „{interruption.spoken}”. "
            "Nie powtarzaj jej, odnieś się do tego, co mówi teraz."
        )
    return "<kontekst>\n" + "\n".join(lines) + "\n</kontekst>"


_MARKDOWN = [
    (re.compile(r"\*\*|__|`+|^#+\s*", re.MULTILINE), ""),
    (re.compile(r"^\s*[-*•]\s+", re.MULTILINE), ""),
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),
    (re.compile(r"\s+"), " "),
]


def clean_reply(text: str) -> str:
    """Usuwa formatowanie, którego nie da się sensownie przeczytać na głos."""
    for pattern, repl in _MARKDOWN:
        text = pattern.sub(repl, text)
    return text.strip()


class Assistant:
    def __init__(
        self,
        llm: LLMClient,
        tool_context: ToolContext,
        settings: SettingsStore,
        bus: EventBus,
        conversation: Conversation,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self._llm = llm
        self._ctx = tool_context
        self._settings = settings
        self._bus = bus
        self._conversation = conversation
        self._clock = clock
        self._lock = threading.Lock()  # jedna rozmowa naraz (głos i UI korzystają z tej samej historii)

    def handle(self, text: str, source: str = "voice", interruption: Interruption | None = None) -> str | None:
        """Przetwarza polecenie i zwraca tekst odpowiedzi (None = nic nie mówić)."""
        text = text.strip()
        if not text:
            return None
        with self._lock:
            self._bus.publish("transcript", text=text, source=source)
            try:
                reply = self._run(text, source, interruption)
            except LLMError as e:
                self._bus.notice(str(e), "error")
                reply = str(e)
            except Exception:
                log.exception("Błąd obsługi polecenia")
                reply = FAILED_REPLY
            self._conversation.add("user", text)
            if reply:
                self._conversation.add("assistant", reply)
                self._bus.publish("reply", text=reply, source=source)
            return reply

    def _run(self, text: str, source: str, interruption: Interruption | None) -> str | None:
        settings = self._settings.get()
        tools = build_tools(settings)
        by_name = {t.name: t for t in tools}
        context = build_context(self._clock(), source, interruption)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": build_system_prompt(settings)},
            *self._conversation.messages(),
            {"role": "user", "content": f"{context}\n{text}"},
        ]
        schemas = [t.schema() for t in tools]

        for _ in range(MAX_ROUNDS):
            message = self._llm.chat(messages, schemas)
            calls = message.get("tool_calls") or []
            if not calls:
                return clean_reply(message.get("content") or "") or None

            results = [(call, *self._execute(call, by_name)) for call in calls]
            if all(direct for _, _, direct in results):
                return " ".join(r for _, r, _ in results if r).strip() or None

            # część wyników wymaga sformułowania odpowiedzi przez model – druga runda
            messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls})
            messages.extend(
                {"role": "tool", "tool_call_id": call["id"], "content": result or "OK"}
                for call, result, _ in results
            )
        return FAILED_REPLY

    def _execute(self, call: dict[str, Any], by_name: dict[str, Tool]) -> tuple[str, bool]:
        """Wykonuje jedno wywołanie; zwraca (wynik, czy_mówić_bezpośrednio)."""
        name = call.get("function", {}).get("name", "")
        tool = by_name.get(name)
        try:
            args = json.loads(call.get("function", {}).get("arguments") or "{}")
            if not isinstance(args, dict):
                args = {}
        except json.JSONDecodeError:
            args = {}
        if not tool:
            result, direct = f"Nieznane narzędzie: {name}.", False
        else:
            direct = tool.speak_directly
            try:
                result = tool.handler(self._ctx, args)
            except ToolError as e:
                result, direct = str(e), True
            except Exception:
                log.exception("Błąd narzędzia %s", name)
                result, direct = "Nie udało się wykonać polecenia.", True
        log.info("Narzędzie %s(%s) -> %s", name, args, result)
        self._bus.publish("tool", name=name, args=args, result=result)
        return result, direct
