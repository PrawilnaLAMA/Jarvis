import json

import pytest

from jarvis.migration import migrate_legacy_data
from jarvis.settings import Secrets, Settings, SettingsError, SettingsStore, messenger_thread


def test_first_run_imports_contacts_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CHANNEL_PIOTREK", "123456789012")
    monkeypatch.setenv("CHANNEL_ŁUKASZ", "223456789012")
    store = SettingsStore(tmp_path / "settings.json")
    names = {c.name for c in store.get().contacts}
    assert {"PIOTREK", "ŁUKASZ"} <= names
    assert (tmp_path / "settings.json").exists()


def test_existing_file_is_not_overwritten_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CHANNEL_PIOTREK", "123456789012")
    (tmp_path / "settings.json").write_text(json.dumps({"contacts": []}), encoding="utf-8")
    assert SettingsStore(tmp_path / "settings.json").get().contacts == []


def test_from_dict_tolerates_garbage():
    s = Settings.from_dict({"voice": {"wake_threshold": "abc", "tts_rate": 5, "unknown": 1}, "x": 2})
    assert s.voice.wake_threshold == 0.5  # zła wartość → domyślna
    assert s.voice.tts_rate == 5


def test_update_merges_and_persists(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    changed = []
    store._on_change = changed.append
    store.update({"voice": {"tts_rate": 10}})
    assert store.get().voice.tts_rate == 10
    assert store.get().voice.tts_voice == "en-US-AndrewMultilingualNeural"  # reszta sekcji zachowana
    assert SettingsStore(tmp_path / "settings.json").get().voice.tts_rate == 10
    assert len(changed) == 1


def test_update_rejects_invalid(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    with pytest.raises(SettingsError) as exc:
        store.update({"contacts": [{"name": "A", "channel_id": "nie-liczba"}], "voice": {"barge_in": "x"}})
    assert len(exc.value.errors) == 2
    assert store.get().contacts == []


@pytest.mark.parametrize(("ref", "thread"), [
    ("https://www.messenger.com/e2ee/t/123456789/", "e2ee/t/123456789"),
    ("messenger.com/t/123456789", "t/123456789"),
    ("123456789", "t/123456789"),
    (" e2ee/t/123456789 ", "e2ee/t/123456789"),
    ("https://facebook.com/natalia", None),
    ("Natalia", None),
])
def test_messenger_thread(ref, thread):
    assert messenger_thread(ref) == thread


def test_contact_needs_discord_or_messenger(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.update({"contacts": [{"name": "NATALIA", "messenger": "123456789"}]})
    assert store.get().contacts[0].apps == ["messenger"]
    with pytest.raises(SettingsError) as exc:
        store.update({"contacts": [{"name": "A"}, {"name": "B", "messenger": "facebook.com/b"}]})
    assert exc.value.errors == [
        "Kontakt A potrzebuje ID kanału Discorda albo linku do czatu Messengera.",
        "Nieprawidłowy link do czatu Messengera dla kontaktu B.",
    ]


def test_contact_lookup_by_alias():
    s = Settings.from_dict({"contacts": [{"name": "PIOTREK", "channel_id": "1234567", "aliases": ["Piotr"]}]})
    assert s.contact_by_name("piotr").name == "PIOTREK"
    assert s.contact_by_name("piotrek").name == "PIOTREK"
    assert s.contact_by_name("anna") is None


def test_secrets_roundtrip_and_legacy_token(tmp_path, monkeypatch):
    monkeypatch.delenv("DISCORD_USER_TOKEN", raising=False)
    monkeypatch.setenv("USER_TOKEN", "legacy-token-123456")
    env = tmp_path / ".env"
    secrets = Secrets(env)
    assert secrets.discord_token == "legacy-token-123456"
    secrets.set("GROQ_API_KEY", "gsk_abcdefghijkl")
    assert "GROQ_API_KEY=gsk_abcdefghijkl" in env.read_text(encoding="utf-8")
    masked = secrets.masked()["GROQ_API_KEY"]
    assert masked == {"set": True, "hint": "…ijkl"}
    with pytest.raises(KeyError):
        secrets.set("PATH", "x")


def test_domownik_url_validation(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    assert store.get().domownik.url == "http://127.0.0.1:8080"
    assert store.update({"domownik": {"url": "http://domownik.local:8080/"}}).domownik.url == "http://domownik.local:8080/"
    with pytest.raises(SettingsError):
        store.update({"domownik": {"url": "domownik.local"}})


def test_migration_copies_conversation_once(tmp_path):
    src = tmp_path / "old_conv.json"
    src.write_text(json.dumps([{"role": "user", "content": "cześć"}]), encoding="utf-8")
    dst = tmp_path / "data" / "conv.json"
    migrate_legacy_data(src, dst)
    assert json.loads(dst.read_text(encoding="utf-8")) == [{"role": "user", "content": "cześć"}]
    src.write_text("[]", encoding="utf-8")
    migrate_legacy_data(src, dst)  # istniejących danych nie nadpisuje
    assert json.loads(dst.read_text(encoding="utf-8")) != []
    migrate_legacy_data(tmp_path / "none.json", tmp_path / "data" / "other.json")
    assert not (tmp_path / "data" / "other.json").exists()
