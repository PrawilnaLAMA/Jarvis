"""Klient modeli językowych zgodnych z API OpenAI (Groq, Cerebras).

Dostawcy są próbowani po kolei: gdy główny (Groq) zwróci limit zapytań (429) albo błąd
serwera, zapytanie idzie do zapasowego (Cerebras, jeśli skonfigurowany).
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

from jarvis.settings import Secrets, Settings

log = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1"
CEREBRAS_URL = "https://api.cerebras.ai/v1"

# modele Groq, które nie służą do rozmowy – pomijamy je na liście w ustawieniach
_NON_CHAT_MARKERS = ("whisper", "guard", "orpheus", "tts", "playai", "distil")

# ile najwyżej czekać na zwolnienie limitu zapytań, zanim zgłosimy błąd użytkownikowi
MAX_LIMIT_WAIT = 20.0


def _retry_after(response: requests.Response) -> float | None:
    """Czas oczekiwania z nagłówka retry-after (sekundy) albo None."""
    try:
        return float(response.headers.get("retry-after", ""))
    except (TypeError, ValueError):
        return None


def _log_usage(provider: "Provider", usage: dict[str, Any]) -> None:
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
    log.info(
        "%s %s: prompt=%s (cache=%s) completion=%s",
        provider.name, provider.model, usage.get("prompt_tokens"), cached, usage.get("completion_tokens"),
    )


class LLMError(Exception):
    """Błąd z komunikatem po polsku, który można pokazać/wypowiedzieć."""


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str

    def extra_params(self) -> dict[str, Any]:
        # modele gpt-oss rozumują przed odpowiedzią; niski poziom = szybsze odpowiedzi głosowe
        return {"reasoning_effort": "low"} if "gpt-oss" in self.model else {}


def providers_from(settings: Settings, secrets: Secrets) -> list[Provider]:
    result = []
    if secrets.groq_api_key:
        result.append(Provider("Groq", GROQ_URL, secrets.groq_api_key, settings.llm.model))
    if secrets.cerebras_api_key and settings.llm.fallback_model:
        result.append(Provider("Cerebras", CEREBRAS_URL, secrets.cerebras_api_key, settings.llm.fallback_model))
    return result


class LLMClient:
    def __init__(
        self,
        providers: Callable[[], list[Provider]],
        session: requests.Session | None = None,
        timeout: float = 30,
        on_limit_wait: Callable[[float], None] | None = None,
    ):
        self._providers = providers
        self._session = session or requests.Session()
        self._timeout = timeout
        self._on_limit_wait = on_limit_wait  # np. komunikat w UI „czekam na limit…”

    @property
    def configured(self) -> bool:
        return bool(self._providers())

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Zwraca wiadomość asystenta: {"role": "assistant", "content": ..., "tool_calls": [...]}."""
        providers = self._providers()
        if not providers:
            raise LLMError("Brak klucza API do modelu językowego. Dodaj GROQ_API_KEY w ustawieniach.")
        last_error = LLMError("Model językowy jest niedostępny.")
        for i, provider in enumerate(providers):
            body: dict[str, Any] = {
                "model": provider.model,
                "messages": messages,
                "temperature": temperature,
                "max_completion_tokens": max_tokens,
                **provider.extra_params(),
            }
            if tools:
                body["tools"] = tools
            try:
                # na krótki limit czekamy tylko u ostatniego dostawcy – wcześniej lepiej przejść do zapasowego
                return self._post_with_retry(provider, body, wait_on_limit=i == len(providers) - 1)
            except LLMError as e:
                log.warning("%s: %s", provider.name, e)
                last_error = e
        raise last_error

    def _post_with_retry(
        self, provider: Provider, body: dict[str, Any], attempts: int = 2, wait_on_limit: bool = True
    ) -> dict[str, Any]:
        for attempt in range(attempts):
            retry = attempt + 1 < attempts
            try:
                response = self._session.post(
                    f"{provider.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {provider.api_key}"},
                    json=body,
                    timeout=self._timeout,
                )
            except requests.RequestException as e:
                if retry:
                    continue
                raise LLMError("Nie mogę połączyć się z modelem językowym. Sprawdź internet.") from e

            if response.status_code == 200:
                data = response.json()
                _log_usage(provider, data.get("usage") or {})
                return data["choices"][0]["message"]
            if response.status_code == 401:
                raise LLMError(f"Klucz API dostawcy {provider.name} jest nieprawidłowy.")
            if response.status_code == 429:
                wait = _retry_after(response)
                if retry and wait_on_limit and wait is not None and wait <= MAX_LIMIT_WAIT:
                    log.info("%s: limit zapytań, czekam %.1f s", provider.name, wait)
                    if self._on_limit_wait:
                        self._on_limit_wait(wait)
                    time.sleep(wait)
                    continue
                raise LLMError("Przekroczono limit zapytań do modelu językowego. Spróbuj za chwilę.")
            if response.status_code == 400 and "tool_use_failed" in response.text and retry:
                continue  # model wygenerował niepoprawne wywołanie narzędzia – zwykle druga próba się udaje
            if response.status_code >= 500 and retry:
                time.sleep(0.5)
                continue
            log.error("%s HTTP %s: %s", provider.name, response.status_code, response.text[:500])
            raise LLMError(f"Model językowy zwrócił błąd ({response.status_code}).")
        raise LLMError("Model językowy jest niedostępny.")

    def list_models(self) -> list[str]:
        """Modele czatu dostępne u głównego dostawcy (do wyboru w ustawieniach)."""
        providers = self._providers()
        if not providers:
            return []
        provider = providers[0]
        try:
            response = self._session.get(
                f"{provider.base_url}/models",
                headers={"Authorization": f"Bearer {provider.api_key}"},
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise LLMError("Nie udało się pobrać listy modeli.") from e
        ids = [m["id"] for m in response.json().get("data", []) if m.get("active", True)]
        return sorted(i for i in ids if not any(marker in i.lower() for marker in _NON_CHAT_MARKERS))
