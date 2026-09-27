"""Minimalny klient REST Discorda działający na tokenie użytkownika."""

from collections.abc import Callable
from typing import Any

import requests

API_URL = "https://discord.com/api/v9"


class DiscordError(Exception):
    pass


class DiscordClient:
    def __init__(
        self,
        token_provider: Callable[[], str | None],
        session: requests.Session | None = None,
        api_url: str = API_URL,
    ):
        self._token_provider = token_provider
        self._session = session or requests.Session()
        self._api_url = api_url
        self._me: dict[str, Any] | None = None

    @property
    def configured(self) -> bool:
        return bool(self._token_provider())

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        token = self._token_provider()
        if not token:
            raise DiscordError("Brak tokenu Discorda (DISCORD_USER_TOKEN).")
        try:
            response = self._session.request(
                method, f"{self._api_url}{path}", headers={"authorization": token}, timeout=15, **kwargs
            )
        except requests.RequestException as e:
            raise DiscordError(f"Brak połączenia z Discordem: {e}") from e
        if response.status_code == 401:
            raise DiscordError("Token Discorda jest nieprawidłowy.")
        if response.status_code == 429:
            raise DiscordError("Discord ogranicza liczbę zapytań, spróbuj za chwilę.")
        if response.status_code >= 400:
            raise DiscordError(f"Discord zwrócił błąd {response.status_code}.")
        return response.json() if response.content else None

    def me(self) -> dict[str, Any]:
        if self._me is None:
            self._me = self._request("GET", "/users/@me")
        return self._me

    def send_message(self, channel_id: str, content: str) -> dict[str, Any]:
        return self._request("POST", f"/channels/{channel_id}/messages", json={"content": content})

    def latest_message(self, channel_id: str) -> dict[str, Any] | None:
        messages = self._request("GET", f"/channels/{channel_id}/messages", params={"limit": 1})
        return messages[0] if messages else None
