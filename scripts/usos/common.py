"""Wspólna konfiguracja skryptów USOS – dane dostępowe z pliku .env (nigdy w kodzie)."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

BASE_URL = os.getenv("USOS_BASE_URL") or os.getenv("BASE_URL") or "https://apps.usos-szkol.pwr.edu.pl/"


def require(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        sys.exit(f"Brak zmiennej {name} w pliku .env")
    return value
