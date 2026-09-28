"""Warstwa zapisu danych.

Cały stan aplikacji (obowiązki + odhaczenia) trzyma się w jednym pliku JSON,
zeby dalo sie go po prostu skopiowac na inny komputer.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
import threading
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DATA_VERSION = 1


def default_state() -> dict:
    """Pusty, poprawny stan aplikacji."""
    return {
        "version": DATA_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "settings": {"household_name": "Dom", "seeded": False},
        # lista definicji obowiazkow (kazdy z wlasna reguła powtarzania)
        "chores": [],
        # {chore_id: ["2026-08-11", ...]} - dni, w ktore obowiazek zostal zrobiony
        "completions": {},
        # wspolna lista zakupow - rzeczy do kupienia i juz kupione
        "shopping": [],
        # grafik pracy domownikow: {"osoby": {kto: {data: zmiana}}, "miesiace": {...}}
        "grafik": {"osoby": {}, "miesiace": {}},
    }


class Store:
    """Prosty magazyn JSON z blokada i atomowym zapisem."""

    def __init__(self, path: str | os.PathLike) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        # ustawiane z zewnatrz (app.py): wolane po kazdym udanym zapisie.
        # Dzieki temu magazyn nic nie wie o przegladarkach ani o SSE.
        self.on_change: Callable[[], None] | None = None

    # ------------------------------------------------------------------ io --

    def load(self) -> dict:
        with self._lock:
            if not self.path.exists():
                state = default_state()
                self._write(state)
                return state
            try:
                with self.path.open("r", encoding="utf-8") as fh:
                    state = json.load(fh)
            except (json.JSONDecodeError, OSError):
                # Nie kasujemy uszkodzonego pliku - odkladamy go obok.
                self._backup(suffix="uszkodzony")
                state = default_state()
                self._write(state)
                return state
            return self._migrate(state)

    def save(self, state: dict) -> None:
        with self._lock:
            self._write(state)

    @contextmanager
    def edit(self):
        """Wczytaj stan, pozwol go zmienic, zapisz na koniec bloku."""
        with self._lock:
            state = self.load()
            yield state
            self._write(state)

    def replace(self, raw: dict) -> dict:
        """Podmien caly plik (import z innego komputera). Zwraca nowy stan."""
        state = self._migrate(raw)
        with self._lock:
            if self.path.exists():
                self._backup(suffix="przed-importem")
            self._write(state)
        return state

    def snapshot_daily(self, keep: int = 14) -> None:
        """Odklada kopie danych do podkatalogu 'kopie' - raz na dzien.

        Gdy aplikacja stoi na serwerze (Raspberry Pi), ten jeden plik bywa jedynym
        egzemplarzem danych calego domu - a karty microSD potrafia paść bez
        ostrzezenia.

        Wolane z _write(), czyli przed pierwsza dzisiejsza zmiana: kopia lapie stan
        sprzed edycji. Robienie tego przy starcie programu nie zadzialaloby, bo
        serwer domowy potrafi chodzic tygodniami bez restartu. Kopia nigdy nie moze
        zablokowac zapisu, wiec bledy tylko polykamy."""
        if not self.path.exists():
            return
        folder = self.path.parent / "kopie"
        target = folder / f"{self.path.stem}-{datetime.now():%Y-%m-%d}.json"
        if target.exists():
            return  # dzisiejsza kopia juz jest
        try:
            folder.mkdir(parents=True, exist_ok=True)
            with self._lock:
                shutil.copy2(self.path, target)
        except OSError:
            return
        for old in sorted(folder.glob(f"{self.path.stem}-*.json"))[:-keep]:
            with contextlib.suppress(OSError):
                old.unlink()

    # -------------------------------------------------------------- helpers --

    def _write(self, state: dict) -> None:
        self.snapshot_daily()  # kopia stanu sprzed pierwszej dzisiejszej zmiany
        self.path.parent.mkdir(parents=True, exist_ok=True)
        state["updated_at"] = datetime.now().isoformat(timespec="seconds")
        # zapis do pliku tymczasowego + podmiana, zeby nie stracic danych
        # gdyby proces padl w polowie zapisu
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

        if self.on_change is not None:
            self.on_change()  # dopiero po udanym zapisie - inaczej budzilibysmy na darmo

    def _backup(self, suffix: str) -> None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.path.with_name(f"{self.path.stem}.{suffix}-{stamp}.json")
        with contextlib.suppress(OSError):
            shutil.copy2(self.path, target)

    @staticmethod
    def _migrate(state: dict) -> dict:
        """Uzupelnia brakujace pola, zeby stary/obcy plik dalo sie wczytac."""
        if not isinstance(state, dict):
            raise ValueError("Plik JSON musi zawierac obiekt.")
        base = default_state()
        base.update({k: v for k, v in state.items() if k in base})
        if not isinstance(base.get("chores"), list):
            raise ValueError("Pole 'chores' musi byc lista.")
        if not isinstance(base.get("completions"), dict):
            base["completions"] = {}
        # starsze pliki (sprzed listy zakupow) w ogole nie maja tego pola
        if not isinstance(base.get("shopping"), list):
            base["shopping"] = []
        grafik = base.get("grafik")
        if not isinstance(grafik, dict):
            grafik = {}
        for klucz in ("osoby", "miesiace"):
            if not isinstance(grafik.get(klucz), dict):
                grafik[klucz] = {}
        base["grafik"] = grafik
        # Jedna osoba ("assignee") -> lista osob ("assignees"). Bez tego wszystkie
        # dotychczasowe obowiazki zrobilyby sie niczyje przy pierwszym odczycie.
        for chore in base["chores"]:
            if isinstance(chore, dict) and not isinstance(chore.get("assignees"), list):
                kto = chore.pop("assignee", "")
                chore["assignees"] = [kto] if isinstance(kto, str) and kto else []
            elif isinstance(chore, dict):
                chore.pop("assignee", None)
        settings = base.get("settings")
        base["settings"] = {**default_state()["settings"], **(settings or {})}
        base["version"] = DATA_VERSION
        return base
