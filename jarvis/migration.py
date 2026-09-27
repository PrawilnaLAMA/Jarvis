"""Jednorazowe przeniesienie danych ze starej struktury projektu do data/."""

import logging
from pathlib import Path

from jarvis import paths
from jarvis.jsonfile import read_json, write_json

log = logging.getLogger(__name__)


def migrate_legacy_data(
    events_src: Path = paths.LEGACY_EVENTS_FILE,
    events_dst: Path = paths.EVENTS_FILE,
    conversation_src: Path = paths.LEGACY_CONVERSATION_FILE,
    conversation_dst: Path = paths.CONVERSATION_FILE,
) -> None:
    if events_src.exists() and not events_dst.exists():
        events = read_json(events_src, [])
        if isinstance(events, list):
            # pole "reminded" zastępuje osobny stan przypomnień (reminders_state.json)
            for e in events:
                if isinstance(e, dict):
                    e.pop("reminded", None)
            write_json(events_dst, events)
            log.info("Przeniesiono %d wydarzeń z %s", len(events), events_src)

    if conversation_src.exists() and not conversation_dst.exists():
        history = read_json(conversation_src, [])
        if isinstance(history, list):
            write_json(conversation_dst, history)
            log.info("Przeniesiono historię rozmowy z %s", conversation_src)
