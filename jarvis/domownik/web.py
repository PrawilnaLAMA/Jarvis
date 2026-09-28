"""Domownik - trasy HTTP (strony, API, PWA, strumien zmian).

Aplikacje sklada `create_app(data_file)`; serwer (waitress) uruchamia
`jarvis.services.domownik_server.DomownikServer`.
"""

from __future__ import annotations

import io
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import (
    Blueprint,
    Flask,
    Response,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
    send_from_directory,
)
from markupsafe import Markup
from werkzeug.exceptions import HTTPException

from . import chores as core
from . import grafik, planer, shopping
from .storage import Store
from .sync import Broadcaster

log = logging.getLogger(__name__)

MAX_GRAFIK = 8 * 1024 * 1024  # grafik miesieczny wazy ~200 kB, wiec to duzy zapas
PACKAGE_DIR = Path(__file__).resolve().parent

bp = Blueprint("dom", __name__)


def create_app(data_file: Path) -> Flask:
    """Aplikacja Domownika nad plikiem danych `data_file`.

    Przy pustym, nieoznaczonym stanie wsypuje przykladowe obowiazki (bootstrap)."""
    app = Flask(
        __name__,
        template_folder=str(PACKAGE_DIR / "templates"),
        static_folder=str(PACKAGE_DIR / "static"),
    )
    app.json.ensure_ascii = False
    # Kolejnosc slownikow cos u nas znaczy - dzialy sklepu maja isc tak, jak sie idzie
    # przez sklep, a nie od A do Z. Sortowanie trzeba wylaczyc w DWOCH miejscach:
    # w JSON-ie z API (app.json) i w filtrze |tojson w szablonach (polityka Jinji,
    # ktora ma wlasne, domyslnie wlaczone sort_keys).
    app.json.sort_keys = False
    app.jinja_env.policies["json.dumps_kwargs"] = {"sort_keys": False}
    app.jinja_env.globals["icon"] = _icon

    store = Store(data_file)
    # Kazdy zapis budzi przegladarki wiszace na /api/zmiany (natychmiastowa synchronizacja).
    zmiany = Broadcaster()
    store.on_change = zmiany.bump
    app.extensions["domownik"] = {"store": store, "zmiany": zmiany}
    app.register_blueprint(bp)
    _bootstrap(store)
    return app


def _icon(name: str) -> Markup:
    """Ikona ze sprite'a templates/_ikony.html (nazwy wpisane w szablonach, nie od uzytkownika)."""
    return Markup(f'<svg class="icon" aria-hidden="true" focusable="false"><use href="#i-{name}"/></svg>')


def _store() -> Store:
    return current_app.extensions["domownik"]["store"]


def _zmiany() -> Broadcaster:
    return current_app.extensions["domownik"]["zmiany"]


def today() -> date:
    """Dzien 'dzisiejszy' - mozna nadpisac ?dzis=RRRR-MM-DD do testow."""
    override = request.args.get("dzis")
    if override:
        try:
            return date.fromisoformat(override)
        except ValueError:
            pass
    return date.today()


def plan_dla(state: dict, od: date, do: date) -> dict:
    """Plan ulozony przez planer dla okna, ktore i tak zaraz narysujemy.

    Liczony raz na zadanie i podawany dalej do agenda()/month_grid() - te same
    rozstrzygniecia musza obowiazywac we wszystkich widokach naraz."""
    return planer.rozklad(state, od, do, today())


def _bootstrap(store: Store) -> None:
    """Przy pierwszym starcie wrzuca kilka przykladowych obowiazkow."""
    with store.edit() as state:
        if not state["settings"].get("seeded") and not state["chores"]:
            state["chores"] = core.seed_examples(date.today())
            state["settings"]["seeded"] = True


def _page(template: str, page: str, **extra):
    # base.html trzyma wspolny modal obowiazku - potrzebuje categories i people na KAZDEJ stronie
    return render_template(template, page=page, categories=core.CATEGORIES, people=core.PEOPLE, **extra)


# ------------------------------------------------------------------ strony --


@bp.get("/")
def page_home():
    return _page("index.html", "home")


@bp.get("/kalendarz")
def page_calendar():
    return _page("calendar.html", "calendar")


@bp.get("/obowiazki")
def page_chores():
    return _page("chores.html", "chores")


@bp.get("/zakupy")
def page_shopping():
    return _page("shopping.html", "shopping", shop_categories=shopping.CATEGORIES)


# ------------------------------------------------- aplikacja na telefonie --


@bp.get("/manifest.webmanifest")
def pwa_manifest():
    """Opis aplikacji dla telefonu (ikona, nazwa, kolory, pelny ekran).

    Podajemy typ jawnie - Windows nie zna rozszerzenia .webmanifest i bez tego
    oddalby plik jako zwykly tekst, a przegladarka by go odrzucila."""
    return send_from_directory(
        current_app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json"
    )


@bp.get("/sw.js")
def pwa_service_worker():
    """Service worker MUSI byc podany z glownego adresu.

    Plik lezy w static/, ale worker serwowany z /static/sw.js obejmowalby swoim
    zasiegiem tylko /static/ - czyli nie kontrolowalby zadnej strony aplikacji."""
    res = send_from_directory(current_app.static_folder, "sw.js", mimetype="text/javascript")
    res.headers["Service-Worker-Allowed"] = "/"
    res.headers["Cache-Control"] = "no-cache"  # sam worker nigdy nie moze byc stary
    return res


# --------------------------------------------------------------------- api --


@bp.get("/api/slowniki")
def api_dictionaries():
    return jsonify(
        {
            "categories": core.CATEGORIES,
            "priorities": core.PRIORITIES,
            "people": core.PEOPLE,
            "weekdays": core.WEEKDAYS,
            "weekdays_short": core.WEEKDAYS_SHORT,
        }
    )


@bp.get("/api/agenda")
def api_agenda():
    state = _store().load()
    now = today()
    try:
        days = max(1, min(31, int(request.args.get("dni", 7))))
    except ValueError:
        days = 7
    start = core.parse_date(request.args.get("od", now.isoformat()), "data startu")
    # okno planu obejmuje takze zaleglosci (3 tygodnie wstecz), bo one tez pokazuja,
    # kto mial dana rzecz zrobic
    plan = plan_dla(state, min(start, now) - timedelta(days=21), start + timedelta(days=days))
    data = core.agenda(state, start, days, now, plan)
    data["stats"] = core.stats(state, now)
    data["grafik"] = grafik.widok(state, now, start + timedelta(days=days))
    return jsonify(data)


@bp.get("/api/dzien/<day>")
def api_day(day: str):
    state = _store().load()
    now = today()
    dzien = core.parse_date(day)
    plan = plan_dla(state, dzien, dzien)
    return jsonify(core.day_summary(state, dzien, now, plan))


def _year_month(now: date) -> tuple[int, int]:
    try:
        year = int(request.args.get("rok", now.year))
        month = int(request.args.get("miesiac", now.month))
    except ValueError:
        raise core.ValidationError("Rok i miesiąc muszą być liczbami.") from None
    if not 1 <= month <= 12 or not 1970 <= year <= 2200:
        raise core.ValidationError("Nieprawidłowy rok lub miesiąc.")
    return year, month


@bp.get("/api/miesiac")
def api_month():
    state = _store().load()
    now = today()
    year, month = _year_month(now)
    od, do = core.month_range(year, month)
    plan = plan_dla(state, od, do)
    data = core.month_grid(state, year, month, now, plan)
    data["grafik"] = grafik.widok(state, od, do)
    data["dlugi"] = planer.podsumowanie_dlugow(state, plan)
    data["grafik_miesiac"] = f"{year:04d}-{month:02d}"
    data["grafik_wczytany"] = {
        osoba: grafik.miesiac_znany(state, osoba, f"{year:04d}-{month:02d}") for osoba in core.PEOPLE
    }
    return jsonify(data)


@bp.get("/api/obowiazki")
def api_chores_list():
    state = _store().load()
    now = today()
    items = []
    for chore in state["chores"]:
        view = dict(chore)
        cat = core.CATEGORIES.get(chore.get("category"), core.CATEGORIES[core.DEFAULT_CATEGORY])
        view["category_label"] = cat["label"]
        view["color"] = core.display_color(chore)
        przypisane = core.assignees_of(chore)
        view["assignees"] = przypisane
        view["assignees_label"] = core.assignees_label(przypisane)
        view["na_zmiane"] = len(przypisane) > 1
        view["repeat_label"] = core.repeat_label(chore)
        view["next_date"] = _next_occurrence(chore, now)
        view["done_count"] = len(state["completions"].get(chore["id"], []))
        items.append(view)
    items.sort(key=lambda c: (c["archived"], c["title"].lower()))
    return jsonify({"chores": items, "stats": core.stats(state, now)})


def _next_occurrence(chore: dict, now: date) -> str | None:
    for offset in range(0, 400):
        day = now + timedelta(days=offset)
        if core.occurs_on(chore, day):
            return day.isoformat()
    return None


def _not_found(message: str):
    return jsonify({"error": message}), 404


NO_CHORE = "Nie znaleziono takiego obowiązku."
NO_ITEM = "Nie ma takiej rzeczy na liście."


@bp.get("/api/obowiazki/<chore_id>")
def api_chore_detail(chore_id: str):
    chore = core.find_chore(_store().load(), chore_id)
    if chore is None:
        return _not_found(NO_CHORE)
    return jsonify(chore)


@bp.post("/api/obowiazki")
def api_chore_create():
    payload = request.get_json(silent=True) or {}
    chore = core.normalize_chore(payload)
    with _store().edit() as state:
        state["chores"].append(chore)
    return jsonify(chore), 201


@bp.put("/api/obowiazki/<chore_id>")
def api_chore_update(chore_id: str):
    payload = request.get_json(silent=True) or {}
    with _store().edit() as state:
        existing = core.find_chore(state, chore_id)
        if existing is None:
            return _not_found(NO_CHORE)
        updated = core.normalize_chore(payload, existing)
        state["chores"] = [updated if c["id"] == chore_id else c for c in state["chores"]]
    return jsonify(updated)


@bp.delete("/api/obowiazki/<chore_id>")
def api_chore_delete(chore_id: str):
    with _store().edit() as state:
        before = len(state["chores"])
        state["chores"] = [c for c in state["chores"] if c["id"] != chore_id]
        if len(state["chores"]) == before:
            return _not_found(NO_CHORE)
        state["completions"].pop(chore_id, None)
    return jsonify({"ok": True})


@bp.post("/api/odhacz")
def api_toggle_done():
    payload = request.get_json(silent=True) or {}
    chore_id = str(payload.get("id", ""))
    day = core.parse_date(payload.get("date", date.today().isoformat()))
    done = bool(payload.get("done", True))

    with _store().edit() as state:
        if core.find_chore(state, chore_id) is None:
            return _not_found(NO_CHORE)
        core.set_done(state, chore_id, day, done)
        result = {
            "id": chore_id,
            "date": day.isoformat(),
            "done": done,
            "stats": core.stats(state, today()),
        }
    return jsonify(result)


# ------------------------------------------------------------------ zakupy --


@bp.get("/api/zakupy")
def api_shopping_list():
    state = _store().load()
    return jsonify({"items": shopping.items_view(state), "stats": shopping.stats(state)})


@bp.post("/api/zakupy")
def api_shopping_create():
    payload = request.get_json(silent=True) or {}
    item = shopping.normalize_item(payload)
    with _store().edit() as state:
        state.setdefault("shopping", []).append(item)
    return jsonify(shopping.item_view(item)), 201


@bp.put("/api/zakupy/<item_id>")
def api_shopping_update(item_id: str):
    payload = request.get_json(silent=True) or {}
    with _store().edit() as state:
        existing = shopping.find_item(state, item_id)
        if existing is None:
            return _not_found(NO_ITEM)
        updated = shopping.normalize_item(payload, existing)
        state["shopping"] = [updated if i["id"] == item_id else i for i in state["shopping"]]
    return jsonify(shopping.item_view(updated))


@bp.delete("/api/zakupy/<item_id>")
def api_shopping_delete(item_id: str):
    with _store().edit() as state:
        items = state.setdefault("shopping", [])
        before = len(items)
        state["shopping"] = [i for i in items if i["id"] != item_id]
        if len(state["shopping"]) == before:
            return _not_found(NO_ITEM)
    return jsonify({"ok": True})


@bp.post("/api/zakupy/wyczysc")
def api_shopping_clear_done():
    """Sprzata kupione rzeczy - typowo po powrocie ze sklepu."""
    with _store().edit() as state:
        items = state.setdefault("shopping", [])
        state["shopping"] = [i for i in items if not i.get("done")]
        removed = len(items) - len(state["shopping"])
        result = {"usuniete": removed, "stats": shopping.stats(state)}
    return jsonify(result)


# ------------------------------------------------------------------ grafik --


@bp.post("/api/grafik/wczytaj")
def api_grafik_read():
    """Czyta plik i oddaje PODGLAD wszystkich kolumn - celowo nic nie zapisuje.

    Dzieki temu zla kolumna nie wjedzie po cichu do danych: najpierw widac,
    co znaleziono, a dopiero klikniecie osoby zapisuje jej miesiac."""
    if "plik" not in request.files:
        raise core.ValidationError("Nie wybrano pliku z grafikiem.")
    plik = request.files["plik"]
    dane = plik.read(MAX_GRAFIK + 1)
    if len(dane) > MAX_GRAFIK:
        raise core.ValidationError("Plik jest za duży (maksymalnie 8 MB).")
    return jsonify(grafik.czytaj(plik.filename or "grafik", dane))


@bp.get("/api/grafik")
def api_grafik_view():
    state = _store().load()
    year, month = _year_month(today())
    od, do = core.month_range(year, month)
    miesiac = f"{year:04d}-{month:02d}"
    return jsonify(
        {
            "miesiac": miesiac,
            "dni": grafik.widok(state, od, do),
            "wczytany": {o: grafik.miesiac_znany(state, o, miesiac) for o in core.PEOPLE},
        }
    )


def _znany_domownik(osoba: str) -> None:
    if osoba not in core.PEOPLE:
        raise core.ValidationError(f"Nie znam domownika o nazwie {osoba!r}.")


@bp.put("/api/grafik/<osoba>/<miesiac>")
def api_grafik_save(osoba: str, miesiac: str):
    _znany_domownik(osoba)
    payload = request.get_json(silent=True) or {}
    dni = grafik.oczysc_dni(payload.get("dni"))
    with _store().edit() as state:
        zapisane = grafik.zapisz_miesiac(state, osoba, miesiac, dni, str(payload.get("plik", "")))
    return jsonify({"ok": True, "osoba": osoba, "miesiac": miesiac, "dni": zapisane})


@bp.delete("/api/grafik/<osoba>/<miesiac>")
def api_grafik_delete(osoba: str, miesiac: str):
    _znany_domownik(osoba)
    with _store().edit() as state:
        if not grafik.usun_miesiac(state, osoba, miesiac):
            return _not_found("Tego miesiąca nie ma w grafiku.")
    return jsonify({"ok": True})


@bp.put("/api/grafik/<osoba>/dzien/<dzien>")
def api_grafik_day(osoba: str, dzien: str):
    """Reczna poprawka jednego dnia - przezywa ponowne wgranie tego samego miesiaca."""
    _znany_domownik(osoba)
    payload = request.get_json(silent=True) or {}
    dzien_iso = core.parse_date(dzien).isoformat()
    with _store().edit() as state:
        grafik.ustaw_dzien(state, osoba, dzien_iso, payload if payload.get("pracuje") else None)
        wynik = {"ok": True, "opis": grafik.opis(state, osoba, dzien_iso)}
    return jsonify(wynik)


@bp.get("/api/eksport")
def api_export():
    state = _store().load()
    blob = json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8")
    name = f"domownik-{datetime.now():%Y-%m-%d}.json"
    return send_file(io.BytesIO(blob), mimetype="application/json", as_attachment=True, download_name=name)


@bp.post("/api/import")
def api_import():
    if "plik" in request.files:
        raw = request.files["plik"].read().decode("utf-8-sig")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise core.ValidationError(f"To nie jest poprawny plik JSON ({exc.msg}).") from None
    else:
        payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise core.ValidationError("Plik nie zawiera danych Domownika.")
    try:
        state = _store().replace(payload)
    except ValueError as exc:
        raise core.ValidationError(str(exc)) from None
    return jsonify({"ok": True, "chores": len(state["chores"])})


@bp.get("/api/statystyki")
def api_stats():
    return jsonify(core.stats(_store().load(), today()))


def data_stamp(store: Store) -> str:
    """Znacznik stanu danych - czas modyfikacji pliku, bez wczytywania JSON-a."""
    try:
        return str(store.path.stat().st_mtime_ns)
    except OSError:
        return "0"


@bp.get("/api/wersja")
def api_version():
    """Znacznik ostatniego zapisu - zapasowy sposob wykrywania zmian.

    Uzywany, gdy strumien /api/zmiany nie dziala (stara przegladarka, posrednik
    tnacy dlugie polaczenia) oraz po wybudzeniu telefonu, gdy polaczenie moglo
    zostac ubite w tle."""
    return jsonify({"stamp": data_stamp(_store())})


@bp.get("/api/zmiany")
def api_changes():
    """Strumien powiadomien o zmianach (Server-Sent Events).

    Przegladarka trzyma jedno otwarte polaczenie, a serwer odzywa sie sam, gdy
    ktokolwiek cos zapisze - stad natychmiastowa synchronizacja miedzy telefonem
    a komputerem. Co ~20 s leci komentarz podtrzymujacy, zeby posrednicy (Tailscale,
    router) nie uznali polaczenia za martwe.

    Uwaga: kazde otwarte polaczenie zajmuje jeden watek serwera - dlatego serwer
    startuje z zapasem watkow."""
    store, zmiany = _store(), _zmiany()

    def stream():
        seen = zmiany.version
        # pierwszy pakiet od razu: klient poznaje punkt odniesienia i wie, ze zyje
        yield f"data: {data_stamp(store)}\n\n"
        while True:
            current = zmiany.wait(seen, timeout=20)
            if current != seen:
                seen = current
                yield f"data: {data_stamp(store)}\n\n"
            else:
                yield ": ping\n\n"

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # zeby posrednik nie buforowal strumienia
        },
        # Bez naglowka Connection - to naglowek warstwy polaczenia, waitress
        # odrzuca takie w odpowiedzi aplikacji (blad 500) i sam nim zarzadza.
    )


# ------------------------------------------------------------------ bledy ---


@bp.app_errorhandler(core.ValidationError)
def handle_validation(exc: core.ValidationError):
    return jsonify({"error": str(exc)}), 400


@bp.app_errorhandler(404)
def handle_404(_exc):
    if request.path.startswith("/api/"):
        return _not_found("Nie ma takiego zasobu.")
    return _page("404.html", ""), 404


@bp.app_errorhandler(Exception)
def handle_unexpected(exc: Exception):
    if isinstance(exc, core.ValidationError):
        return handle_validation(exc)
    if isinstance(exc, HTTPException):
        if request.path.startswith("/api/"):
            return jsonify({"error": exc.description}), exc.code
        return exc
    log.exception("Nieoczekiwany blad Domownika")
    if request.path.startswith("/api/"):
        return jsonify({"error": f"Coś poszło nie tak: {exc}"}), 500
    raise exc
