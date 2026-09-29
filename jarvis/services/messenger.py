"""Messenger przez messenger.com w przeglądarce sterowanej Playwrightem.

Messenger nie ma API dla prywatnych kont, a prywatne rozmowy są szyfrowane end-to-end, więc Jarvis
korzysta ze strony messenger.com w osobnym profilu przeglądarki (data/messenger): logujesz się raz
w oknie, potem okno może być zminimalizowane. Nowe wiadomości czytamy z listy czatów (podgląd
ostatniej wiadomości) – bez otwierania rozmowy, więc u nadawcy nie pojawia się „wyświetlono”.

Playwright (API synchroniczne) działa tylko w wątku, który go uruchomił, dlatego przeglądarką
zajmuje się jeden wątek roboczy, a reszta aplikacji zleca mu zadania przez kolejkę.
"""

import logging
import queue
import re
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from jarvis.events import EventBus
from jarvis.services.inbox import Inbox
from jarvis.settings import SettingsStore, messenger_thread

log = logging.getLogger(__name__)

BASE_URL = "https://www.messenger.com"
SEND_TIMEOUT = 45.0
SETTLE_SECONDS = 5.0  # po zalogowaniu lista czatów doczytuje się chwilę – dopiero potem zapamiętujemy stan
RETRY_SECONDS = 20.0
# Ogłaszamy tylko świeże wiadomości. Podgląd zmienia się też bez nowej wiadomości, np. gdy
# Messenger doczyta historię zaszyfrowanego czatu – wtedy przy wiadomości stoi „4 godz.” albo „pon.”.
FRESH_MINUTES = 5

# Podgląd na liście czatów: nazwa, treść ostatniej wiadomości, „·” i czas („5 min”, „2 godz.”, „Właśnie teraz”)
_TIME = re.compile(
    r"(\d+\s*(s|sek\.?|m|min\.?|h|g|godz\.?|d|dni|dzień|tydz\.?|tyg\.?|w|mies\.?|r|l|lat|y|mo)|"
    r"teraz|właśnie teraz|just now|now|wczoraj|yesterday)",
    re.IGNORECASE,
)
_TIME_SUFFIX = re.compile(r"\s*·\s*([^·]{1,20})$")
_OWN_PREFIXES = ("Ty:", "You:")
# linie, które nie są treścią wiadomości (stan kontaktu, znaczniki dla czytników ekranu)
_NOISE = re.compile(
    r"^(aktywn[ya](\(-a\))?( teraz)?|active now|nieprzeczytan[aey].*|unread.*|wiadomość nieprzeczytana.*)$",
    re.IGNORECASE,
)
# komunikat zamiast podglądu w zaszyfrowanym czacie bez historii na tym urządzeniu
_PLACEHOLDER = re.compile(r"chronione przy użyciu pełnego szyfrowania|secured with end-to-end encryption", re.I)


class MessengerError(Exception):
    """Błąd z komunikatem po polsku (do wypowiedzenia/pokazania)."""


def thread_url(thread: str) -> str:
    return f"{BASE_URL}/{thread}/"


def thread_id(thread: str) -> str:
    return thread.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class Preview:
    text: str  # treść ostatniej wiadomości (bez „Ty:”)
    own: bool  # czy wysłał ją użytkownik
    # ile minut temu (None = czasu nie ma na liście); nie wchodzi do porównań – sam upływ czasu to nie zmiana
    age_minutes: float | None = field(default=None, compare=False)


def age_minutes(label: str) -> float | None:
    """„Właśnie teraz” → 0, „5 min” → 5, „2 godz.” → 120, dzień tygodnia albo data → dawno."""
    label = label.strip().lower()
    if not label:
        return None
    if label in ("teraz", "właśnie teraz", "just now", "now"):
        return 0.0
    match = re.fullmatch(r"(\d+)\s*(\S*)", label)
    unit = match.group(2).rstrip(".") if match else ""
    if match and unit in ("s", "sek"):
        return 0.0
    if match and unit in ("m", "min"):
        return float(match.group(1))
    if match and unit in ("h", "g", "godz"):
        return float(match.group(1)) * 60
    return 10_000.0  # dni, tygodnie, „pon.”, „5 wrz”


def parse_row(row_text: str) -> Preview | None:
    """Wyciąga ostatnią wiadomość z tekstu wiersza listy czatów (pierwsza linia to nazwa rozmowy).

    Czas („5 min”, „pon.”, „5 wrz”) stoi po separatorze „·” – odcinamy wszystko po nim, bo inaczej
    zmiana samego czasu wyglądałaby jak nowa wiadomość."""
    lines = [line.strip() for line in row_text.splitlines()]
    lines = [line for line in lines if line and not _NOISE.match(line)]
    body = lines[1:]
    when = ""
    if "·" in body:
        cut = len(body) - 1 - body[::-1].index("·")  # czas w osobnej linii po „·”
        body, when = body[:cut], " ".join(body[cut + 1:])
    elif body:
        suffix = _TIME_SUFFIX.search(body[-1])
        if suffix:
            body[-1], when = body[-1][: suffix.start()], suffix.group(1)
        elif len(body) > 1 and _TIME.fullmatch(body[-1]):
            when = body.pop()
    text = " ".join(part for part in body if part)
    if not text or _PLACEHOLDER.search(text):
        return None
    for prefix in _OWN_PREFIXES:
        if text.startswith(prefix):
            return Preview(text[len(prefix):].strip(), True, age_minutes(when))
    return Preview(text, False, age_minutes(when))


class PreviewTracker:
    """Porównuje kolejne odczyty listy czatów i wskazuje nowe wiadomości od kontaktów."""

    def __init__(self) -> None:
        self._last: dict[str, Preview | None] = {}  # ostatni znany podgląd (None = czatu nie było na liście)

    def update(self, rows: dict[str, str], threads: list[str]) -> list[tuple[str, Preview]]:
        """`rows` – tekst wiersza dla czatów widocznych na liście; zwraca (czat, podgląd) nowych wiadomości."""
        new = []
        for thread in threads:
            preview = parse_row(rows[thread]) if thread in rows else None
            if thread not in self._last:
                self._last[thread] = preview  # pierwszy odczyt tylko zapamiętuje stan
                continue
            if preview is None or preview == self._last[thread]:
                continue  # czat zniknął z listy albo nic się nie zmieniło – pamiętamy poprzedni podgląd
            self._last[thread] = preview
            # czat spoza listy pojawia się na niej dopiero po nowej wiadomości – to też ogłaszamy
            fresh = preview.age_minutes is None or preview.age_minutes <= FRESH_MINUTES
            if not preview.own and fresh:
                new.append((thread, preview))
        return new


class BrowserSession(Protocol):
    """Operacje na otwartej stronie messenger.com (prawdziwa: PlaywrightSession, w testach atrapa)."""

    def state(self) -> str: ...  # login | ready | loading

    def rows(self, threads: list[str]) -> dict[str, str]: ...

    def send(self, thread: str, text: str) -> None: ...

    def recent_threads(self) -> list[dict[str, str]]: ...

    def set_window(self, visible: bool) -> None: ...

    def closed(self) -> bool: ...

    def close(self) -> None: ...


Launcher = Callable[[Path, str], BrowserSession]


class MessengerService:
    """Wątek przeglądarki z Messengerem: logowanie, wysyłanie, nasłuch nowych wiadomości."""

    def __init__(
        self,
        settings: SettingsStore,
        bus: EventBus,
        inbox: Inbox,
        profile_dir: Path,
        launcher: Launcher | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._settings = settings
        self._bus = bus
        self._inbox = inbox
        self._profile_dir = profile_dir
        self._launcher = launcher or launch_browser
        self._clock = clock
        self._tasks: queue.Queue[tuple[Callable[[BrowserSession], Any], Future]] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop: threading.Event | None = None
        self._state = "off"  # off | starting | login | ready | error
        self._error = ""
        self.tick = 0.5  # co ile wątek sprawdza stronę, gdy nie ma zleceń (w testach krócej)
        bus.subscribe(lambda _: self._sync_enabled(), {"settings.changed"})

    # --- cykl życia ---

    def start(self, stop: threading.Event) -> None:
        self._stop = stop
        self._sync_enabled()

    def _sync_enabled(self) -> None:
        """Uruchamia wątek po włączeniu Messengera w ustawieniach (wyłączenie kończy go sam wątek)."""
        if self._stop is None or self._stop.is_set() or not self._settings.get().messenger.enabled:
            return
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, name="messenger", daemon=True)
            self._thread.start()

    def join(self, timeout: float) -> None:
        """Czeka, aż wątek zamknie przeglądarkę (po ustawieniu zdarzenia stop)."""
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout)

    def _enabled(self) -> bool:
        return bool(self._stop and not self._stop.is_set() and self._settings.get().messenger.enabled)

    # --- zlecenia z innych wątków ---

    def send(self, thread: str, text: str) -> None:
        if self._state == "login":
            raise MessengerError("Najpierw zaloguj się do Messengera – okno przeglądarki jest otwarte.")
        text = " ".join(text.split())  # Enter w treści wysłałby wiadomość w połowie
        self._call(lambda s: s.send(thread, text), SEND_TIMEOUT)

    def recent_threads(self) -> list[dict[str, str]]:
        return self._call(lambda s: s.recent_threads(), 15)

    def set_window(self, visible: bool) -> None:
        self._call(lambda s: s.set_window(visible), 15)

    def _call(self, fn: Callable[[BrowserSession], Any], timeout: float) -> Any:
        if not self._settings.get().messenger.enabled:
            raise MessengerError("Messenger jest wyłączony – włącz go w ustawieniach Jarvisa.")
        if self._state not in ("login", "ready"):
            raise MessengerError("Messenger jeszcze się uruchamia – spróbuj za chwilę.")
        future: Future = Future()
        self._tasks.put((fn, future))
        try:
            return future.result(timeout)
        except FutureTimeout as e:
            future.cancel()
            raise MessengerError("Messenger nie odpowiada – spróbuj za chwilę.") from e

    # --- stan ---

    @property
    def profile_dir(self) -> Path:
        """Profil przeglądarki Messengera – po nim poznajemy jej okno (np. „zamknij Chrome” go omija)."""
        return self._profile_dir

    def status(self) -> dict[str, Any]:
        return {"enabled": self._settings.get().messenger.enabled, "state": self._state, "error": self._error}

    def _set_state(self, state: str, error: str = "") -> None:
        if (state, error) == (self._state, self._error):
            return
        self._state, self._error = state, error
        self._bus.publish("messenger.status", **self.status())

    # --- wątek przeglądarki ---

    def _run(self) -> None:
        while self._enabled():
            session = None
            failed = True
            try:
                self._set_state("starting")
                session = self._launcher(self._profile_dir, self._settings.get().messenger.browser)
                self._serve(session)
                failed = False  # wyłączony w ustawieniach
            except MessengerError as e:
                log.warning("Messenger: %s", e)
                self._set_state("error", str(e))
            except Exception as e:
                log.exception("Błąd przeglądarki Messengera")
                self._set_state("error", f"Błąd przeglądarki: {e}")
            finally:
                if session:
                    try:
                        session.close()
                    except Exception:
                        log.debug("Zamykanie przeglądarki Messengera", exc_info=True)
                self._fail_pending()
            if failed and self._stop:
                self._stop.wait(RETRY_SECONDS)
        self._set_state("off")

    def _serve(self, session: BrowserSession) -> None:
        tracker = PreviewTracker()
        ready_since: float | None = None
        announced_login = False
        next_poll = 0.0
        while self._enabled():
            if session.closed():
                raise MessengerError("Okno Messengera zostało zamknięte – otwieram je ponownie.")
            settings = self._settings.get()
            state = session.state()
            if state == "login":
                ready_since = None
                if not announced_login:
                    announced_login = True
                    session.set_window(True)
                    self._bus.notice("Messenger: zaloguj się w otwartym oknie przeglądarki.", "warning")
                self._set_state("login")
            elif state == "ready":
                if ready_since is None:
                    ready_since = self._clock()
                    if announced_login:
                        self._bus.notice(
                            "Zalogowano do Messengera. Jeśli pyta o PIN do zaszyfrowanych czatów, wpisz go – "
                            "okno schowasz w Ustawieniach → Messenger.",
                            "info",
                        )
                    else:
                        session.set_window(False)  # sesja z poprzedniego uruchomienia – okno niepotrzebne
                self._set_state("ready")
                now = self._clock()
                if now - ready_since >= SETTLE_SECONDS and now >= next_poll:
                    next_poll = now + settings.messenger.poll_seconds
                    self._poll(session, tracker, settings)
            self._run_tasks(session, timeout=self.tick)

    def _poll(self, session: BrowserSession, tracker: PreviewTracker, settings: Any) -> None:
        contacts = {messenger_thread(c.messenger): c for c in settings.contacts if messenger_thread(c.messenger)}
        if not contacts:
            return
        rows = session.rows(list(contacts))
        for thread, preview in tracker.update(rows, list(contacts)):
            self._inbox.receive("messenger", contacts[thread], preview.text, settings.messenger.read_aloud)

    def _run_tasks(self, session: BrowserSession, timeout: float) -> None:
        try:
            fn, future = self._tasks.get(timeout=timeout)
        except queue.Empty:
            return
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(fn(session))
        except MessengerError as e:
            future.set_exception(e)
        except Exception as e:
            log.exception("Błąd zadania Messengera")
            future.set_exception(MessengerError(f"Nie udało się: {e}"))

    def _fail_pending(self) -> None:
        while True:
            try:
                _, future = self._tasks.get_nowait()
            except queue.Empty:
                return
            if future.set_running_or_notify_cancel():
                future.set_exception(MessengerError("Messenger został zamknięty."))


# --- prawdziwa przeglądarka (Playwright) ---

_STATE_JS = """() => {
  if (location.pathname.includes('checkpoint') || document.querySelector('input[name="pass"]')) return 'login';
  if (document.querySelector('a[href*="/t/"]')) return 'ready';
  return 'loading';
}"""

# Tylko wiersze rozmów: „/t/123/” albo „/e2ee/t/123/”. Nawigacja ma podobne linki
# („/t/123/?focus_target=…” z liczbą nieprzeczytanych, „/marketplace/t/…”, „/requests/t/…”, „/archived/t/…”).
_CHAT_HREF = r"/^\/((?:e2ee\/)?t\/(\d+))\/?$/"

_ROWS_JS = """(ids) => {
  const out = {};
  for (const a of document.querySelectorAll('a[href*="/t/"]')) {
    const m = (a.getAttribute('href') || '').match(CHAT_HREF);
    if (m && ids.includes(m[2]) && !(m[2] in out)) out[m[2]] = a.innerText || '';
  }
  return out;
}""".replace("CHAT_HREF", _CHAT_HREF)

_THREADS_JS = """() => {
  const out = [];
  const seen = new Set();
  for (const a of document.querySelectorAll('a[href*="/t/"]')) {
    const m = (a.getAttribute('href') || '').match(CHAT_HREF);
    if (!m || seen.has(m[2])) continue;
    const name = (a.innerText || '').split('\\n').map((s) => s.trim()).find(Boolean);
    if (!name) continue;
    seen.add(m[2]);
    out.push({ thread: m[1], name });
  }
  return out;
}""".replace("CHAT_HREF", _CHAT_HREF)

_COMPOSER = 'div[role="textbox"][contenteditable="true"]'


class PlaywrightSession:
    def __init__(self, playwright: Any, context: Any):
        self._pw = playwright
        self._context = context
        self._page = context.pages[0] if context.pages else context.new_page()
        self._page.goto(BASE_URL, wait_until="domcontentloaded")

    def state(self) -> str:
        try:
            return self._page.evaluate(_STATE_JS)
        except Exception:
            return "loading"  # strona w trakcie przeładowania

    def rows(self, threads: list[str]) -> dict[str, str]:
        ids = [thread_id(t) for t in threads]
        found = self._page.evaluate(_ROWS_JS, ids)
        by_id = {thread_id(t): t for t in threads}
        return {by_id[i]: text for i, text in found.items()}

    def recent_threads(self) -> list[dict[str, str]]:
        return self._page.evaluate(_THREADS_JS)

    def send(self, thread: str, text: str) -> None:
        page = self._page
        tid = thread_id(thread)
        if not re.search(rf"/t/{tid}(/|$)", page.url):
            link = page.locator(f'a[href="/t/{tid}/"], a[href="/e2ee/t/{tid}/"]').first  # wiersz czatu
            if link.count():
                link.click()  # przejście wewnątrz aplikacji – szybsze niż wczytanie strony od nowa
            else:
                page.goto(thread_url(thread), wait_until="domcontentloaded")
            page.wait_for_url(re.compile(rf"/t/{tid}(/|$)"), timeout=20000)
        composer = page.locator(_COMPOSER).last
        try:
            composer.wait_for(state="visible", timeout=20000)
        except Exception as e:
            raise MessengerError("Nie mogę otworzyć tej rozmowy na Messengerze.") from e
        composer.click()
        page.keyboard.insert_text(text)
        page.keyboard.press("Enter")
        try:
            page.wait_for_function("(el) => !el.innerText.trim()", arg=composer.element_handle(), timeout=8000)
        except Exception as e:
            raise MessengerError("Messenger nie potwierdził wysłania wiadomości.") from e

    def set_window(self, visible: bool) -> None:
        cdp = self._context.new_cdp_session(self._page)
        window = cdp.send("Browser.getWindowForTarget")
        cdp.send("Browser.setWindowBounds",
                 {"windowId": window["windowId"], "bounds": {"windowState": "normal" if visible else "minimized"}})
        if visible:
            self._page.bring_to_front()

    def closed(self) -> bool:
        return self._page.is_closed()

    def close(self) -> None:
        try:
            self._context.close()
        finally:
            self._pw.stop()


def _browser_candidates(browser: str) -> list[dict[str, str]]:
    if browser.strip():
        return [{"executable_path": browser.strip()}]
    # najpierw Chrome (wybór użytkownika), Edge tylko gdy Chrome'a nie ma
    if sys.platform == "win32":
        return [{"channel": "chrome"}, {"channel": "msedge"}, {}]
    return [{"channel": "chrome"}] + [
        {"executable_path": path}
        for path in ("/usr/bin/chromium", "/usr/bin/chromium-browser")
        if Path(path).exists()
    ] + [{}]


def launch_browser(profile_dir: Path, browser: str = "") -> BrowserSession:
    """Otwiera messenger.com w osobnym profilu (logowanie zostaje między uruchomieniami)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise MessengerError("Brak pakietu playwright – zainstaluj zależności z requirements.txt.") from e
    profile_dir.mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    errors = []
    context = None
    for candidate in _browser_candidates(browser):
        try:
            context = pw.chromium.launch_persistent_context(
                str(profile_dir),
                headless=False,  # logowanie i PIN do zaszyfrowanych czatów wymagają okna
                viewport={"width": 1280, "height": 860},  # pełny układ z podglądem wiadomości na liście czatów
                locale="pl-PL",
                # to zwykłe konto użytkownika, a nie bot – bez paska „przeglądarka sterowana automatycznie”
                # i bez znacznika navigator.webdriver, przez który Meta mogłaby zablokować konto
                ignore_default_args=["--enable-automation"],
                args=["--disable-blink-features=AutomationControlled", "--start-minimized"],
                **candidate,
            )
            break
        except Exception as e:
            errors.append(f"{candidate or 'chromium'}: {e}")
    if context is None:
        pw.stop()
        log.error("Nie udało się uruchomić przeglądarki dla Messengera: %s", errors)
        raise MessengerError(
            "Nie udało się uruchomić przeglądarki dla Messengera (Chrome, Edge ani Chromium) – "
            "szczegóły są w data/jarvis.log."
        )
    try:
        return PlaywrightSession(pw, context)
    except Exception:
        context.close()
        pw.stop()
        raise
