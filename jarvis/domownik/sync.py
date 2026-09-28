"""Powiadamianie przegladarek o zmianie danych.

Serce natychmiastowej synchronizacji: kazdy zapis do pliku podbija licznik i budzi
wszystkie polaczenia SSE (/api/zmiany), ktore wisza w oczekiwaniu. Dzieki temu
telefon dowiaduje sie o zmianie zrobionej na laptopie w ulamku sekundy, zamiast
czekac na kolejne odpytanie.
"""

from __future__ import annotations

import threading


class Broadcaster:
    """Licznik zmian + budzik dla watkow czekajacych na kolejna zmiane."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._version = 0

    @property
    def version(self) -> int:
        with self._cond:
            return self._version

    def bump(self) -> None:
        """Wolane po kazdym zapisie danych - budzi wszystkich sluchaczy."""
        with self._cond:
            self._version += 1
            self._cond.notify_all()

    def wait(self, seen: int, timeout: float) -> int:
        """Czeka na zmiane wzgledem wersji 'seen'. Zwraca aktualna wersje.

        Gdy nic sie nie wydarzy w zadanym czasie, po prostu oddaje stara wersje -
        wolajacy wysyla wtedy sygnal podtrzymujacy polaczenie."""
        with self._cond:
            if self._version == seen:
                self._cond.wait(timeout)
            return self._version
