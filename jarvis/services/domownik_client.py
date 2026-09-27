"""Klient API Domownika – aplikacji domowej z obowiązkami, listą zakupów i grafikiem pracy.

Domownik jest kalendarzem Jarvisa. Rozmawiamy z nim WYŁĄCZNIE przez HTTP: jego plik danych
może zapisywać tylko jeden proces (serwer Domownika), inaczej zmiany by się nadpisywały.
"""

from collections.abc import Callable
from datetime import date
from typing import Any

import requests


class DomownikError(Exception):
    """Błąd z komunikatem po polsku (do wypowiedzenia/pokazania)."""


class DomownikClient:
    def __init__(self, base_url: Callable[[], str], session: requests.Session | None = None, timeout: float = 6):
        self._base_url = base_url
        self._session = session or requests.Session()
        self._timeout = timeout

    @property
    def url(self) -> str:
        return self._base_url().rstrip("/")

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._session.request(method, f"{self.url}{path}", timeout=self._timeout, **kwargs)
        except requests.RequestException as e:
            raise DomownikError("Domownik nie odpowiada – czy jego serwer jest uruchomiony?") from e
        try:
            data = response.json() if response.content else {}
        except ValueError:
            data = {}
        if response.status_code >= 400:
            message = data.get("error") if isinstance(data, dict) else None
            raise DomownikError(message or f"Domownik zwrócił błąd {response.status_code}.")
        return data

    # --- stan ---

    def ping(self) -> None:
        self._request("GET", "/api/wersja")

    # --- obowiązki ---

    def agenda(self, start: date, days: int) -> dict[str, Any]:
        """Dni z obowiązkami (kto robi, czy zrobione), zaległości i grafik pracy."""
        return self._request("GET", "/api/agenda", params={"od": start.isoformat(), "dni": max(1, min(31, days))})

    def chores(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/obowiazki").get("chores", [])

    def add_chore(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/obowiazki", json=payload)

    def delete_chore(self, chore_id: str) -> None:
        self._request("DELETE", f"/api/obowiazki/{chore_id}")

    def set_done(self, chore_id: str, day: date, done: bool = True) -> None:
        self._request("POST", "/api/odhacz", json={"id": chore_id, "date": day.isoformat(), "done": done})

    # --- zakupy ---

    def shopping(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/zakupy").get("items", [])

    def add_item(self, title: str, qty: str = "") -> dict[str, Any]:
        return self._request("POST", "/api/zakupy", json={"title": title, "qty": qty})

    def update_item(self, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/api/zakupy/{item_id}", json=payload)

    def delete_item(self, item_id: str) -> None:
        self._request("DELETE", f"/api/zakupy/{item_id}")

    def clear_bought(self) -> int:
        """Usuwa kupione rzeczy; zwraca, ile ich było."""
        return int(self._request("POST", "/api/zakupy/wyczysc").get("usuniete", 0))
