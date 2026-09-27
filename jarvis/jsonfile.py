"""Bezpieczny zapis i odczyt plików JSON."""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def read_json(path: Path, default: Any) -> Any:
    """Zwraca zawartość pliku albo `default`, gdy go nie ma lub jest uszkodzony."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as e:
        log.warning("Nie udało się wczytać %s: %s", path, e)
        return default


def write_json(path: Path, data: Any) -> None:
    """Zapis atomowy: najpierw plik tymczasowy, potem podmiana."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
