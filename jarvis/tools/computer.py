"""Komputer (Windows): aplikacje, strony, foldery i ustawienia, głośność i muzyka, zamykanie programów,
blokada, uśpienie, zrzut ekranu, stan komputera i minutnik.

Same gotowe czynności z naszymi, stałymi skryptami – model wybiera tylko czynność i nazwę, nigdy nie
podaje kodu. Nazwy od użytkownika trafiają do PowerShella wyłącznie przez zmienne środowiska.
"""

import contextlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from typing import Any

from jarvis.polish import join_pl
from jarvis.tools.base import Tool, ToolContext, ToolError, params

_ASCII = str.maketrans("ąćęłńóśźż", "acelnoszz")
# słowa, które model czasem dokleja do nazwy („aplikację Spotify”) – nic nie znaczą przy szukaniu
_FILLER = {"aplikacja", "aplikacje", "aplikacji", "program", "programu", "strona", "strone", "strony", "stronke",
           "folder", "folderu", "otworz", "wlacz", "uruchom", "odpal", "app"}

# strony dla aplikacji, których nie ma w menu Start (np. Instagram)
SITES = {
    "instagram": "https://www.instagram.com/",
    "facebook": "https://www.facebook.com/",
    "youtube": "https://www.youtube.com/",
    "netflix": "https://www.netflix.com/",
    "gmail": "https://mail.google.com/",
    "poczta": "https://mail.google.com/",
    "kalendarz google": "https://calendar.google.com/",
    "dysk google": "https://drive.google.com/",
    "mapy": "https://www.google.com/maps",
    "tlumacz": "https://translate.google.com/",
    "twitter": "https://x.com/",
    "tiktok": "https://www.tiktok.com/",
    "reddit": "https://www.reddit.com/",
    "allegro": "https://allegro.pl/",
    "olx": "https://www.olx.pl/",
    "chatgpt": "https://chatgpt.com/",
    "claude": "https://claude.ai/",
    "linkedin": "https://www.linkedin.com/",
    "github": "https://github.com/",
    "wikipedia": "https://pl.wikipedia.org/",
    "twitch": "https://www.twitch.tv/",
    "pinterest": "https://www.pinterest.com/",
    "disney": "https://www.disneyplus.com/",
    "prime video": "https://www.primevideo.com/",
}

# foldery użytkownika – przez nazwy powłoki, bo „Dokumenty” mogą leżeć w OneDrive
FOLDERS = {
    "pobrane": ("shell:Downloads", "Pobrane"),
    "dokumenty": ("shell:Personal", "Dokumenty"),
    "pulpit": ("shell:Desktop", "Pulpit"),
    "obrazy": ("shell:My Pictures", "Obrazy"),
    "zdjecia": ("shell:My Pictures", "Obrazy"),
    "muzyka": ("shell:My Music", "Muzyka"),
    "wideo": ("shell:My Video", "Wideo"),
    "filmy": ("shell:My Video", "Wideo"),
    "kosz": ("shell:RecycleBinFolder", "Kosz"),
    "ten komputer": ("shell:MyComputerFolder", "Ten komputer"),
    "eksplorator": ("shell:MyComputerFolder", "Ten komputer"),
}

# strony ustawień Windows
SETTINGS_PAGES = {
    "bluetooth": ("ms-settings:bluetooth", "Bluetooth"),
    "wifi": ("ms-settings:network-wifi", "Wi-Fi"),
    "wi fi": ("ms-settings:network-wifi", "Wi-Fi"),
    "siec": ("ms-settings:network", "sieć"),
    "dzwiek": ("ms-settings:sound", "dźwięk"),
    "ekran": ("ms-settings:display", "ekran"),
    "aktualizacje": ("ms-settings:windowsupdate", "aktualizacje"),
    "windows update": ("ms-settings:windowsupdate", "aktualizacje"),
    "aplikacje": ("ms-settings:appsfeatures", "aplikacje"),
    "domyslne aplikacje": ("ms-settings:defaultapps", "domyślne aplikacje"),
    "powiadomienia": ("ms-settings:notifications", "powiadomienia"),
    "zasilanie": ("ms-settings:powersleep", "zasilanie"),
    "tapeta": ("ms-settings:personalization-background", "tło pulpitu"),
    "tlo": ("ms-settings:personalization-background", "tło pulpitu"),
    "drukarki": ("ms-settings:printers", "drukarki"),
    "mysz": ("ms-settings:mousetouchpad", "mysz"),
    "data": ("ms-settings:dateandtime", "data i godzina"),
    "godzina": ("ms-settings:dateandtime", "data i godzina"),
    "prywatnosc": ("ms-settings:privacy", "prywatność"),
    "motyw": ("ms-settings:colors", "kolory i motyw"),
    "kolory": ("ms-settings:colors", "kolory i motyw"),
    "tryb ciemny": ("ms-settings:colors", "kolory i motyw"),
    "personalizacja": ("ms-settings:personalization", "personalizacja"),
}
_SETTINGS_WORDS = ("ustawienia", "ustawien", "settings")

APPS_TTL_SECONDS = 600  # lista aplikacji z menu Start – odświeżana co 10 min albo gdy czegoś nie ma
# Skróty serwisowe z menu Start (reset ustawień, odinstalowanie, naprawa) nigdy nie są „aplikacją do otwarcia”:
# „włącz ciemny motyw” trafiło kiedyś w „Reset settings” Cheat Engine'a i uruchomiło jego reset ustawień.
_SERVICE_ENTRY = re.compile(
    r"reset|uninstal|odinstal|remove|usun|repair|napraw|factory|default|reinstal|clean|wipe|format|unins\d*\.exe",
    re.IGNORECASE,
)

# klawisze multimedialne (każdy krok głośności to 2%)
VK = {"mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF, "next": 0xB0, "previous": 0xB1, "play_pause": 0xB3}
MEDIA_ACTIONS = ["volume_up", "volume_down", "set_volume", "mute", "play_pause", "next", "previous"]

_START_APPS = "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"

_CLOSE = r"""
$t = [WildcardPattern]::Escape($env:JARVIS_TARGET)
$skip = @([int]$env:JARVIS_PID)
if ($env:JARVIS_SKIP_PROFILE) {
  $p = [WildcardPattern]::Escape($env:JARVIS_SKIP_PROFILE)
  $skip += @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe' OR Name='msedge.exe'" |
    Where-Object { $_.CommandLine -like "*$p*" } | ForEach-Object { [int]$_.ProcessId })
}
Get-Process | Where-Object {
  $_.MainWindowHandle -ne 0 -and $skip -notcontains $_.Id -and $_.ProcessName -ne 'explorer' -and
  ($_.ProcessName -like "*$t*" -or $_.MainWindowTitle -like "*$t*")
} | ForEach-Object { if ($_.CloseMainWindow()) { $_.ProcessName } }
"""

_SLEEP = r"""
Add-Type -AssemblyName System.Windows.Forms
[void][System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)
"""

_SCREENSHOT = r"""
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$dpi = '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
Add-Type -Name Dpi -Namespace JarvisShot -MemberDefinition $dpi
[void][JarvisShot.Dpi]::SetProcessDPIAware()
$box = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $box.Width, $box.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($box.Left, $box.Top, 0, 0, $bmp.Size)
$dir = Join-Path ([Environment]::GetFolderPath('MyPictures')) 'Screenshots'
[void](New-Item -ItemType Directory -Force $dir)
$file = Join-Path $dir ("Jarvis " + (Get-Date -Format 'yyyy-MM-dd HH-mm-ss') + ".png")
$bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
$file
"""

_SYSTEM_INFO = r"""
$o = [ordered]@{}
$b = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | Select-Object -First 1
if ($b) { $o.battery = @{ percent = $b.EstimatedChargeRemaining; plugged = ($b.BatteryStatus -in 2, 6, 7, 8, 9) } }
$o.disks = @(Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -ne $null -and ($_.Used + $_.Free) -gt 0 } |
  ForEach-Object {
    @{ name = $_.Name; free = [math]::Round($_.Free / 1GB, 1); total = [math]::Round(($_.Used + $_.Free) / 1GB, 1) }
  })
$os = Get-CimInstance Win32_OperatingSystem
$o.memory = @{
  free = [math]::Round($os.FreePhysicalMemory / 1MB, 1); total = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
}
$o.uptime_hours = [math]::Round(((Get-Date) - $os.LastBootUpTime).TotalHours, 1)
$o.cpu = [math]::Round((Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average)
$o.ipv4 = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
  ForEach-Object { $_.IPAddress })
$o | ConvertTo-Json -Compress -Depth 4
"""


def _words(text: str) -> list[str]:
    text = text.lower().translate(_ASCII).replace("'", "").replace("’", "")
    return [w for w in re.findall(r"[a-z0-9+]+", text) if w not in _FILLER]


def _word_match(a: str, b: str) -> bool:
    # odmiana zmienia tylko końcówkę („Instagrama”, „Steama”, „pobranych”), więc słowa muszą się pokrywać
    # prawie w całości – sam wspólny początek łączyłby „Instagrama” z „Installer”
    prefix = len(os.path.commonprefix([a, b]))
    return a == b or (prefix >= 3 and prefix >= max(len(a), len(b)) - 3)


def _matches(query: list[str], name: str) -> bool:
    words = _words(name)
    return bool(query) and all(any(_word_match(q, w) for w in words) for q in query)


def _lookup(query: list[str], table: dict[str, Any]) -> Any:
    """Wpis słownika, którego wszystkie słowa klucza pasują do zapytania (najdłuższy klucz wygrywa)."""
    hits = [key for key in table if all(any(_word_match(k, q) for q in query) for k in key.split())]
    return table[max(hits, key=len)] if hits else None


def _start_apps(ctx: ToolContext, refresh: bool = False) -> list[dict[str, str]]:
    cache = ctx.state.setdefault("start_apps", {"apps": [], "at": 0.0})
    if refresh or not cache["apps"] or time.monotonic() - cache["at"] > APPS_TTL_SECONDS:
        try:
            data = json.loads(ctx.powershell(_START_APPS) or "[]")
        except (OSError, subprocess.SubprocessError, ValueError):
            data = []
        items = [data] if isinstance(data, dict) else data if isinstance(data, list) else []
        cache["apps"] = [
            {"name": str(a.get("Name", "")), "id": str(a.get("AppID", ""))}
            for a in items
            if a.get("AppID") and not _SERVICE_ENTRY.search(f"{a.get('Name', '')} {a.get('AppID', '')}")
        ]
        cache["at"] = time.monotonic()
    return cache["apps"]


def _find_app(ctx: ToolContext, query: list[str], refresh: bool = False) -> dict[str, str] | None:
    hits = [a for a in _start_apps(ctx, refresh) if _matches(query, a["name"])]
    # dokładna nazwa przed dłuższymi („Steam” przed „Steam Support Center”)
    return min(hits, key=lambda a: (_words(a["name"]) != query, len(_words(a["name"])))) if hits else None


def _run(ctx: ToolContext, fn, *args):
    try:
        return fn(*args)
    except (OSError, subprocess.SubprocessError) as e:
        raise ToolError("Nie udało się tego zrobić na komputerze.") from e


# --- otwieranie ---


def open_app(ctx: ToolContext, args: dict[str, Any]) -> str:
    target = str(args.get("target", "")).strip()
    query = _words(target)
    if not query:
        raise ToolError("Nie usłyszałem, co mam otworzyć.")
    if "jarvis" in query or "jarvisa" in query:  # „ustawienia Jarvisa” – nasz własny widok
        ctx.bus.publish("ui.navigate", view="settings")
        return "Otwieram ustawienia Jarvisa."
    domain = re.fullmatch(r"(?:https?://)?([\w-]+(?:\.[\w-]+)+)(/\S*)?", target.lower())
    if domain:  # podany adres – dokładnie ten, bez zgadywania
        ctx.open_url(target if target.lower().startswith("http") else f"https://{target}")
        return f"Otwieram stronę {domain.group(1)}."
    folder = _lookup(query, FOLDERS)
    if folder:
        _run(ctx, ctx.launch, ["explorer.exe", folder[0]])
        return f"Otwieram folder {folder[1]}."
    page = _lookup(query, SETTINGS_PAGES)
    if page:
        _run(ctx, ctx.launch, ["explorer.exe", page[0]])
        return f"Otwieram ustawienia: {page[1]}."
    if any(w in _SETTINGS_WORDS for w in query):
        # o ustawienia pytamy tylko ustawienia Windows – „settings” pasowało np. do aplikacji „Reset settings”
        _run(ctx, ctx.launch, ["explorer.exe", "ms-settings:"])
        return "Otwieram ustawienia Windows."
    site = _lookup(query, SITES)
    # aplikacja przed stroną; świeżo zainstalowanej nie ma jeszcze w pamięci – wtedy lista od nowa
    app = _find_app(ctx, query) or (None if site else _find_app(ctx, query, refresh=True))
    if app:
        if app["id"].startswith(("http://", "https://")):
            ctx.open_url(app["id"])
        else:
            _run(ctx, ctx.launch, ["explorer.exe", f"shell:AppsFolder\\{app['id']}"])
        return f"Otwieram {app['name']}."
    if site:
        ctx.open_url(site)
        return f"Otwieram {target} w przeglądarce."
    raise ToolError(f"Nie znalazłem aplikacji ani strony „{target}”.")


def close_app(ctx: ToolContext, args: dict[str, Any]) -> str:
    name = str(args.get("name", "")).strip()
    if not name:
        raise ToolError("Nie wiem, który program zamknąć.")
    if "jarvis" in name.lower():
        raise ToolError("Siebie nie zamknę – użyj przycisku zasilania.")
    profile = getattr(ctx.messenger, "profile_dir", None)
    env = {"JARVIS_TARGET": name, "JARVIS_PID": str(os.getpid()), "JARVIS_SKIP_PROFILE": str(profile or "")}
    output = _run(ctx, ctx.powershell, _CLOSE, env)
    closed = sorted({line.strip() for line in output.splitlines() if line.strip()})
    if not closed:
        raise ToolError(f"Nie widzę otwartego programu „{name}”.")
    return f"Zamykam: {join_pl(closed)}. Jeśli coś jest niezapisane, program zapyta."


# --- dźwięk ---


def media(ctx: ToolContext, args: dict[str, Any]) -> str:
    action = args.get("action")
    if action not in MEDIA_ACTIONS:
        raise ToolError("Nie wiem, co zrobić z dźwiękiem.")
    try:
        value = None if args.get("value") is None else int(args["value"])
    except (TypeError, ValueError):
        value = None
    if action == "set_volume":
        if value is None:
            raise ToolError("Na ile ustawić głośność?")
        level = max(0, min(100, value))
        # nie da się odczytać bieżącej głośności klawiszami – najpierw do zera, potem w górę
        _run(ctx, ctx.press_key, VK["volume_down"], 50)
        _run(ctx, ctx.press_key, VK["volume_up"], round(level / 2))
        return f"Głośność na {round(level / 2) * 2} procent."
    if action in ("volume_up", "volume_down"):
        step = max(2, min(100, value or 10))
        _run(ctx, ctx.press_key, VK[action], round(step / 2))
        return "Głośniej." if action == "volume_up" else "Ciszej."
    _run(ctx, ctx.press_key, VK[action], 1)
    return {"mute": "Przełączam wyciszenie.", "play_pause": "Dobrze.", "next": "Następny utwór.",
            "previous": "Poprzedni utwór."}[action]


# --- komputer ---


def pc(ctx: ToolContext, args: dict[str, Any]) -> str:
    action = args.get("action")
    if action == "lock":
        _run(ctx, ctx.launch, ["rundll32.exe", "user32.dll,LockWorkStation"])
        return "Blokuję komputer."
    if action == "sleep":
        # chwila na wypowiedzenie odpowiedzi, zanim komputer zaśnie
        threading.Timer(4, lambda: _quiet(ctx.powershell, _SLEEP)).start()
        return "Usypiam komputer."
    if action == "screenshot":
        path = _run(ctx, ctx.powershell, _SCREENSHOT).splitlines()[-1:]
        if not path:
            raise ToolError("Nie udało się zrobić zrzutu ekranu.")
        ctx.bus.notice(f"Zrzut ekranu: {path[0]}", "info")
        return "Zrobiłem zrzut ekranu – jest w Obrazach, w folderze Screenshots."
    raise ToolError("Nie wiem, co zrobić z komputerem.")


def _quiet(fn, *args) -> None:
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        fn(*args)


def system_info(ctx: ToolContext, args: dict[str, Any]) -> str:
    try:
        data = json.loads(ctx.powershell(_SYSTEM_INFO) or "{}")
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        raise ToolError("Nie udało się sprawdzić stanu komputera.") from e
    lines = []
    if battery := data.get("battery"):
        lines.append(f"Bateria {battery.get('percent')}%{' (podłączony do prądu)' if battery.get('plugged') else ''}")
    for disk in data.get("disks") or []:
        lines.append(f"Dysk {disk.get('name')}: wolne {disk.get('free')} z {disk.get('total')} GB")
    if memory := data.get("memory"):
        lines.append(f"Pamięć RAM: wolne {memory.get('free')} z {memory.get('total')} GB")
    if data.get("cpu") is not None:
        lines.append(f"Procesor: {data['cpu']}%")
    if data.get("uptime_hours") is not None:
        lines.append(f"Włączony od {data['uptime_hours']} godz.")
    if ips := data.get("ipv4"):
        lines.append(f"Adres IP: {', '.join(ips)}")
    return "; ".join(lines) or "Brak danych o komputerze."


# --- minutnik ---


def _duration(seconds: float) -> str:
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds} {_plural(seconds, 'sekundę', 'sekundy', 'sekund')}"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} {_plural(minutes, 'minutę', 'minuty', 'minut')}"
    hours, rest = divmod(minutes, 60)
    text = f"{hours} {_plural(hours, 'godzinę', 'godziny', 'godzin')}"
    return f"{text} i {rest} {_plural(rest, 'minutę', 'minuty', 'minut')}" if rest else text


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n == 1:
        return one
    return few if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else many


def timer(ctx: ToolContext, args: dict[str, Any]) -> str:
    timers: dict[int, dict[str, Any]] = ctx.state.setdefault("timers", {})
    action = args.get("action") or "set"
    label = str(args.get("label") or "").strip()
    if action == "set":
        try:
            seconds = float(args.get("minutes")) * 60
        except (TypeError, ValueError) as e:
            raise ToolError("Na ile nastawić minutnik?") from e
        seconds = max(5.0, min(seconds, 24 * 3600))
        timer_id = max(timers, default=0) + 1

        def ring() -> None:
            timers.pop(timer_id, None)
            text = f"Minął czas: {label}." if label else "Minął czas na minutniku."
            ctx.bus.notice(text, "info")
            ctx.announce(text)

        handle = threading.Timer(seconds, ring)
        handle.daemon = True
        timers[timer_id] = {"label": label, "due": time.monotonic() + seconds, "handle": handle}
        handle.start()
        return f"Minutnik na {_duration(seconds)}{f': {label}' if label else ''}."
    if action == "cancel":
        chosen = [i for i, t in timers.items() if not label or _matches(_words(label), t["label"] or "minutnik")]
        if not chosen:
            raise ToolError("Nie ma takiego minutnika.")
        for i in chosen:
            timers.pop(i)["handle"].cancel()
        return "Anulowałem minutnik." if len(chosen) == 1 else f"Anulowałem minutniki: {len(chosen)}."
    if not timers:
        return "Nie ma nastawionych minutników."
    now = time.monotonic()
    parts = [f"{t['label'] or 'minutnik'} – zostało {_duration(t['due'] - now)}" for t in timers.values()]
    return "; ".join(parts) + "."


def tools() -> list[Tool]:
    everywhere = [
        Tool(
            "timer",
            "Minutnik: set (minutes, label – np. „makaron”), cancel, list.",
            params({
                "action": {"type": "string", "enum": ["set", "cancel", "list"]},
                "minutes": {"type": "number"},
                "label": {"type": "string"},
            }),
            timer,
        ),
    ]
    if sys.platform != "win32":
        return everywhere
    return [
        *everywhere,
        Tool(
            "open_app",
            "Otwiera aplikację (z menu Start), stronę (np. Instagram), folder (Pobrane) albo ustawienia Windows.",
            params({"target": {"type": "string", "description": "np. Spotify, Instagram, Pobrane, bluetooth"}},
                   ["target"]),
            open_app,
        ),
        Tool("close_app", "Zamyka program (łagodnie – sam zapyta o zapis zmian).",
             params({"name": {"type": "string"}}, ["name"]), close_app),
        Tool(
            "media",
            "Dźwięk i muzyka w każdym odtwarzaczu (Spotify, YouTube…): głośniej/ciszej o value %, głośność na "
            "value, wycisz, pauza/wznów, następna/poprzednia piosenka.",
            params({"action": {"type": "string", "enum": MEDIA_ACTIONS}, "value": {"type": "integer"}}, ["action"]),
            media,
        ),
        Tool("pc", "Komputer: zablokuj, uśpij, zrób zrzut ekranu.",
             params({"action": {"type": "string", "enum": ["lock", "sleep", "screenshot"]}}, ["action"]), pc),
        Tool("system_info", "Stan komputera: bateria, dyski, pamięć, procesor, czas pracy, adres IP.", params(),
             system_info, speak_directly=False),
    ]
