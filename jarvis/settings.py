"""Ustawienia aplikacji.

Zwykłe ustawienia trzymamy w data/settings.json (edytowalne z UI), a sekrety (klucze API,
token Discorda) w .env, żeby nie trafiły do repozytorium ani do pliku ustawień.
"""

import copy
import dataclasses
import logging
import os
import re
import threading
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv, set_key

from jarvis.jsonfile import read_json, write_json

log = logging.getLogger(__name__)

BARGE_IN_MODES = ("any", "wakeword", "off")


MESSAGING_APPS = ("discord", "messenger")
_MESSENGER_REF = re.compile(r"(?:(?:https?://)?(?:www\.)?messenger\.com/)?/?(e2ee/)?(?:t/)?(\d{5,25})/?")


def messenger_thread(ref: str) -> str | None:
    """Ścieżka czatu Messengera z linku lub numeru: „…/e2ee/t/123/” → „e2ee/t/123”, „123” → „t/123”."""
    match = _MESSENGER_REF.fullmatch(ref.strip())
    if not match:
        return None
    return f"{match.group(1) or ''}t/{match.group(2)}"


@dataclass
class Contact:
    name: str  # nazwa używana przez LLM, np. "PIOTREK"
    channel_id: str = ""  # kanał Discorda (rozmowa prywatna); pusty = kontakt bez Discorda
    aliases: list[str] = field(default_factory=list)  # inne formy, np. "Piotr", "Piotrka"
    messenger: str = ""  # link do czatu z messenger.com albo jego numer; pusty = bez Messengera

    @property
    def display_name(self) -> str:
        return self.name.capitalize()

    @property
    def apps(self) -> list[str]:
        """Komunikatory, na których można napisać do kontaktu."""
        refs = {"discord": self.channel_id, "messenger": self.messenger}
        return [app for app in MESSAGING_APPS if refs[app].strip()]


@dataclass
class LLMSettings:
    model: str = "openai/gpt-oss-120b"
    fallback_model: str = "gpt-oss-120b"  # model u dostawcy zapasowego (Cerebras)
    history_messages: int = 12  # ile ostatnich wiadomości rozmowy wysyłać do modelu


@dataclass
class VoiceSettings:
    listen: bool = True  # czy nasłuchiwać mikrofonu
    wake_threshold: float = 0.5
    barge_in: str = "any"  # any | wakeword | off
    follow_up_seconds: float = 5.0
    input_device: str = ""  # pusta nazwa = urządzenie domyślne
    output_device: str = ""
    stt_model: str = "whisper-large-v3"
    vocabulary: list[str] = field(default_factory=list)  # dodatkowe słowa dla Whispera
    tts_voice: str = "en-US-AndrewMultilingualNeural"  # wielojęzyczny, mówi po polsku; alternatywy w UI
    tts_rate: int = 0  # procent, np. 10 = szybciej o 10%
    tts_pitch: int = 0  # Hz, np. -5 = trochę niżej
    volume: float = 1.0
    speak_text_replies: bool = True  # czy czytać na głos odpowiedzi na komendy wpisane w UI


@dataclass
class DomownikSettings:
    # serwer aplikacji Domownik (obowiązki domowe, zakupy, grafik) – kalendarz Jarvisa;
    # po przeniesieniu na Raspberry Pi np. http://domownik.local:8080 albo adres Tailscale
    url: str = "http://127.0.0.1:8080"


@dataclass
class DiscordSettings:
    read_aloud: bool = True
    poll_seconds: float = 3.0


@dataclass
class MessengerSettings:
    # Messenger nie ma API dla prywatnych kont – Jarvis steruje messenger.com w osobnej przeglądarce
    enabled: bool = False
    read_aloud: bool = True
    poll_seconds: float = 3.0
    browser: str = ""  # pusty = Chrome (a bez niego Edge/Chromium), albo ścieżka do pliku przeglądarki


@dataclass
class UISettings:
    fullscreen: bool = False


@dataclass
class Settings:
    contacts: list[Contact] = field(default_factory=list)
    llm: LLMSettings = field(default_factory=LLMSettings)
    voice: VoiceSettings = field(default_factory=VoiceSettings)
    domownik: DomownikSettings = field(default_factory=DomownikSettings)
    discord: DiscordSettings = field(default_factory=DiscordSettings)
    messenger: MessengerSettings = field(default_factory=MessengerSettings)
    ui: UISettings = field(default_factory=UISettings)

    def contact_by_name(self, name: str) -> Contact | None:
        wanted = name.strip().lower()
        for c in self.contacts:
            if c.name.lower() == wanted or wanted in (a.lower() for a in c.aliases):
                return c
        return None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        return _from_dict(cls, data)


def _from_dict(cls: type, data: Any) -> Any:
    """Buduje dataclass ze słownika: ignoruje nieznane klucze, braki uzupełnia domyślnymi,
    a wartości o złym typie zastępuje domyślnymi (żeby uszkodzony plik nie wywalał aplikacji)."""
    if not isinstance(data, dict):
        return cls()
    hints = typing.get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        value = _coerce(hints[f.name], data[f.name])
        if value is not _INVALID:
            kwargs[f.name] = value
    return cls(**kwargs)


_INVALID = object()


def _coerce(tp: Any, value: Any) -> Any:
    origin = typing.get_origin(tp)
    if dataclasses.is_dataclass(tp):
        return _from_dict(tp, value)
    if origin is list:
        if not isinstance(value, list):
            return _INVALID
        (item_tp,) = typing.get_args(tp)
        items = [_coerce(item_tp, v) for v in value]
        return [v for v in items if v is not _INVALID]
    if tp is float:
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else _INVALID
    if tp is int:
        return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else _INVALID
    if tp is bool:
        return value if isinstance(value, bool) else _INVALID
    if tp is str:
        return value if isinstance(value, str) else str(value) if isinstance(value, (int, float)) else _INVALID
    return value


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def validate(settings: Settings) -> list[str]:
    """Zwraca listę błędów (po polsku) – pusta lista oznacza poprawne ustawienia."""
    errors = []
    names = [c.name.strip().lower() for c in settings.contacts]
    if any(not n for n in names):
        errors.append("Każdy kontakt musi mieć nazwę.")
    if len(set(names)) != len(names):
        errors.append("Nazwy kontaktów muszą być unikalne.")
    for c in settings.contacts:
        if c.channel_id.strip() and not re.fullmatch(r"\d{5,25}", c.channel_id.strip()):
            errors.append(f"Nieprawidłowe ID kanału Discorda dla kontaktu {c.name or '?'}.")
        if c.messenger.strip() and not messenger_thread(c.messenger):
            errors.append(f"Nieprawidłowy link do czatu Messengera dla kontaktu {c.name or '?'}.")
        if not c.apps:
            errors.append(f"Kontakt {c.name or '?'} potrzebuje ID kanału Discorda albo linku do czatu Messengera.")
    v = settings.voice
    if v.barge_in not in BARGE_IN_MODES:
        errors.append("Nieznany tryb przerywania.")
    if not 0.05 <= v.wake_threshold <= 0.99:
        errors.append("Próg słowa wywołania musi być między 0,05 a 0,99.")
    if not 0 <= v.follow_up_seconds <= 30:
        errors.append("Czas nasłuchu po odpowiedzi musi być między 0 a 30 s.")
    if not -50 <= v.tts_rate <= 100:
        errors.append("Tempo mowy musi być między -50% a +100%.")
    if not -30 <= v.tts_pitch <= 30:
        errors.append("Wysokość głosu musi być między -30 a +30 Hz.")
    if not 0 <= v.volume <= 1.5:
        errors.append("Głośność musi być między 0 a 1,5.")
    if not re.fullmatch(r"https?://[^\s/]+(:\d+)?(/\S*)?", settings.domownik.url.strip()):
        errors.append("Adres Domownika musi zaczynać się od http:// lub https://, np. http://127.0.0.1:8080.")
    if not 1 <= settings.discord.poll_seconds <= 300:
        errors.append("Odświeżanie Discorda musi być między 1 a 300 s.")
    if not 1 <= settings.messenger.poll_seconds <= 300:
        errors.append("Odświeżanie Messengera musi być między 1 a 300 s.")
    return errors


class SettingsError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__(" ".join(errors))
        self.errors = errors


class SettingsStore:
    """Trzyma aktualne ustawienia w pamięci i zapisuje je do pliku JSON."""

    def __init__(self, path: Path, on_change: typing.Callable[[Settings], None] | None = None):
        self._path = path
        self._lock = threading.RLock()
        self._on_change = on_change
        raw = read_json(path, None)
        self._settings = Settings.from_dict(raw) if raw is not None else self._initial_settings()
        if raw is None:
            self._save()

    def _initial_settings(self) -> Settings:
        """Pierwsze uruchomienie: przenosimy kontakty CHANNEL_<NAZWA>=<id> z .env."""
        contacts = [
            Contact(name=key[len("CHANNEL_"):].upper(), channel_id=value.strip())
            for key, value in sorted(os.environ.items())
            if key.startswith("CHANNEL_") and len(key) > len("CHANNEL_") and value.strip()
        ]
        if contacts:
            log.info("Zaimportowano %d kontaktów z .env", len(contacts))
        return Settings(contacts=contacts)

    def get(self) -> Settings:
        with self._lock:
            return copy.deepcopy(self._settings)

    def update(self, patch: dict[str, Any]) -> Settings:
        """Scala częściowe ustawienia (np. {"voice": {"tts_rate": 10}}); listy są podmieniane w całości."""
        with self._lock:
            merged = Settings.from_dict(_deep_merge(self._settings.to_dict(), patch))
            errors = validate(merged)
            if errors:
                raise SettingsError(errors)
            self._settings = merged
            self._save()
            result = copy.deepcopy(merged)
        if self._on_change:
            self._on_change(result)
        return result

    def _save(self) -> None:
        write_json(self._path, self._settings.to_dict())


# --- sekrety ---

SECRET_KEYS = ("GROQ_API_KEY", "CEREBRAS_API_KEY", "DISCORD_USER_TOKEN")


class Secrets:
    """Dostęp do sekretów z .env. Zapis aktualizuje plik i bieżące środowisko procesu."""

    def __init__(self, env_file: Path):
        self._env_file = env_file
        self._lock = threading.Lock()
        load_dotenv(env_file)
        # zgodność wstecz: dawniej token Discorda był w USER_TOKEN
        if not os.environ.get("DISCORD_USER_TOKEN") and os.environ.get("USER_TOKEN"):
            os.environ["DISCORD_USER_TOKEN"] = os.environ["USER_TOKEN"]

    def get(self, key: str) -> str | None:
        value = os.environ.get(key, "").strip()
        return value or None

    @property
    def groq_api_key(self) -> str | None:
        return self.get("GROQ_API_KEY")

    @property
    def cerebras_api_key(self) -> str | None:
        return self.get("CEREBRAS_API_KEY")

    @property
    def discord_token(self) -> str | None:
        return self.get("DISCORD_USER_TOKEN")

    def set(self, key: str, value: str) -> None:
        if key not in SECRET_KEYS:
            raise KeyError(key)
        value = value.strip()
        with self._lock:
            self._env_file.touch(exist_ok=True)
            set_key(str(self._env_file), key, value, quote_mode="never")
            os.environ[key] = value

    def masked(self) -> dict[str, dict[str, Any]]:
        """Opis sekretów bezpieczny do wysłania do UI (bez pełnych wartości)."""
        out = {}
        for key in SECRET_KEYS:
            value = self.get(key)
            out[key] = {"set": bool(value), "hint": f"…{value[-4:]}" if value and len(value) > 8 else ""}
        return out
