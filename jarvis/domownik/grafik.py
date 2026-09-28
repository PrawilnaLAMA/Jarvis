"""Grafik pracy: czytanie planu ze sklepu i odpowiedz na pytanie "kto jest dzis w domu".

Osobno od chores.py, bo to inna dziedzina - tu nie ma powtarzalnosci ani odhaczania,
tylko dni i godziny. Zero importow Flaska, jak w chores.py i shopping.py.

Grafik przychodzi w dwoch postaciach tego samego arkusza:
  * PDF  - wydruk, czytany przez pypdf po WSPOLRZEDNYCH (patrz _fragmenty_pdf),
  * XLSX - oryginal, czytany samym stdlibem, czyli dokladnie i bez zaleznosci.
Oba formaty musza dawac identyczny wynik - to nasz najlepszy test parsera.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timedelta

from .chores import PEOPLE, ValidationError

# --------------------------------------------------------------- legenda ----

# Legenda arkusza sklepowego. Uwaga na pulapke: "nieobecny w sklepie" to nie to
# samo co "nieobecny w domu" - urlop jest najlepszym dniem na obowiazki domowe,
# a wyjazdowe szkolenie najgorszym. Drugi element mowi, czy osoba jest w domu.
KODY = {
    "u": ("urlop", True),
    "w": ("dzień wolny", True),
    "l4": ("zwolnienie lekarskie", False),
    "sw": ("szkolenie wyjazdowe", False),
    "wsp": ("wsparcie innego sklepu", False),
    "zeb": ("zebranie kierowników", False),
}

# Kod z legendy wygrywa z godzinami. W prawdziwym grafiku urlop bywa wpisany jako
# 10:00-18:00 z literka "u", bo osiem godzin ksieguje sie do czasu pracy - a mimo
# to Natalii tego dnia w sklepie nie ma.
_TRANS = str.maketrans("ąćęłńóśźż", "acelnoszz")

DATA_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")
LICZBA_RE = re.compile(r"^\d{1,4}$")
ULAMEK_RE = re.compile(r"^\d+[.,]\d+$")  # 0.416666 = 10:00 w liczeniu Excela
EPOKA_EXCELA = date(1899, 12, 30)  # dzien 0 w numeracji Excela


def fold(text: str) -> str:
    """Nazwa sprowadzona do postaci porownywalnej: male litery, bez ogonkow."""
    return str(text).strip().lower().translate(_TRANS)


def dopasuj_osobe(nazwa: str) -> str | None:
    """Nazwa kolumny z grafiku -> klucz domownika z PEOPLE (albo nic)."""
    szukane = fold(nazwa)
    if not szukane:
        return None
    for klucz, osoba in PEOPLE.items():
        if szukane == fold(osoba["label"]) or szukane == klucz:
            return klucz
    return None


# ----------------------------------------------------------- stan aplikacji --


def pusty_grafik() -> dict:
    return {"osoby": {}, "miesiace": {}}


def _grafik(state: dict) -> dict:
    grafik = state.setdefault("grafik", pusty_grafik())
    grafik.setdefault("osoby", {})
    grafik.setdefault("miesiace", {})
    return grafik


def _iso(dzien) -> str:
    return dzien.isoformat() if isinstance(dzien, date) else str(dzien)


def wpis(state: dict, osoba: str, dzien) -> dict | None:
    """Surowy wpis grafiku dla osoby i dnia (albo None, gdy nic nie wpisano)."""
    return _grafik(state)["osoby"].get(osoba, {}).get(_iso(dzien))


def miesiac_znany(state: dict, osoba: str, miesiac: str) -> bool:
    return miesiac in _grafik(state)["miesiace"].get(osoba, {})


def dostepna(state: dict, osoba: str, dzien) -> bool:
    """Czy ta osoba moze tego dnia zrobic cos w domu.

    Jedyne zrodlo prawdy dla planera. Brak wpisu = wolne (osoba bez wczytanego
    grafiku, np. Leon, jest dostepna zawsze)."""
    dane = wpis(state, osoba, dzien)
    if not dane:
        return True
    kod = fold(dane.get("kod", ""))
    if kod in KODY:
        return KODY[kod][1]
    return not dane.get("od")  # sa godziny -> pracuje


def godziny(dane: dict) -> str:
    """'09:45' + '21:15' -> '9:45-21:15' (bez zera wiodacego, jak sie mowi)."""
    od, do = dane.get("od"), dane.get("do")
    if not od or not do:
        return ""
    return f"{od.lstrip('0')}–{do.lstrip('0')}"


def opis(state: dict, osoba: str, dzien) -> str:
    """Zdanie do pokazania w kalendarzu, np. 'Natalia pracuje 9:45–21:15'."""
    dane = wpis(state, osoba, dzien)
    if not dane:
        return ""
    label = PEOPLE.get(osoba, {}).get("label", osoba)
    kod = fold(dane.get("kod", ""))
    if kod in KODY:
        return f"{label} — {KODY[kod][0]}"
    czas = godziny(dane)
    return f"{label} pracuje {czas}" if czas else f"{label} pracuje"


def widok(state: dict, od_dnia: date, do_dnia: date) -> dict:
    """{data: [{osoba, label, initial, color, od, do, kod, opis, pracuje}]}."""
    grafik = _grafik(state)
    out: dict[str, list[dict]] = {}
    dzien = od_dnia
    while dzien <= do_dnia:
        klucz = dzien.isoformat()
        for osoba, dni in grafik["osoby"].items():
            dane = dni.get(klucz)
            if not dane:
                continue
            info = PEOPLE.get(osoba, {})
            out.setdefault(klucz, []).append(
                {
                    "osoba": osoba,
                    "label": info.get("label", osoba),
                    "initial": info.get("initial", "?"),
                    "color": info.get("color", "#9a8b7d"),
                    "od": dane.get("od", ""),
                    "do": dane.get("do", ""),
                    "kod": dane.get("kod", ""),
                    "godziny": godziny(dane),
                    "opis": opis(state, osoba, dzien),
                    "pracuje": not dostepna(state, osoba, dzien),
                    "reczne": bool(dane.get("reczne")),
                }
            )
        dzien += timedelta(days=1)
    return out


def zapisz_miesiac(state: dict, osoba: str, miesiac: str, dni: dict, plik: str = "") -> int:
    """Podmienia JEDEN miesiac tej osoby, nie ruszajac pozostalych.

    Reczne poprawki (dopisane w aplikacji) przezywaja ponowny import - inaczej
    poprawka zniknelaby przy kazdym wgraniu tego samego pliku."""
    if not re.fullmatch(r"\d{4}-\d{2}", miesiac):
        raise ValidationError(f"Nieprawidłowy miesiąc: {miesiac!r} (oczekiwano RRRR-MM).")
    grafik = _grafik(state)
    biezace = grafik["osoby"].setdefault(osoba, {})

    for dzien in [d for d in biezace if d.startswith(miesiac) and not biezace[d].get("reczne")]:
        del biezace[dzien]
    zapisane = 0
    for dzien, dane in dni.items():
        if not dzien.startswith(miesiac) or biezace.get(dzien, {}).get("reczne"):
            continue
        biezace[dzien] = dane
        zapisane += 1

    grafik["osoby"][osoba] = dict(sorted(biezace.items()))
    grafik["miesiace"].setdefault(osoba, {})[miesiac] = {
        "plik": plik[:120],
        "wczytany": datetime.now().isoformat(timespec="seconds"),
        "dni": zapisane,
    }
    return zapisane


def oczysc_dni(surowe) -> dict:
    """Sprawdza dni przyslane z przegladarki, zanim trafia do pliku z danymi."""
    if not isinstance(surowe, dict):
        raise ValidationError("Oczekiwano listy dni w formacie {data: godziny}.")
    if len(surowe) > 400:
        raise ValidationError("Za dużo dni naraz (maksymalnie 400).")
    out = {}
    for dzien, dane in surowe.items():
        try:
            date.fromisoformat(str(dzien))
        except ValueError:
            raise ValidationError(f"Nieprawidłowa data: {dzien!r} (oczekiwano RRRR-MM-DD).") from None
        if not isinstance(dane, dict):
            raise ValidationError(f"Nieprawidłowy wpis dla dnia {dzien}.")
        out[str(dzien)] = {
            "od": _czas(dane.get("od")),
            "do": _czas(dane.get("do")),
            "kod": str(dane.get("kod", ""))[:8],
            "reczne": False,
        }
    return out


def usun_miesiac(state: dict, osoba: str, miesiac: str) -> bool:
    grafik = _grafik(state)
    if not miesiac_znany(state, osoba, miesiac):
        return False
    dni = grafik["osoby"].get(osoba, {})
    for dzien in [d for d in dni if d.startswith(miesiac)]:
        del dni[dzien]
    grafik["miesiace"][osoba].pop(miesiac, None)
    if not grafik["miesiace"][osoba]:
        del grafik["miesiace"][osoba]
    return True


def ustaw_dzien(state: dict, osoba: str, dzien, dane: dict | None) -> None:
    """Reczna poprawka jednego dnia. None kasuje wpis (czyli 'ma wolne')."""
    if osoba not in PEOPLE:
        raise ValidationError(f"Nie znam domownika o nazwie {osoba!r}.")
    grafik = _grafik(state)
    dni = grafik["osoby"].setdefault(osoba, {})
    klucz = _iso(dzien)
    if dane is None:
        dni[klucz] = {"od": "", "do": "", "kod": "w", "reczne": True}
    else:
        dni[klucz] = {
            "od": _czas(dane.get("od")),
            "do": _czas(dane.get("do")),
            "kod": str(dane.get("kod", ""))[:8],
            "reczne": True,
        }
    grafik["osoby"][osoba] = dict(sorted(dni.items()))


def _czas(wartosc) -> str:
    if not wartosc:
        return ""
    tekst = str(wartosc).strip()
    match = re.fullmatch(r"(\d{1,2})[:.](\d{2})", tekst)
    if not match:
        raise ValidationError(f"Nieprawidłowa godzina: {wartosc!r} (oczekiwano GG:MM).")
    hh, mm = int(match.group(1)), int(match.group(2))
    if hh > 23 or mm > 59:
        raise ValidationError(f"Nieprawidłowa godzina: {wartosc!r}.")
    return f"{hh:02d}:{mm:02d}"


# --------------------------------------------------------- czytanie plikow --


def czytaj(nazwa: str, dane: bytes) -> dict:
    """Rozpoznaje format po naglowku pliku i oddaje podglad wszystkich kolumn."""
    if not dane:
        raise ValidationError("Plik jest pusty.")
    if dane[:4] == b"%PDF":
        osoby = _czytaj_pdf(dane)
    elif dane[:2] == b"PK":
        osoby = _czytaj_xlsx(dane)
    else:
        raise ValidationError(
            "Nie rozpoznaję tego pliku. Wgraj grafik w formacie PDF albo XLSX."
        )
    return _podsumowanie(nazwa, osoby)


def _podsumowanie(nazwa: str, osoby: list[dict]) -> dict:
    wszystkie = [d for osoba in osoby for d in osoba["dni"]]
    if not wszystkie:
        raise ValidationError(
            "W tym pliku nie znalazłem żadnych godzin pracy. "
            "Czy to na pewno grafik miesięczny?"
        )
    miesiace = sorted({d[:7] for d in wszystkie})
    miesiac = max(miesiace, key=lambda m: sum(1 for d in wszystkie if d.startswith(m)))
    for osoba in osoby:
        osoba["dni"] = {d: w for d, w in sorted(osoba["dni"].items()) if d.startswith(miesiac)}
        osoba["pracujace"] = sum(1 for w in osoba["dni"].values() if _pracuje(w))
        osoba["wolne_z_kodem"] = len(osoba["dni"]) - osoba["pracujace"]
        osoba["domownik"] = dopasuj_osobe(osoba["nazwa"])
    # Kolumna bez ani jednej godziny to nie czlowiek. Arkusz XLSX ma za widoczna
    # tabela ukryty obszar pomocniczy, ktory powtarza naglowki OD/DO i trzyma
    # godziny jako ulamki doby (0.416666 = 10:00) - w PDF-ie go po prostu nie widac.
    return {
        "plik": nazwa[:120],
        "miesiac": miesiac,
        "osoby": [o for o in osoby if any(w.get("od") for w in o["dni"].values())],
    }


def _pracuje(dane: dict) -> bool:
    kod = fold(dane.get("kod", ""))
    if kod in KODY:
        return not KODY[kod][1]
    return bool(dane.get("od"))


def _wpis_z_komorek(liczby_od: list[int], liczby_do: list[int], kod: str) -> dict | None:
    """Cztery komorki (godz, min, godz, min) + literka -> jeden wpis grafiku."""
    kod = kod.strip()[:8]
    if ULAMEK_RE.match(kod):
        kod = ""  # ulamek doby z obszaru pomocniczego arkusza, nie kod z legendy
    if not liczby_od or not liczby_do:
        return {"od": "", "do": "", "kod": kod, "reczne": False} if kod else None
    od_h, od_m = liczby_od[0], (liczby_od[1] if len(liczby_od) > 1 else 0)
    do_h, do_m = liczby_do[0], (liczby_do[1] if len(liczby_do) > 1 else 0)
    if od_h > 23 or do_h > 23 or od_m > 59 or do_m > 59:
        return {"od": "", "do": "", "kod": kod, "reczne": False} if kod else None
    return {
        "od": f"{od_h:02d}:{od_m:02d}",
        "do": f"{do_h:02d}:{do_m:02d}",
        "kod": kod,
        "reczne": False,
    }


# ------------------------------------------------------------------- PDF ----


def _fragmenty_pdf(dane: bytes) -> list[tuple[float, float, str]]:
    """(y, x, tekst) dla kazdego kawalka tekstu na pierwszej stronie z tabela.

    Idziemy po operatorach strumienia sami, bo KOLEJNOSC TEKSTU W PDF-IE KLAMIE
    (kolumna "info" Jaska trafia przed jego godziny) - liczy sie wylacznie
    wspolrzedna X. Gotowe extract_text() tego nie odda, a visitor_text() z pypdf
    rozjezdza tekst ze wspolrzednymi o jedno wywolanie."""
    try:
        from pypdf import PdfReader
        from pypdf.generic import ContentStream
    except ImportError:
        raise ValidationError(
            "Do czytania PDF-ów potrzebna jest biblioteka pypdf "
            "(py -m pip install pypdf). Grafik w formacie .xlsx działa bez niej."
        ) from None

    try:
        reader = PdfReader(io.BytesIO(dane))
    except Exception as exc:
        raise ValidationError(f"Nie udało się otworzyć PDF-a: {exc}") from None

    najlepsza: list[tuple[float, float, str]] = []
    for strona in reader.pages:
        frags: list[tuple[float, float, str]] = []
        x = y = 0.0
        try:
            content = ContentStream(strona.get_contents(), reader)
        except Exception:
            continue
        for operands, op in content.operations:
            if op == b"BT":
                x = y = 0.0
            elif op == b"Tm" and len(operands) >= 6:
                x, y = float(operands[4]), float(operands[5])
            elif op in (b"Td", b"TD") and len(operands) >= 2:
                x += float(operands[0])
                y += float(operands[1])
            else:
                tekst = ""
                if op == b"Tj" and operands:
                    tekst = str(operands[0])
                elif op == b"TJ" and operands:
                    tekst = "".join(
                        str(part) for part in operands[0] if not isinstance(part, (int, float))
                    )
                if tekst.strip():
                    frags.append((round(y, 1), round(x, 1), tekst.strip()))
        if len(frags) > len(najlepsza):
            najlepsza = frags
    return najlepsza


def _wiersze(frags: list[tuple[float, float, str]], tolerancja: float = 1.8) -> list[list[tuple[float, str]]]:
    """Fragmenty pogrupowane w wiersze po zblizonej wysokosci, od gory strony."""
    out: list[list[tuple[float, str]]] = []
    kotwica: float | None = None
    for y, x, tekst in sorted(frags, key=lambda f: (-f[0], f[1])):
        if kotwica is None or abs(kotwica - y) > tolerancja:
            kotwica = y
            out.append([])
        out[-1].append((x, tekst))
    return [sorted(wiersz) for wiersz in out]


def _czytaj_pdf(dane: bytes) -> list[dict]:
    wiersze = _wiersze(_fragmenty_pdf(dane))
    if not wiersze:
        raise ValidationError("W tym PDF-ie nie ma tekstu (to chyba skan albo zdjęcie).")

    # naglowek: wiersz z najwieksza liczba komorek "OD"
    idx = max(range(len(wiersze)), key=lambda i: sum(1 for _, s in wiersze[i] if s.upper() == "OD"))
    naglowek = wiersze[idx]
    od_x = sorted(x for x, s in naglowek if s.upper() == "OD")
    do_x = sorted(x for x, s in naglowek if s.upper() == "DO")
    info_x = sorted(x for x, s in naglowek if s.lower() == "info")
    if len(od_x) < 2 or len(do_x) < len(od_x):
        raise ValidationError(
            "Nie znalazłem w tym PDF-ie nagłówka grafiku (kolumn OD i DO). "
            "Czy to na pewno miesięczny grafik ze sklepu?"
        )

    krok = min(b - a for a, b in zip(od_x, od_x[1:], strict=False))
    margines = krok * 0.16
    bloki = []
    for i, start in enumerate(od_x):
        # Koniec danych to poczatek rubryki "info" - bez tego numer z tej rubryki
        # (np. "3825" przy Jaśku) wjechalby jako godzina wyjscia.
        # Szukamy pierwszej rubryki NA PRAWO od DO, bo w naglowku jest jeszcze
        # kolumna "INFO" calego dnia, na lewo od wszystkich osob.
        po_prawej = [x for x in info_x if x > do_x[i]]
        koniec = (po_prawej[0] - margines) if po_prawej else (start + krok * 0.63)
        bloki.append(
            {
                "lewa": start - margines,
                "srodek": (start + do_x[i]) / 2,
                "koniec_godzin": koniec,
                "prawa": (od_x[i + 1] - margines) if i + 1 < len(od_x) else start + krok - margines,
            }
        )

    # imiona: pierwszy wiersz powyzej naglowka, ktory ma tekst w co najmniej dwoch blokach
    nazwy = ["" for _ in bloki]
    for wiersz in reversed(wiersze[:idx]):
        kandydat = ["" for _ in bloki]
        for x, tekst in wiersz:
            for i, blok in enumerate(bloki):
                if blok["lewa"] <= x < blok["prawa"] and not LICZBA_RE.match(tekst):
                    kandydat[i] = tekst
        if sum(1 for n in kandydat if n) >= 2:
            nazwy = kandydat
            break

    osoby = [{"nazwa": nazwa or f"kolumna {i + 1}", "kolumna": i + 1, "dni": {}} for i, nazwa in enumerate(nazwy)]

    for wiersz in wiersze[idx + 1:]:
        dzien = _data_z_wiersza(wiersz)
        if dzien is None:
            continue
        for i, blok in enumerate(bloki):
            liczby_od, liczby_do, kod = [], [], []
            for x, tekst in wiersz:
                if not (blok["lewa"] <= x < blok["prawa"]):
                    continue
                if x >= blok["koniec_godzin"]:
                    kod.append(tekst)
                elif LICZBA_RE.match(tekst):
                    (liczby_od if x < blok["srodek"] else liczby_do).append(int(tekst))
                else:
                    kod.append(tekst)
            wpis_dnia = _wpis_z_komorek(liczby_od, liczby_do, " ".join(kod))
            if wpis_dnia:
                osoby[i]["dni"][dzien.isoformat()] = wpis_dnia
    return osoby


def _data_z_wiersza(wiersz: list[tuple[float, str]]) -> date | None:
    for _, tekst in wiersz[:2]:
        match = DATA_RE.match(tekst)
        if match:
            dzien, miesiac, rok = (int(g) for g in match.groups())
            try:
                return date(rok, miesiac, dzien)
            except ValueError:
                return None
    return None


# ------------------------------------------------------------------ XLSX ----

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _kolumna_na_numer(ref: str) -> int:
    """'A' -> 1, 'AB' -> 28."""
    numer = 0
    for znak in ref:
        if not znak.isalpha():
            break
        numer = numer * 26 + (ord(znak.upper()) - 64)
    return numer


def _czytaj_xlsx(dane: bytes) -> list[dict]:
    try:
        paczka = zipfile.ZipFile(io.BytesIO(dane))
    except zipfile.BadZipFile:
        raise ValidationError("Ten plik XLSX jest uszkodzony albo to nie jest arkusz.") from None

    try:
        teksty = [
            "".join(t.text or "" for t in si.iter(_NS + "t"))
            for si in ET.fromstring(paczka.read("xl/sharedStrings.xml"))
        ]
    except KeyError:
        teksty = []

    arkusz = _znajdz_arkusz(paczka)
    wiersze: dict[int, dict[int, str]] = {}
    for wiersz in ET.fromstring(paczka.read(arkusz)).iter(_NS + "row"):
        komorki: dict[int, str] = {}
        for komorka in wiersz.iter(_NS + "c"):
            wartosc = komorka.find(_NS + "v")
            if wartosc is None or wartosc.text is None:
                continue
            surowa = wartosc.text
            if komorka.get("t") == "s":
                try:
                    surowa = teksty[int(surowa)]
                except (ValueError, IndexError):
                    surowa = ""
            komorki[_kolumna_na_numer(komorka.get("r", ""))] = surowa
        if komorki:
            wiersze[int(wiersz.get("r", 0))] = komorki

    numer_naglowka = max(
        wiersze,
        key=lambda n: sum(1 for v in wiersze[n].values() if str(v).strip().upper() == "OD"),
        default=0,
    )
    naglowek = wiersze.get(numer_naglowka, {})
    od_kol = sorted(k for k, v in naglowek.items() if str(v).strip().upper() == "OD")
    do_kol = sorted(k for k, v in naglowek.items() if str(v).strip().upper() == "DO")
    info_kol = sorted(k for k, v in naglowek.items() if str(v).strip().lower() == "info")
    if len(od_kol) < 2 or len(do_kol) < len(od_kol):
        raise ValidationError("W tym arkuszu nie ma nagłówka grafiku (kolumn OD i DO).")

    imiona = wiersze.get(numer_naglowka - 1, {})
    osoby = []
    for i, start in enumerate(od_kol):
        # jak w PDF-ie: pierwsza rubryka "info" NA PRAWO od DO, bo kolumna "INFO"
        # calego dnia stoi przed wszystkimi osobami
        po_prawej = [k for k in info_kol if k > do_kol[i]]
        koniec = po_prawej[0] if po_prawej else start + 4
        nazwa = next(
            (str(v).strip() for k, v in sorted(imiona.items()) if start - 1 <= k < koniec and str(v).strip()),
            "",
        )
        osoby.append(
            {
                "nazwa": nazwa or f"kolumna {i + 1}",
                "kolumna": i + 1,
                "dni": {},
                "_od": (start, do_kol[i]),
                "_do": (do_kol[i], koniec),
                "_info": koniec,
            }
        )

    for numer in sorted(n for n in wiersze if n > numer_naglowka):
        komorki = wiersze[numer]
        dzien = _data_z_serii(komorki.get(1))
        if dzien is None:
            continue
        for osoba in osoby:
            liczby_od = _liczby(komorki, *osoba["_od"])
            liczby_do = _liczby(komorki, *osoba["_do"])
            kod = str(komorki.get(osoba["_info"], "")).strip()
            wpis_dnia = _wpis_z_komorek(liczby_od, liczby_do, kod)
            if wpis_dnia:
                osoba["dni"][dzien.isoformat()] = wpis_dnia

    for osoba in osoby:
        for klucz in ("_od", "_do", "_info"):
            osoba.pop(klucz, None)
    return osoby


def _znajdz_arkusz(paczka: zipfile.ZipFile) -> str:
    """Sciezka do arkusza 'grafik' (albo pierwszego, jesli nazwa sie zmienila)."""
    workbook = ET.fromstring(paczka.read("xl/workbook.xml"))
    rels = {
        rel.get("Id"): rel.get("Target")
        for rel in ET.fromstring(paczka.read("xl/_rels/workbook.xml.rels"))
    }
    pierwszy = None
    for arkusz in workbook.find(_NS + "sheets"):
        cel = rels.get(arkusz.get(_NS_REL + "id"), "")
        sciezka = "xl/" + cel.lstrip("/").removeprefix("xl/")
        pierwszy = pierwszy or sciezka
        if fold(arkusz.get("name", "")) == "grafik":
            return sciezka
    if pierwszy is None:
        raise ValidationError("W tym pliku XLSX nie ma żadnego arkusza.")
    return pierwszy


def _liczby(komorki: dict[int, str], od_kol: int, do_kol: int) -> list[int]:
    out = []
    for kolumna in range(od_kol, do_kol):
        wartosc = str(komorki.get(kolumna, "")).strip()
        if LICZBA_RE.match(wartosc):
            out.append(int(wartosc))
    return out


def _data_z_serii(wartosc) -> date | None:
    """Kolumna A trzyma date jako liczbe dni od 1899-12-30 (numeracja Excela)."""
    try:
        numer = int(float(wartosc))
    except (TypeError, ValueError):
        return None
    if not 20000 < numer < 80000:
        return None
    return EPOKA_EXCELA + timedelta(days=numer)
