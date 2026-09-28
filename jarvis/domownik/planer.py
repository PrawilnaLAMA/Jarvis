"""Planer: uklada obowiazki na dni, w ktore da sie je faktycznie zrobic.

Zasada dzialania dla jednego wystapienia, w kolejnosci dat:

  1. TURA      - obowiazek z dwiema osobami chodzi na zmiane (kolejnosc z PEOPLE,
                 wiec zaczyna Leon). Z jedna osoba tura jest zawsze jej.
  2. WYROWNANIE- jesli tura wypada na kogos, kto ma nadwyzke (robil za druga osobe),
                 a ta druga jest tego dnia wolna, to robi ta druga i licznik spada.
  3. DOSTEPNOSC- jesli osoba z tury tego dnia pracuje: probujemy dzien pozniej,
                 potem dzien wczesniej, a w ostatecznosci bierze to druga osoba
                 z domu i jej licznik rosnie o 1.

Dwie zasady, ktore chronia dane:

  * DATE RUSZAMY TYLKO OD DZIS W PRZOD i nigdy przy odhaczonym wystapieniu.
    Odhaczenia siedza pod para (obowiazek, data) - przesuniecie dnia w przeszlosci
    osierocilby taki wpis i zrobiona rzecz nagle zrobilaby sie niezrobiona.
  * REGULA POWTARZANIA SIE NIE ZMIENIA. Przesuniecie dotyczy jednego wystapienia,
    kolejne liczy sie od pierwotnej daty - inaczej plan by dryfowal.

Stanu tu nie ma: caly przebieg jest odtwarzany od nowa przy kazdym wywolaniu,
wiec poprawiony grafik od razu przelicza wszystko i nie ma trzeciego miejsca,
ktore moze sie rozjechac z danymi.
"""

from __future__ import annotations

from datetime import date, timedelta

from . import grafik
from .chores import PEOPLE, WEEKDAYS_SHORT, assignees_of, is_done, occurs_on, parse_date

# Ile najwyzej dni odtwarzamy wstecz, zeby policzyc liczniki. Przy starszym
# obowiazku kolejka zaczyna sie liczyc od nowa - zmienia to tylko to, kto bierze
# pierwsza ture, a liczniki i tak same wyrownuja reszte.
MAX_WSTECZ = 730


def rozklad(state: dict, od: date, do: date, dzis: date) -> dict:
    """Plan dla okna [od, do]: co ktorego dnia wypada, kto to robi i jakie sa liczniki.

    Zwraca {"od", "do", "dni": {data: {chore_id: decyzja}}, "dlugi": {chore_id: {osoba: ile}}}.
    'dlugi' to stan na koniec okna - czyli dokladnie to, co zostaje niewyrownane."""
    dni: dict[str, dict[str, dict]] = {}
    dlugi: dict[str, dict[str, int]] = {}
    for chore in state.get("chores", []):
        _zaplanuj(state, chore, od, do, dzis, dni, dlugi)
    return {"od": od.isoformat(), "do": do.isoformat(), "dni": dni, "dlugi": dlugi}


def _zaplanuj(state: dict, chore: dict, od: date, do: date, dzis: date,
              dni: dict, dlugi: dict) -> None:
    przypisane = assignees_of(chore)

    if not przypisane:
        # obowiazek wspolny - planer go nie rusza, po prostu go pokazuje
        dzien = od
        while dzien <= do:
            if occurs_on(chore, dzien):
                _zapisz(dni, dzien, chore, {"kto": "", "powod": "", "z_dnia": None})
            dzien += timedelta(days=1)
        return

    dlug = {osoba: 0 for osoba in PEOPLE}
    numer = 0
    dzien = max(parse_date(chore["start_date"]), od - timedelta(days=MAX_WSTECZ))
    # Liczymy o dzien dluzej niz okno, bo wystapienie z dnia PO oknie moze sie
    # cofnac do jego ostatniego dnia. Liczniki bierzemy jednak ze stanu na koniec
    # okna - inaczej pokazywalyby dlug z dnia, ktorego uzytkownik jeszcze nie widzi.
    granica = do + timedelta(days=1)
    niezerowe: dict[str, int] | None = None
    while dzien <= granica:
        if dzien > do and niezerowe is None:
            niezerowe = {osoba: ile for osoba, ile in dlug.items() if ile}
        if occurs_on(chore, dzien):
            tura = przypisane[numer % len(przypisane)]
            numer += 1
            docelowy, decyzja = _rozstrzygnij(state, chore, przypisane, tura, dzien, dzis, dlug)
            if od <= docelowy <= do:
                _zapisz(dni, docelowy, chore, decyzja)
        dzien += timedelta(days=1)

    if niezerowe:
        dlugi[chore["id"]] = niezerowe


def _zapisz(dni: dict, dzien: date, chore: dict, decyzja: dict) -> None:
    dni.setdefault(dzien.isoformat(), {})[chore["id"]] = decyzja


def _rozstrzygnij(state: dict, chore: dict, przypisane: list[str], tura: str,
                  dzien: date, dzis: date, dlug: dict) -> tuple[date, dict]:
    label = lambda osoba: PEOPLE[osoba]["label"]  # noqa: E731

    # 1. wyrownanie licznika - ktos ma nadwyzke, a tura wypada wlasnie na niego
    wierzyciel = _wierzyciel(dlug)
    if wierzyciel and wierzyciel == tura:
        dluznik = next((o for o in przypisane if o != wierzyciel), "")
        if dluznik and grafik.dostepna(state, dluznik, dzien):
            dlug[wierzyciel] -= 1
            return dzien, {
                "kto": dluznik,
                "z_dnia": None,
                "powod": f"wyrównanie — {label(wierzyciel)} zrobił(a) to wcześniej za {label(dluznik)}",
            }

    # 2. osoba z tury tego dnia pracuje
    if not grafik.dostepna(state, tura, dzien):
        nowy = _sasiedni_wolny_dzien(state, chore, tura, dzien, dzis)
        if nowy:
            return nowy, {
                "kto": tura,
                "z_dnia": dzien.isoformat(),
                "powod": f"{label(tura)} pracuje {_krotko(dzien)} — przeniesione",
            }
        zastepca = _zastepca(state, przypisane, tura, dzien)
        if zastepca:
            dlug[zastepca] += 1
            return dzien, {
                "kto": zastepca,
                "z_dnia": None,
                "powod": f"{label(tura)} pracuje — bierze {label(zastepca)}",
            }
        return dzien, {
            "kto": tura,
            "z_dnia": None,
            "powod": f"{label(tura)} pracuje, nie ma kto zastąpić",
        }

    return dzien, {"kto": tura, "z_dnia": None, "powod": ""}


def _wierzyciel(dlug: dict) -> str:
    """Osoba z najwieksza nadwyzka zrobionych obowiazkow (albo nikt)."""
    osoba = max(dlug, key=lambda o: dlug[o], default="")
    return osoba if osoba and dlug[osoba] > 0 else ""


def _zastepca(state: dict, przypisane: list[str], tura: str, dzien: date) -> str:
    """Kto moze wziac obowiazek zamiast osoby z tury - najpierw wspolwlasciciel."""
    kandydaci = [o for o in przypisane if o != tura]
    kandydaci += [o for o in PEOPLE if o != tura and o not in przypisane]
    return next((o for o in kandydaci if grafik.dostepna(state, o, dzien)), "")


def _sasiedni_wolny_dzien(state: dict, chore: dict, osoba: str,
                          dzien: date, dzis: date) -> date | None:
    """Dzien pozniej, a jak sie nie da - dzien wczesniej. Nigdy w przeszlosc."""
    if is_done(state, chore["id"], dzien):
        return None  # zrobione tego dnia - nie ma czego przesuwac

    # Jesli przy poprzednim ukladzie obowiazek zostal przeniesiony i TAM odhaczony,
    # zostawiamy go tam na stale. Bez tego zmiana grafiku cofnelaby go na pierwotny
    # dzien, a odhaczenie zostaloby sierota i zrobiona rzecz zrobilaby sie niezrobiona.
    for przesuniecie in (1, -1):
        kandydat = dzien + timedelta(days=przesuniecie)
        if (
            _w_zakresie(chore, kandydat)
            and not occurs_on(chore, kandydat)
            and is_done(state, chore["id"], kandydat)
        ):
            return kandydat

    if dzien < dzis:
        return None
    for przesuniecie in (1, -1):
        kandydat = dzien + timedelta(days=przesuniecie)
        if kandydat < dzis or not _w_zakresie(chore, kandydat):
            continue
        if occurs_on(chore, kandydat):
            continue  # ten obowiazek juz tam wypada, nie ma czego przesuwac
        if grafik.dostepna(state, osoba, kandydat):
            return kandydat
    return None


def _w_zakresie(chore: dict, dzien: date) -> bool:
    if dzien < parse_date(chore["start_date"]):
        return False
    koniec = chore.get("end_date")
    return not (koniec and dzien > parse_date(koniec))


def _krotko(dzien: date) -> str:
    return f"{WEEKDAYS_SHORT[dzien.weekday()]} {dzien.day}.{dzien.month:02d}"


def podsumowanie_dlugow(state: dict, plan: dict) -> list[dict]:
    """Liczniki do pokazania pod naglowkiem miesiaca - tylko te niewyrownane."""
    tytuly = {c["id"]: c["title"] for c in state.get("chores", [])}
    out = []
    for chore_id, dlug in plan.get("dlugi", {}).items():
        for osoba, ile in dlug.items():
            if ile <= 0 or chore_id not in tytuly:
                continue
            out.append(
                {
                    "obowiazek": tytuly[chore_id],
                    "osoba": osoba,
                    "label": PEOPLE[osoba]["label"],
                    "color": PEOPLE[osoba]["color"],
                    "ile": ile,
                }
            )
    return sorted(out, key=lambda w: (-w["ile"], w["obowiazek"].lower()))
