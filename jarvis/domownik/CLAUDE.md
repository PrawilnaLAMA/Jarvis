# Domownik (w Jarvisie)

Obowiązki domowe, kalendarz, lista zakupów i grafik pracy Natalii. Dawniej osobne repozytorium
HouseholdChoresApp z własnym serwerem; teraz aplikacja Flask w tym pakiecie, którą Jarvis uruchamia
w wątku (`jarvis/services/domownik_server.py`) na własnym porcie (domyślnie 8080, przy `lan=True` na
0.0.0.0 – telefony i PWA). Panel Jarvisa zostaje na 127.0.0.1; w sieci widać tylko Domownika.

## Język

Interfejs, komunikaty błędów, nazwy tras (`/kalendarz`, `/obowiazki`, `/api/odhacz`) i komentarze są
polskie. Teksty dla użytkownika mają pełne polskie znaki; komentarze w plikach `.py` tego pakietu są
w większości bez ogonków (ASCII) – tak zostało z oryginału.

## Uruchamianie i testy

- Serwer startuje razem z Jarvisem (`JarvisApp.start()` → `DomownikServer.start()`); ustawienia w sekcji
  `domownik` (`serve`, `lan`, `port`, `url`), zmiana portu/sieci restartuje serwer na żywo.
- Dane: `data/domownik/chores.json` (+ dzienne kopie w `data/domownik/kopie/`). **To prawdziwe dane
  domu** – nie nadpisuj ich, nie regeneruj seedem i nie zostawiaj w nich testowych obowiązków.
- Testy: `py -m pytest tests/test_domownik_app.py tests/test_domownik_server.py`. Aplikację buduje
  `create_app(tmp_path / "chores.json")` – nic nie liczy się przy imporcie, więc test nie dotknie
  prawdziwego pliku. Serwer w testach tylko na 127.0.0.1 (`lan=False`) i wolnym porcie.
- Ręczne sprawdzenie: `JarvisApp(data_dir=<katalog tymczasowy>, voice=False)` z kopią danych,
  `settings.update({"domownik": {"lan": False, "port": <wolny>}})`, `app.start()`.
- **Daty:** `?dzis=RRRR-MM-DD` udaje inny dzień w całej aplikacji (backend i frontend).
- **Wygląd:** zrzuty przez Playwright + Chrome (`p.chromium.launch(channel="chrome", headless=True)`,
  `page.set_viewport_size`) – prawdziwy viewport, więc reguły `@media (max-width: 430px)` działają.
  `document.documentElement.scrollWidth` większy niż szerokość = prawdziwe przepełnienie w poziomie.
  Otwarty strumień SSE nie pozwala doczekać się „networkidle” – czekaj na `load` + chwilę, albo `?bez-sync=1`.
- **Parser grafiku:** najmocniejszy test to porównanie **PDF kontra XLSX** tego samego miesiąca – dwa
  niezależne sposoby odczytu muszą dać identyczny wynik. Prawdziwe pliki leżą w `~/Downloads` i **nie
  trafiają do repozytorium** (nazwiska współpracowników Natalii).
- **Planer:** stan buduj ręcznie (`{"chores": [...], "completions": {}, "grafik": ...}`) i sprawdzaj
  `planer.rozklad()` co do dnia: brak grafiku (plan identyczny z samą regułą powtarzania), przesunięcie
  w przód i w tył, brak przesunięcia w przeszłość i przy odhaczonym wystąpieniu, obowiązek jedno- i dwuosobowy.

## Architektura

| Plik | Rola |
| --- | --- |
| `storage.py` | `Store` – jeden plik JSON, atomowy zapis (temp + `os.replace`), kopia przy uszkodzeniu/imporcie, dzienne kopie, `_migrate()` uzupełnia braki. Nic nie wie o obowiązkach. |
| `chores.py` | logika obowiązków (powtarzalność, plan dnia, statystyki) – zero importów Flaska. |
| `shopping.py` | lista zakupów (działy sklepu, zgadywanie działu z nazwy) – też bez Flaska. |
| `grafik.py` | czytanie grafiku pracy (PDF/XLSX) i „czy ta osoba jest tego dnia w domu”. |
| `planer.py` | układanie obowiązków wokół grafiku: tury, licznik długu, przesuwanie dni. |
| `sync.py` | `Broadcaster` – licznik zmian + budzik dla połączeń SSE. |
| `web.py` | `create_app(data_file)` + Blueprint `dom`: parsowanie żądania → logika → JSON. |

Stan to jeden słownik: `chores`, `completions`, `shopping`, `grafik`. Nowy klucz najwyższego poziomu
**musi** trafić do `default_state()` – `_migrate()` przepisuje tylko klucze, które tam istnieją, więc
bez tego dane znikną przy pierwszym zapisie.

**Obowiązki to reguły, nie wygenerowane wystąpienia.** Jedynym źródłem prawdy „czy to wypada dziś” jest
`occurs_on(chore, day)`; wszystkie widoki iterują po dniach i o to pytają. Nowy typ powtarzania = cztery
miejsca: `REPEAT_TYPES`, `_normalize_repeat()`, `occurs_on()`, `repeat_label()`.

**Odhaczenia są osobno** – `completions: {chore_id: ["2026-08-11", ...]}`, per dzień, nigdy globalnie.

**Obowiązek ma LISTĘ osób (`assignees`).** Pusto = wspólny, jedna osoba = jej, **dwie = na zmianę**
(kolejność zawsze z `PEOPLE`, więc pierwszą turę bierze Leon – pilnuje tego `_normalize_assignees()`).

**Kolor liczy tylko `display_color(chore, kto)`** – osoba wygrywa z kategorią, przy obowiązku na zmianę
kolor zależy od tego, czyja tura. Frontend czyta gotowe `item.color`; nie licz koloru drugi raz.

**Walidacja:** rzuć `chores.ValidationError` z polskim komunikatem – handler zamieni to na JSON 400.

**Kolejność kluczy coś znaczy** – działy sklepu są ułożone tak, jak się idzie przez sklep. Sortowanie
kluczy jest wyłączone w **dwóch** miejscach: `app.json.sort_keys` (API) oraz
`app.jinja_env.policies["json.dumps_kwargs"]` (filtr `|tojson` – Jinja ma własną politykę). Zgubienie
drugiego objawia się działami po alfabecie (test: `test_dictionaries_keep_shop_order`).

**Zgadywanie działu** (`shopping.guess_category`): nazwy złożone („papier toaletowy”), potem **pierwszy
wyraz**, dopiero potem reszta – bez tego `sok pomarańczowy` ląduje w warzywach. Słowa kluczowe bez
polskich znaków (`fold()`).

### Serwer – jeden proces, wiele wątków

`Store` serializuje zapisy przez `threading.RLock`, który działa tylko wewnątrz procesu; `store.edit()` to
odczyt-modyfikacja-zapis całego pliku. Dlatego **jeden** serwer nad plikiem: nie uruchamiaj obok starego
`start-serwer.bat` ani drugiego Jarvisa z `serve=True` na tych samych danych. Drugi Jarvis (np. na PC,
gdy Domownik żyje na Raspberry Pi) ustawia `serve=False` i `url` serwera – narzędzia Jarvisa i tak
rozmawiają z Domownikiem przez HTTP (`services/domownik_client.py`).

`DomownikServer` (waitress, `threads=16`): każde połączenie SSE na stałe zajmuje wątek, stąd zapas.
waitress nie ma „stop” – zamykamy gniazda pętli (`wasyncore.close_all`), budzimy SSE (`Broadcaster.bump`)
i gasimy wątki robocze. `create_server` uruchamia wątki przed zajęciem portu, więc dostaje własny
dyspozytor bez wątków (`_dispatcher=`), a wątki dodajemy dopiero po udanym starcie. Zajęty port = zwykle
stary serwer: stan `error`, jeden komunikat, ponowna próba co `RETRY_SECONDS`.

**Natychmiastowa synchronizacja między urządzeniami:** `Store.on_change` → `Broadcaster.bump()` →
`GET /api/zmiany` (SSE, `: ping` co 20 s). W przeglądarce `app.js` trzyma `EventSource` i zamienia zmianę
znacznika na `notifyChanged({ reason: 'remote' })`. `GET /api/wersja` to **plan B** (odpytywanie, gdy
strumień nie jest `OPEN`, i po powrocie na kartę – telefon po uśpieniu ubija połączenie). Nie usuwaj go.

Pułapki, na które już wpadliśmy:
- **Nagłówek `Connection` w odpowiedzi = HTTP 500 pod waitress.** W `test_client()` przechodzi, więc SSE
  testuj na prawdziwym serwerze (`tests/test_domownik_server.py`).
- Otwarty strumień sprawia, że strona nigdy nie kończy wczytywania – stąd furtka `?bez-sync=1`.

### Frontend – bez frameworka

`static/js/app.js` to IIFE z globalnym obiektem `Domownik` (`api`, `esc`, `icon`, `toast`, `taskElement`,
`miniTask`, `newChore`, `openChore`, `notifyChanged`, `todayISO`, `dayShort`) plus wspólny modal
obowiązku, toasty i skróty klawiszowe. Skrypty stron tylko rysują swój widok.

- Każde zapytanie idzie przez `Domownik.api()` – dokleja `?dzis=`. Gołe `fetch()` wyłamuje podgląd dnia.
- Po każdej zmianie danych `Domownik.notifyChanged()`; widoki słuchają `domownik:changed`.
- Nigdy `new Date('2026-08-11')` – północ UTC potrafi cofnąć dzień. `todayISO()` i ręczne rozbijanie.
- `base.html` trzyma wspólny modal, który iteruje po `categories` i `people` – każda strona idzie przez
  `_page()` w `web.py`, który je przekazuje (także 404).
- W ramce zakładki Dom Jarvisa (`window.self !== window.top`) `<html>` dostaje klasę `is-embedded`:
  bez logo i stopki. Jarvis otwiera podstrony przez `ui.navigate {view: "dom", path}`.

### Grafik pracy i planer

Natalia wgrywa w kalendarzu miesięczny grafik ze sklepu, a `planer.py` układa wokół niego obowiązki.

**Czytanie pliku (`grafik.py`).** XLSX samym stdlibem; PDF przez `pypdf` tylko jako rozpakowywacz – po
operatorach strumienia (`BT`/`Tm`/`TJ`) chodzimy sami, bo **kolejność tekstu w PDF-ie kłamie**; liczy się
współrzędna X. Pułapki:
- `extract_text(visitor_text=…)` rozjeżdża tekst ze współrzędnymi o jedno wywołanie.
- Nagłówek ma dwa „info”: kolumnę `INFO` dnia i rubryki `info` przy osobach. Granica kolumny to pierwsza
  rubryka **na prawo od `DO`** – inaczej numer sklepu (`3825`) wjeżdża jako godzina.
- XLSX ma ukryty obszar pomocniczy z godzinami jako ułamkami doby – kolumna bez godziny to nie człowiek.
- **Kod z legendy wygrywa z godzinami** (`u`/`w` = wolne, `l4`/`sw`/`wsp`/`zeb` = niedostępna).
  Jedynym źródłem prawdy jest `grafik.dostepna()`.

Import jest dwustopniowy: `POST /api/grafik/wczytaj` tylko czyta i oddaje podgląd, `PUT
/api/grafik/<osoba>/<miesiąc>` zapisuje. `grafik.js` sam wybiera kolumnę podpisaną imieniem Natalii
(`OSOBA`); okno wyboru tylko, gdy takiej nie ma albo jest kilka. Ręczne poprawki dnia (`"reczne": true`)
przeżywają ponowne wgranie miesiąca.

**Układanie (`planer.py`)** dla każdego wystąpienia: tura (`assignees[nr % liczba_osób]`), wyrównanie
długu, dostępność (dzień później, dzień wcześniej, w ostateczności druga osoba). Planer **nie trzyma
stanu** – przelicza wszystko przy każdym wywołaniu. Zasady pilnujące danych:
- Daty przesuwamy tylko od dzisiaj w przód i nigdy przy odhaczonym wystąpieniu.
- Obowiązek przeniesiony i **tam** odhaczony zostaje tam na stałe (`_sasiedni_wolny_dzien`).
- Reguła powtarzania się nie zmienia – kolejne wystąpienia liczą się od pierwotnej daty.
- Nie cofamy przed `start_date`.

`items_for_day(state, day, plan=None)` bez planu zachowuje się dokładnie jak przed planerem – bez
grafiku kalendarz musi wyglądać identycznie. `web.py` liczy `planer.rozklad()` raz na żądanie.

### PWA

`/manifest.webmanifest` (jawny `application/manifest+json` – Windows nie zna rozszerzenia) i `/sw.js`
(z katalogu głównego, inaczej zasięg tylko `/static/`) mają własne trasy. Service worker działa **siecią
najpierw**, a `/api/` pomija w całości. Przy zmianie wyglądu podbij `CACHE` w `sw.js`. Service worker
istnieje tylko w bezpiecznym kontekście (HTTPS albo localhost) – na Androidzie po `http://ip:8080`
instalacji nie będzie, dopiero po `tailscale serve` (HTTPS).

### Wygląd

`static/css/style.css` – wygląd Jarvisa (tokeny jak w `jarvis/web/static/css/app.css`: granat, cyjan
`#38e8ff`, siatka HUD, znacznik w rogu kart). **Tylko ciemny motyw.** Ikony interfejsu to sprite SVG
`templates/_ikony.html`, w szablonach `{{ icon('nazwa') }}`, w JS `Domownik.icon('nazwa')`. Emotki
zostają tylko jako dane (kategorie, działy) i przy Atomie.

`templates/_dog.html` – Atom, owczarek niemiecki (inline SVG). Animacje wiszą na klasach
`dog-tail-wrap`, `dog-head`, `dog-eyes`; kolory sierści w zmiennych `--dog-*`.

Kalendarz to CSS Grid 7 × `1fr`; `.cal-day` **musi** mieć `min-width: 0`. Karty mają `::before`
(znacznik HUD) pozycjonowany względem karty – nie dawaj karcie `position: static`.
