# Jarvis

Polski asystent głosowy z interfejsem w HTML. Mówisz „Hej Jarvis…”, a on rozumie polecenie
(model językowy z narzędziami), wykonuje je i odpowiada naturalnym głosem. W trakcie odpowiedzi
możesz mu przerwać – przestanie mówić i odniesie się do tego, co powiedziałeś.

Działa na Windows i Raspberry Pi 4/5 (64-bit) z ekranem.

## Co potrafi

- **Rozmowa** – odpowiada na pytania, pamięta kontekst kilku ostatnich wymian.
- **Discord i Messenger** – „napisz do Piotrka i Natana, że spóźnię się 10 minut”, „napisz Natalii na
  Messengerze, że kupię mleko” (wiadomość wychodzi z Twojego konta); czyta na głos nowe wiadomości od
  kontaktów, a „odpisz jej, że OK” trafia do osoby, która napisała ostatnia, tym samym komunikatorem.
- **Kalendarz (Domownik)** – obowiązki domowe, lista zakupów i grafik pracy Natalii z aplikacji
  Domownik (repozytorium HouseholdChoresApp): „co mam dziś do zrobienia?”, „zrobiłem pranie”, „dodaj trening w każdą
  środę o 18”, „dodaj do zakupów mleko i chleb”, „kupiłem mleko”, „czy Natalia jutro pracuje?”,
  „otwórz kalendarz”. Zakładka **Kalendarz** pokazuje Domownika.
- **YouTube i Google** – „puść Bohemian Rhapsody”, „wyszukaj pogodę we Wrocławiu”.
- **Wyłączanie komputera** – z 30-sekundowym opóźnieniem („anuluj wyłączenie” przerywa).
- **Cisza** – „stop”, „dobra, wystarczy” – Jarvis nic nie odpowiada.

Po odpowiedzi Jarvis przez kilka sekund słucha dalej, więc można kontynuować bez „Hej Jarvis”.

## Instalacja

### Windows

Wymagany Python 3.11+.

```cmd
py -m pip install -r requirements.txt
```

Uruchomienie: dwuklik w `jarvis.bat` albo `py -m jarvis`.

### Raspberry Pi 4/5 (Raspberry Pi OS 64-bit)

```bash
make pi-setup   # pakiety systemowe (GTK/WebKit, PortAudio) + venv + zależności
make pi-run     # Jarvis na pełnym ekranie
```

Przy pierwszym uruchomieniu pobierane są modele wykrywania „Hey Jarvis” (kilka MB, do `data/models`).

## Konfiguracja

Klucze API trzymane są w pliku `.env` (wzór: `.env.example`), ale najprościej wpisać je w aplikacji:
**Ustawienia → Klucze API**.

| Klucz | Do czego |
|---|---|
| `GROQ_API_KEY` | model językowy i rozpoznawanie mowy (Whisper) – [console.groq.com](https://console.groq.com/keys) |
| `CEREBRAS_API_KEY` | opcjonalny zapasowy model, używany, gdy Groq zwróci limit zapytań |
| `DISCORD_USER_TOKEN` | wysyłanie i czytanie wiadomości na Discordzie |

Kontakty (nazwa, ID kanału Discorda i/lub link do czatu Messengera, inne formy imienia) ustawia się
w **Ustawienia → Kontakty**. Stare wpisy `CHANNEL_<NAZWA>=<id>` z `.env` są importowane automatycznie
przy pierwszym starcie.

### Messenger

Messenger nie ma API dla prywatnych kont, a prywatne czaty są szyfrowane end-to-end, więc Jarvis
korzysta z messenger.com w osobnym oknie Chrome (bez Chrome'a – Edge albo Chromium) z własnym
profilem w `data/messenger`. Włącz go w **Ustawienia → Messenger**, zaloguj się w oknie, które się
otworzy, a potem możesz je schować. Link do czatu kontaktu skopiuj z paska adresu messenger.com
(np. `https://www.messenger.com/e2ee/t/123…`) albo wybierz z podpowiedzi w polu kontaktu.

- Nowe wiadomości Jarvis czyta z listy czatów, bez otwierania rozmowy, więc u nadawcy nie pojawia
  się „wyświetlono”. Ogłasza tylko świeże wiadomości (do 5 minut).
- Na nowym urządzeniu Messenger nie pokazuje starej historii zaszyfrowanych czatów („Wiadomości
  i rozmowy są chronione…”). Nowe wiadomości przychodzą normalnie.
- To automatyzacja konta niezgodna z regulaminem Meta – ryzyko blokady konta jest małe, ale istnieje.

Pozostałe ustawienia (głos, tempo mowy, czułość „Hey Jarvis”, tryb przerywania, urządzenia audio,
adres Domownika) też są w zakładce **Ustawienia** i zapisują się w `data/settings.json`.

### Domownik

Kalendarzem jest osobna aplikacja Domownik – Jarvis rozmawia z jej serwerem przez HTTP, więc serwer
musi być uruchomiony (`start-serwer.bat` w katalogu Domownika). Domyślny adres to
`http://127.0.0.1:8080`; po przeniesieniu Domownika na Raspberry Pi wpisz jego adres w
**Ustawienia → Domownik** (np. `http://domownik.local:8080`). Domownik nie zna godzin, więc godzina
trafia do nazwy („Trening 18:00”), a przypomnień o wydarzeniach nie ma.

### Limity darmowego planu Groq

Darmowy plan to ok. 8 000 tokenów na minutę, a jedno polecenie zużywa ok. 1 300–1 500. Przy kilku
poleceniach pod rząd Jarvis może chwilę poczekać na limit. Rozwiązania: dodać `CEREBRAS_API_KEY`
(darmowy zapas) albo włączyć płatny plan Developer w Groq – przy domowym użyciu to grosze.

## Uruchamianie – opcje

```
py -m jarvis              # okno aplikacji
py -m jarvis --browser    # interfejs w przeglądarce
py -m jarvis --no-voice   # bez mikrofonu i dźwięku, tylko komendy wpisywane
py -m jarvis --fullscreen # pełny ekran
py -m jarvis --debug      # szczegółowe logi i narzędzia deweloperskie w oknie
```

Logi: `data/jarvis.log`.

## Przerywanie a głośniki

Mikrofon słyszy też głos Jarvisa. Filtr echa rozpoznaje, że mówisz Ty, gdy Twój głos w mikrofonie
jest co najmniej tak głośny jak echo z głośników – wtedy Jarvis ścisza się i milknie po ok. sekundzie.
Przy bardzo głośnych głośnikach blisko mikrofonu przerwij mówiąc „Hej Jarvis” albo ustaw tryb
przerywania „Tylko Hej Jarvis”. Najlepiej działa mikrofon blisko Ciebie albo słuchawki.

## Dla programistów

```
py -m pip install -r requirements-dev.txt
py -m pytest          # testy
py -m ruff check .    # lint
```

Architekturę opisuje `CLAUDE.md`. Skrypty planu zajęć USOS są w `scripts/usos/`.
