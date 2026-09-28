"""Jarvis jako kulka na pulpicie (Windows): okno bez ramki i bez przycisku na pasku zadań.

Okno ma cały czas pełny rozmiar, a tryb „kulka” to tylko region okna w kształcie koła (SetWindowRgn –
poza nim nic nie widać i kliknięcia idą do okien pod spodem). Rozwinięcie powiększa ten region od kulki do
całego okna nad gotowym już interfejsem. Zmiana rozmiaru okna odpada: WebView2 rysuje stronę w nowym
rozmiarze z opóźnieniem ~0,5 s i przez ten czas widać czarne tło.

Kulka mieszka na pulpicie: leży tuż nad nim (HWND_BOTTOM – pod wszystkimi oknami), a gdy na wierzchu jest
pulpit (kliknięcie w tapetę, Win+D), wychodzi nad okna, żeby było ją widać. Sprawdzamy to co WATCH_SECONDS.

Pułapki, na które już wpadliśmy:
- WebView2 rysuje stronę w osobnym procesie, więc przezroczystość okna (transparent, TransparencyKey)
  daje tylko ciemny prostokąt. Kształt koła da wyłącznie region okna.
- Przy ciemnym motywie pywebview włącza tło Mica, a DWM rysuje je także poza regionem (szary kwadrat
  wokół kulki). Wyłączamy je – i ponownie po każdym UserPreferenceChanged, bo pywebview włącza je wtedy znów.
- Przycisku na pasku nie ma, bo okno ma niewidocznego właściciela (okna posiadane nie trafiają na pasek).
  WS_EX_TOOLWINDOW dokładamy tylko kulce – zabiera też miejsce w Alt+Tab, a pełne okno ma tam zostać.

Współrzędne to piksele Win32 (proces jest „system DPI aware” – tak ustawia go pywebview), dlatego całą
geometrię liczymy sami przez Win32; stronie podajemy je w pikselach CSS (podzielone przez skalę).
"""

import ctypes
import ctypes.wintypes as wt
import logging
import math
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jarvis.jsonfile import read_json, write_json

log = logging.getLogger(__name__)

ORB_SIZE = 112  # średnica kulki przy 100% skalowania
FULL_SIZE = (1180, 760)
BIG_ORB = (0.35, 0.448)  # typowy środek dużej kuli w widoku Jarvis (ułamek okna), zanim ją zmierzymy
SCREEN_MARGIN = 16
ANIMATION_SECONDS = 0.26
WATCH_SECONDS = 0.2
LAYOUT_TIMEOUT = 0.6
DESKTOP_CLASSES = ("Progman", "WorkerW")  # okna pulpitu Eksploratora
# pasek zadań, Start, Alt+Tab i wysuwane panele – nie zmieniają tego, czy kulka jest nad oknami
NEUTRAL_CLASSES = ("Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow",
                   "XamlExplorerHostIslandWindow", "NotifyIconOverflowWindow", "TopLevelWindowForOverflowXamlIsland")

# Środek dużej kuli z widoku Jarvis w pikselach okna – albo null, gdy widać inny widok.
_BIG_ORB_JS = """(function () {
  var box = document.getElementById('orb-wrap');
  var r = box && box.getBoundingClientRect();
  var k = window.devicePixelRatio || 1;
  return r && r.width > 0 ? [(r.left + r.width / 2) * k, (r.top + r.height / 2) * k] : null;
})()"""

Rect = tuple[int, int, int, int]  # x, y, szerokość, wysokość


# --- czysta geometria (testowana bez okien) ---


def fit_rect(cx: float, cy: float, width: int, height: int, work: Rect, margin: int = SCREEN_MARGIN) -> Rect:
    """Prostokąt o środku w (cx, cy), przesunięty tak, żeby zmieścił się w obszarze roboczym ekranu."""
    wx, wy, ww, wh = work
    width = min(width, ww - 2 * margin)
    height = min(height, wh - 2 * margin)
    x = min(max(round(cx - width / 2), wx + margin), wx + ww - margin - width)
    y = min(max(round(cy - height / 2), wy + margin), wy + wh - margin - height)
    return x, y, width, height


def placement(home: tuple[float, float], big: tuple[float, float], size: tuple[int, int], work: Rect) -> Rect:
    """Pełne okno ustawione tak, żeby duża kula z widoku Jarvis wypadła w miejscu kulki (home) – o ile mieści się
    na ekranie; kulka rozwija się wtedy „z siebie”."""
    width, height = size
    return fit_rect(home[0] - big[0] + width / 2, home[1] - big[1] + height / 2, width, height, work)


def cover_radius(cx: float, cy: float, width: int, height: int) -> float:
    """Promień koła o środku (cx, cy), które zakrywa cały prostokąt 0..width × 0..height."""
    return math.hypot(max(cx, width - cx), max(cy, height - cy)) + 2


def ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


# --- Win32 ---


class _Rect(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG), ("right", wt.LONG), ("bottom", wt.LONG)]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", _Rect), ("rcWork", _Rect), ("dwFlags", wt.DWORD)]


class _Margins(ctypes.Structure):
    _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int), ("top", ctypes.c_int), ("bottom", ctypes.c_int)]


GWL_EXSTYLE = -20
GWLP_HWNDPARENT = -8
WS_EX_TOOLWINDOW = 0x80
WS_EX_APPWINDOW = 0x40000
HWND_TOPMOST, HWND_NOTOPMOST, HWND_BOTTOM = -1, -2, 1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x4, 0x10, 0x20
SW_SHOWNOACTIVATE = 4
MONITOR_DEFAULTTONULL, MONITOR_DEFAULTTOPRIMARY, MONITOR_DEFAULTTONEAREST = 0, 1, 2
DWMWA_WINDOW_CORNER_PREFERENCE, DWMWA_BORDER_COLOR, DWMWA_SYSTEMBACKDROP_TYPE = 33, 34, 38
DWMWCP_DONOTROUND, DWMWCP_ROUND = 1, 2
DWMWA_COLOR_NONE, DWMWA_COLOR_DEFAULT = 0xFFFFFFFE, 0xFFFFFFFF
DWMSBT_NONE = 1
TPM_RIGHTBUTTON, TPM_NONOTIFY, TPM_RETURNCMD = 0x2, 0x80, 0x100
MF_STRING, MF_SEPARATOR = 0x0, 0x800


def _winapi():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32")
    dwmapi = ctypes.WinDLL("dwmapi")
    h = wt.HWND
    user32.GetWindowRect.argtypes = [h, ctypes.POINTER(_Rect)]
    user32.SetWindowPos.argtypes = [h, h, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
    user32.SetWindowRgn.argtypes = [h, wt.HRGN, wt.BOOL]
    user32.GetWindowLongPtrW.argtypes = [h, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [h, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, h, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
    user32.CreateWindowExW.restype = h
    user32.MonitorFromWindow.argtypes = [h, wt.DWORD]
    user32.MonitorFromWindow.restype = wt.HMONITOR
    user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
    user32.MonitorFromPoint.restype = wt.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.POINTER(_MonitorInfo)]
    user32.GetForegroundWindow.restype = h
    user32.GetClassNameW.argtypes = [h, wt.LPWSTR, ctypes.c_int]
    user32.IsIconic.argtypes = [h]
    user32.ShowWindow.argtypes = [h, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [h]
    user32.CreatePopupMenu.restype = wt.HMENU
    user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
    user32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, h, wt.LPVOID]
    user32.DestroyMenu.argtypes = [wt.HMENU]
    user32.PostMessageW.argtypes = [h, wt.UINT, wt.WPARAM, wt.LPARAM]
    gdi32.CreateEllipticRgn.restype = wt.HRGN
    gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
    dwmapi.DwmSetWindowAttribute.argtypes = [h, wt.DWORD, wt.LPCVOID, wt.DWORD]
    dwmapi.DwmExtendFrameIntoClientArea.argtypes = [h, ctypes.POINTER(_Margins)]
    return user32, gdi32, dwmapi


def _dark_menus() -> None:
    """Ciemne menu kontekstowe jak w Eksploratorze (nieudokumentowane SetPreferredAppMode z uxtheme)."""
    try:
        uxtheme = ctypes.WinDLL("uxtheme")
        uxtheme[135](2)  # SetPreferredAppMode(ForceDark)
        uxtheme[136]()  # FlushMenuThemes
    except (OSError, AttributeError):
        log.debug("Brak ciemnych menu", exc_info=True)


class DesktopWindow:
    """Tryby kulka/pełny dla okna pywebview. Metody publiczne woła strona (window.pywebview.api.*)."""

    def __init__(self, state_file: Path, on_menu: Callable[[str], None]):
        self._user32, self._gdi32, self._dwm = _winapi()
        self._user32.SetProcessDPIAware()  # to samo robi pywebview – liczymy piksele w tym samym układzie
        self._state_file = state_file
        self._on_menu = on_menu
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self.window = None
        self.hwnd = 0
        self.mode = "orb"
        self._raised: bool | None = None  # kulka nad oknami (pulpit na wierzchu) czy tuż nad pulpitem
        self._restore: Rect | None = None  # położenie przed rozciągnięciem na cały ekran
        self._scale = (self._user32.GetDpiForSystem() or 96) / 96
        self._orb = round(ORB_SIZE * self._scale)
        self._full = (round(FULL_SIZE[0] * self._scale), round(FULL_SIZE[1] * self._scale))
        state = read_json(state_file, {})
        big = state.get("big")
        self._big_ratio = tuple(big) if _pair(big, float) and all(0 < v < 1 for v in big) else BIG_ORB
        home = self._valid_home(state.get("orb"))
        self.rect = placement(home, self._big_estimate(self._full), self._full, self._work_at(home))
        self.offset = (home[0] - self.rect[0], home[1] - self.rect[1])  # środek kulki w oknie

    def create(self, webview, url: str):
        """Tworzy okno pywebview od razu w trybie kulki (położenie kulki dostaje też strona – bez mignięcia)."""
        s = self._scale
        x, y, w, h = self.rect
        ox, oy = self.offset
        window = webview.create_window(
            "Jarvis",
            f"{url}?desktop=orb&ox={ox / s:.1f}&oy={oy / s:.1f}&os={self._orb / s:.1f}",
            width=round(w / s),
            height=round(h / s),
            x=round(x / s),
            y=round(y / s),
            min_size=(40, 40),
            frameless=True,
            easy_drag=False,  # przeciąga tylko kulka i pasek u góry (.pywebview-drag-region)
            shadow=False,
            background_color="#05070d",
        )
        self.window = window
        window.events.before_show += self._setup
        window.events.closed += self._closed.set
        window.expose(self.desktop_state, self.expand, self.collapse, self.orb_moved, self.toggle_maximize,
                      self.orb_menu, self.quit)
        return window

    # --- API dla strony ---

    def desktop_state(self) -> dict[str, Any]:
        s = self._scale
        return {"desktop": True, "mode": self.mode,
                "orb": [self.offset[0] / s, self.offset[1] / s, self._orb / s]}

    def expand(self) -> None:
        with self._lock:
            if self.mode == "full":
                self._focus()
                return
            self.mode = "full"
            x, y, w, h = self._rect()
            ox, oy = self.offset
            home = (x + ox, y + oy)
            big = self._measure_big_orb(w, h)
            tx, ty, _, _ = placement(home, big, (w, h), self._work_at(home))
            if (tx, ty) != (x, y):
                # pełne okno nie mieści się na ekranie wokół kulki – przestawiamy je (kulka na mgnienie znika)
                self._set_region(ox, oy, 1)
                self._user32.SetWindowPos(self.hwnd, None, tx, ty, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                ox, oy = self.offset = (home[0] - tx, home[1] - ty)
                self._send_orb()
            self._set_page_mode("full")
            self._set_toolwindow(False)
            self._focus()  # np. „otwórz kalendarz” głosem, gdy kulka leży pod oknami – rozwija się na wierzchu
            self._animate(ox, oy, self._orb / 2, cover_radius(ox, oy, w, h))
            self._user32.SetWindowRgn(self.hwnd, None, True)
            self._apply_frame()
            self._restore = None
            self._raised = None
            self._focus()

    def collapse(self) -> None:
        with self._lock:
            if self.mode == "orb":
                return
            if self._restore:  # zwijamy z rozciągniętego – najpierw zwykły rozmiar, żeby kulka wróciła na miejsce
                x, y, w, h = self._restore
                self._restore = None
                self._user32.SetWindowPos(self.hwnd, None, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE)
            self.mode = "orb"
            x, y, w, h = self._rect()
            ox, oy = self.offset
            self._set_page_mode("orb")
            self._apply_frame()
            self._animate(ox, oy, cover_radius(ox, oy, w, h), self._orb / 2)
            self._set_toolwindow(True)
            home = (x + ox, y + oy)
            if not self._on_screen(home):  # pełne okno przeciągnięte tak, że kulka wypadłaby poza ekran
                self._place_orb(self._valid_home(None))
            self._save_home()
            self._raised = None
            self._update_layer()

    def orb_moved(self) -> None:
        """Koniec przeciągania kulki – zapamiętujemy, gdzie ma mieszkać."""
        if self.mode == "orb":
            self._save_home()

    def toggle_maximize(self) -> None:
        """Podwójne kliknięcie paska: cały obszar roboczy ekranu albo z powrotem (okno bez ramki nie ma krawędzi)."""
        with self._lock:
            if self.mode != "full":
                return
            if self._restore:
                x, y, w, h = self._restore
                self._restore = None
            else:
                self._restore = self._rect()
                x, y, w, h = self._work_at(self._center())
            self._user32.SetWindowPos(self.hwnd, None, x, y, w, h, SWP_NOZORDER)

    def orb_menu(self) -> None:
        """Prawy klik na kulce – systemowe menu (w kulce nie zmieści się menu z HTML-a)."""
        items = [("open", "Otwórz Jarvisa"), ("settings", "Ustawienia"), None, ("quit", "Zamknij Jarvisa")]
        chosen: list[str] = []

        def show() -> None:
            u = self._user32
            menu = u.CreatePopupMenu()
            for i, item in enumerate(items, start=1):
                if item is None:
                    u.AppendMenuW(menu, MF_SEPARATOR, 0, None)
                else:
                    u.AppendMenuW(menu, MF_STRING, i, item[1])
            point = wt.POINT()
            u.GetCursorPos(ctypes.byref(point))
            u.SetForegroundWindow(self.hwnd)  # inaczej menu nie znika po kliknięciu obok
            cmd = u.TrackPopupMenu(menu, TPM_RETURNCMD | TPM_NONOTIFY | TPM_RIGHTBUTTON, point.x, point.y, 0,
                                   self.hwnd, None)
            u.PostMessageW(self.hwnd, 0, 0, 0)  # WM_NULL
            u.DestroyMenu(menu)
            if cmd and items[cmd - 1]:
                chosen.append(items[cmd - 1][0])

        self._invoke(show)
        if chosen:
            self._on_menu(chosen[0])

    def quit(self) -> None:
        self.window.destroy()

    # --- przygotowanie okna i warstwa pulpitu ---

    def _setup(self) -> None:
        """before_show: na wątku okna, zanim pokaże się pierwszy raz – bez mignięcia prostokąta."""
        u = self._user32
        self.hwnd = int(self.window.native.Handle.ToInt64())
        # niewidoczny właściciel = brak przycisku na pasku zadań
        owner = u.CreateWindowExW(0, "STATIC", "Jarvis", 0, 0, 0, 0, 0, None, None, None, None)
        u.SetWindowLongPtrW(self.hwnd, GWLP_HWNDPARENT, owner or 0)
        ex = u.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        u.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ex & ~WS_EX_APPWINDOW)
        self._set_toolwindow(True)
        x, y, w, h = self.rect
        u.SetWindowPos(self.hwnd, HWND_BOTTOM, x, y, w, h, SWP_NOACTIVATE)
        self._apply_frame()
        self._set_region(*self.offset, self._orb / 2)
        _dark_menus()
        try:
            from Microsoft.Win32 import SystemEvents  # pythonnet – jest razem z pywebview

            SystemEvents.UserPreferenceChanged += lambda *_: self._apply_frame()
        except Exception:
            log.debug("Nie podpiąłem UserPreferenceChanged", exc_info=True)
        threading.Thread(target=self._watch, name="desktop-layer", daemon=True).start()

    def _watch(self) -> None:
        while not self._closed.wait(WATCH_SECONDS):
            if self.mode == "orb" and self._lock.acquire(blocking=False):
                try:
                    self._update_layer()
                finally:
                    self._lock.release()

    def _update_layer(self) -> None:
        """Kulka nad oknami, gdy na wierzchu jest pulpit (albo sama kulka); inaczej tuż nad pulpitem, pod oknami."""
        u = self._user32
        foreground = u.GetForegroundWindow()
        if not foreground:
            return  # chwila przełączania (np. Win+D) – zostawiamy jak jest
        if foreground == self.hwnd:
            raised = True
        else:
            name = ctypes.create_unicode_buffer(64)
            u.GetClassNameW(foreground, name, 64)
            if name.value in NEUTRAL_CLASSES:
                return
            raised = name.value in DESKTOP_CLASSES
        if u.IsIconic(self.hwnd):  # „pokaż pulpit” potrafi zminimalizować wszystko
            u.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self._raised = None
        if raised != self._raised:
            self._raised = raised
            u.SetWindowPos(self.hwnd, HWND_TOPMOST if raised else HWND_BOTTOM, 0, 0, 0, 0,
                           SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def _apply_frame(self) -> None:
        """Wygląd ramki DWM dla bieżącego trybu (pełny: cień i zaokrąglone rogi; kulka: nic)."""
        full = self.mode == "full"
        self._dwm_attr(DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_NONE)
        self._dwm_attr(DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND if full else DWMWCP_DONOTROUND)
        self._dwm_attr(DWMWA_BORDER_COLOR, DWMWA_COLOR_DEFAULT if full else DWMWA_COLOR_NONE)
        margin = 1 if full else 0
        self._dwm.DwmExtendFrameIntoClientArea(self.hwnd, ctypes.byref(_Margins(margin, margin, margin, margin)))

    # --- pomocnicze ---

    def _animate(self, cx: float, cy: float, r0: float, r1: float) -> None:
        start = time.perf_counter()
        while True:
            t = min(1.0, (time.perf_counter() - start) / ANIMATION_SECONDS)
            self._set_region(cx, cy, r0 + (r1 - r0) * ease_out(t))
            if t >= 1:
                return
            time.sleep(1 / 120)

    def _set_region(self, cx: float, cy: float, r: float) -> None:
        region = self._gdi32.CreateEllipticRgn(round(cx - r), round(cy - r), round(cx + r) + 1, round(cy + r) + 1)
        if not self._user32.SetWindowRgn(self.hwnd, region, True):
            self._gdi32.DeleteObject(region)  # po udanym wywołaniu region należy do systemu

    def _place_orb(self, home: tuple[float, float]) -> None:
        """Przestawia okno tak, żeby kulka stała w `home` (np. gdy zniknęła za krawędzią ekranu)."""
        _, _, w, h = self._rect()
        x, y, w, h = placement(home, self._big_estimate((w, h)), (w, h), self._work_at(home))
        self._set_region(*self.offset, 1)
        self._user32.SetWindowPos(self.hwnd, None, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        self.offset = (home[0] - x, home[1] - y)
        self._send_orb()
        self._set_region(*self.offset, self._orb / 2)

    def _measure_big_orb(self, w: int, h: int) -> tuple[float, float]:
        """Środek dużej kuli (piksele okna); pomiar zapamiętujemy, bo przyda się przy następnym starcie."""
        try:
            value = self.window.evaluate_js(_BIG_ORB_JS)
        except Exception:
            value = None
        if _pair(value, (int, float)):
            ratio = (value[0] / w, value[1] / h)
            if all(0 < v < 1 for v in ratio) and ratio != self._big_ratio:
                self._big_ratio = ratio
                self._save_home()
            return float(value[0]), float(value[1])
        return self._big_estimate((w, h))

    def _big_estimate(self, size: tuple[int, int]) -> tuple[float, float]:
        return self._big_ratio[0] * size[0], self._big_ratio[1] * size[1]

    def _save_home(self) -> None:
        x, y, _, _ = self._rect() if self.hwnd else self.rect
        home = [round(x + self.offset[0]), round(y + self.offset[1])]
        write_json(self._state_file, {"orb": home, "big": [round(v, 4) for v in self._big_ratio]})

    def _valid_home(self, saved: Any) -> tuple[float, float]:
        """Zapamiętany środek kulki – o ile nadal leży na którymś ekranie; inaczej środek głównego ekranu."""
        if _pair(saved, int) and self._on_screen(saved):
            return float(saved[0]), float(saved[1])
        wx, wy, ww, wh = self._monitor_work(self._user32.MonitorFromPoint(wt.POINT(0, 0), MONITOR_DEFAULTTOPRIMARY))
        return wx + ww / 2, wy + wh / 2

    def _on_screen(self, point) -> bool:
        return bool(self._user32.MonitorFromPoint(wt.POINT(round(point[0]), round(point[1])), MONITOR_DEFAULTTONULL))

    def _work_at(self, point) -> Rect:
        return self._monitor_work(
            self._user32.MonitorFromPoint(wt.POINT(round(point[0]), round(point[1])), MONITOR_DEFAULTTONEAREST)
        )

    def _monitor_work(self, monitor) -> Rect:
        info = _MonitorInfo()
        info.cbSize = ctypes.sizeof(_MonitorInfo)
        self._user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        r = info.rcWork
        return r.left, r.top, r.right - r.left, r.bottom - r.top

    def _set_toolwindow(self, on: bool) -> None:
        u = self._user32
        ex = u.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        u.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ex | WS_EX_TOOLWINDOW if on else ex & ~WS_EX_TOOLWINDOW)
        u.SetWindowPos(self.hwnd, None, 0, 0, 0, 0,
                       SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)

    def _set_page_mode(self, mode: str) -> None:
        self._js(f"window.jarvisDesktop && window.jarvisDesktop.setMode('{mode}')")

    def _send_orb(self) -> None:
        s = self._scale
        ox, oy = self.offset
        args = f"{ox / s:.1f}, {oy / s:.1f}, {self._orb / s:.1f}"
        self._js(f"window.jarvisDesktop && window.jarvisDesktop.setOrb({args})")

    def _js(self, script: str) -> None:
        try:
            self.window.evaluate_js(script)
        except Exception:
            log.debug("Strona nie przyjęła: %s", script, exc_info=True)

    def _focus(self) -> None:
        # zdejmowanie i nakładanie „zawsze na wierzchu” wyciąga okno na przód także spoza aktywnej aplikacji
        u = self._user32
        flags = SWP_NOMOVE | SWP_NOSIZE
        u.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        u.SetWindowPos(self.hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        u.SetForegroundWindow(self.hwnd)

    def _invoke(self, fn: Callable[[], None]) -> None:
        """Uruchamia fn na wątku okna (menu systemowe musi należeć do wątku, który ma okno)."""
        from System import Action  # pythonnet

        self.window.native.Invoke(Action(fn))

    def _rect(self) -> Rect:
        r = _Rect()
        self._user32.GetWindowRect(self.hwnd, ctypes.byref(r))
        return r.left, r.top, r.right - r.left, r.bottom - r.top

    def _center(self) -> tuple[float, float]:
        x, y, w, h = self._rect()
        return x + w / 2, y + h / 2

    def _dwm_attr(self, attribute: int, value: int) -> None:
        v = wt.DWORD(value)
        self._dwm.DwmSetWindowAttribute(self.hwnd, attribute, ctypes.byref(v), ctypes.sizeof(v))


def _pair(value: Any, kind) -> bool:
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and all(isinstance(v, kind) and not isinstance(v, bool) for v in value))
