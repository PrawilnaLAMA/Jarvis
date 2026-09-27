"""Jednorazowe przeniesienie danych ze starej struktury projektu do data/."""

import logging
from pathlib import Path

from jarvis import paths
from jarvis.jsonfile import read_json, write_json

log = logging.getLogger(__name__)


def migrate_legacy_data(
    conversation_src: Path = paths.LEGACY_CONVERSATION_FILE,
    conversation_dst: Path = paths.CONVERSATION_FILE,
) -> None:
    if conversation_src.exists() and not conversation_dst.exists():
        history = read_json(conversation_src, [])
        if isinstance(history, list):
            write_json(conversation_dst, history)
            log.info("Przeniesiono historię rozmowy z %s", conversation_src)
