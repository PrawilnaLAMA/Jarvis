"""Szyna zdarzeń łącząca wątki backendu z interfejsem (WebSocket).

Tematy (topic) i ich dane:
- state            {state: idle|listening|transcribing|thinking|speaking|follow_up|muted|offline}
- transcript       {text, source: voice|text}          – co powiedział/wpisał użytkownik
- reply            {text, source}                      – odpowiedź Jarvisa
- tool             {name, args, result}                – wywołane narzędzie
- audio.level      {source: mic|tts, level: 0..1, wake?: 0..1}
- tts.start        {text, words: [{text, start_ms, end_ms}]}
- tts.word         {index, text}
- tts.end          {interrupted: bool, spoken: str}
- discord.message  {author, content, channel_id}
- reminder         {text, event_id}
- notice           {text, level: info|warning|error}
- calendar.changed {}
- settings.changed {}
- ui.navigate      {view}
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    topic: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"topic": self.topic, "data": self.data, "ts": self.ts}


Handler = Callable[[Event], None]


class EventBus:
    """Prosty, bezpieczny wątkowo pub/sub. Handlery wywoływane są w wątku publikującym,
    więc muszą być szybkie (np. tylko przekazać zdarzenie do kolejki)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handlers: list[tuple[Handler, frozenset[str] | None]] = []

    def subscribe(self, handler: Handler, topics: set[str] | None = None) -> Callable[[], None]:
        entry = (handler, frozenset(topics) if topics else None)
        with self._lock:
            self._handlers.append(entry)

        def unsubscribe() -> None:
            with self._lock:
                if entry in self._handlers:
                    self._handlers.remove(entry)

        return unsubscribe

    def publish(self, topic: str, **data: Any) -> Event:
        event = Event(topic, data)
        with self._lock:
            handlers = list(self._handlers)
        for handler, topics in handlers:
            if topics is not None and topic not in topics:
                continue
            try:
                handler(event)
            except Exception:
                log.exception("Błąd w handlerze zdarzenia %s", topic)
        return event

    def notice(self, text: str, level: str = "info") -> None:
        """Skrót do komunikatów dla użytkownika (pokazywanych w UI)."""
        getattr(log, "error" if level == "error" else "warning" if level == "warning" else "info")(text)
        self.publish("notice", text=text, level=level)
