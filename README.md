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
- **Dom (Domownik)** – obowiązki domowe, kalendarz, lista zakupów i grafik pracy Natalii, wbudowane
  w Jarvisa: „co mam dziś do zrobienia?”, „zrobiłem pranie”, „dodaj trening w każdą środę o 18”,
  „dodaj do zakupów mleko i chleb”, „kupiłem mleko”, „czy Natalia jutro pracuje?”, „otwórz listę
  zakupów”. Zakładka **Dom** pokazuje całego Domownika, a telefony wchodzą na niego przez przeglądarkę.
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

Uruchomienie: dwuklik w `jarvis.bat` (albo `jarvis.pyw`) – Jarvis startuje w tle, bez okna konsoli;
logi są w `data/jarvis.log`. Z logami na ekranie: `py -m jarvis` w terminalu.

Żeby Jarvis włączał się razem z Windowsem, zaznacz **Ustawienia → Interfejs → Uruchamiaj razem
z Windowsem** (wpis widać też w Menedżerze zadań → Aplikacje autostartu). Ponowne uruchomienie, gdy
Jarvis już działa, tylko przywołuje jego okno – nie startuje drugiej kopii.

### Raspberry Pi 4/5 (Raspberry Pi OS 64-bit)

```bash
make pi-setup   # pakiety systemowe (GTK/WebKit, PortAudio) + venv + zależności
make pi-run     # Jarvis na pełnym ekranie
```

Przy pierwszym uruchomieniu pobierane są modele wykrywania „Hey Jarvis” (kilka MB, do `data/models`).

Ustaw strefę czasową – Domownik liczy dni według `date.today()`, więc na czasie UTC obowiązki
zmieniałyby się o 2:00 w nocy:

```bash
sudo timedatectl set-timezone Europe/Warsaw
```

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
Domownik) też są w zakładce **Ustawienia** i zapisują się w `data/settings.json`.

### Domownik (zakładka Dom)

Domownik – obowiązki, kalendarz, zakupy i grafik – działa razem z Jarvisem, na własnym porcie
(domyślnie 8080). Osobnego serwera (`start-serwer.bat` ze starego repozytorium HouseholdChoresApp) już
nie uruchamiaj – zająłby port, a jego dane rozjechałyby się z danymi Jarvisa.

- **Telefony:** w tej samej sieci Wi-Fi otwórz adres z **Ustawienia → Domownik** (np.
  `http://192.168.1.20:8080`) i dodaj stronę do ekranu głównego. Za pierwszym razem Windows zapyta o
  zgodę zapory – zezwól w sieci prywatnej. Domownik działa, dopóki działa Jarvis.
- **Poza domem:** zainstaluj [Tailscale](https://tailscale.com) na komputerze z Jarvisem i na telefonach
  (to samo konto), a na komputerze z Jarvisem uruchom `tailscale serve --bg 8080`. Dostajesz stały adres
  z HTTPS (np. `https://jarvis.twoj-tailnet.ts.net`), widoczny tylko dla Twoich urządzeń – dzięki HTTPS
  Android zaproponuje też instalację aplikacji.
- **Dane:** `data/domownik/chores.json`, a codzienne kopie (ostatnie 14) w `data/domownik/kopie/`.
  Kopię całości pobierzesz w zakładce **Obowiązki → Pobierz kopię (JSON)**; tam też można ją wczytać.
- **Dwa Jarvisy** (np. na komputerze i na Raspberry Pi): serwer Domownika ma działać tylko w jednym.
  W drugim wyłącz „Uruchamiaj Domownika w Jarvisie” i wpisz adres pierwszego (np.
  `http://raspberrypi.local:8080`).
- Domownik nie zna godzin, więc godzina trafia do nazwy („Trening 18:00”), a przypomnień nie ma.

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
