// Polskie nazwy i teksty używane w kilku miejscach interfejsu.

export const MONTHS_GENITIVE = [
  'stycznia', 'lutego', 'marca', 'kwietnia', 'maja', 'czerwca',
  'lipca', 'sierpnia', 'września', 'października', 'listopada', 'grudnia',
];

// Tydzień zaczyna się w poniedziałek.
export const WEEKDAYS_LONG = ['poniedziałek', 'wtorek', 'środa', 'czwartek', 'piątek', 'sobota', 'niedziela'];

/** Krótka nazwa stanu asystenta (pasek statusu). */
export const STATE_LABELS = {
  idle: 'Czekam',
  listening: 'Słucham',
  transcribing: 'Rozpoznaję mowę',
  thinking: 'Myślę',
  speaking: 'Mówię',
  follow_up: 'Słucham dalej',
  muted: 'Mikrofon wyciszony',
  offline: 'Głos niedostępny',
};

/** Podpowiedź pod kulą, gdy nie są wyświetlane napisy. */
export const STATE_HINTS = {
  idle: 'Powiedz „Hej Jarvis”…',
  listening: 'Słucham…',
  transcribing: 'Rozpoznaję mowę…',
  thinking: 'Myślę…',
  speaking: 'Mówię…',
  follow_up: 'Słucham dalej — możesz mówić bez „Hej Jarvis”…',
  muted: 'Mikrofon jest wyciszony.',
  offline: 'Głos jest niedostępny — możesz pisać na czacie.',
};

/** Co Jarvis zrobił – po ludzku, w czacie (nazwa funkcji zostaje w szczegółach). Nowe narzędzie → nowy wpis. */
export const TOOL_LABELS = {
  house_agenda: 'Plan domu',
  chore_done: 'Odhaczenie obowiązku',
  chore_add: 'Nowy wpis w kalendarzu',
  chore_delete: 'Usunięcie obowiązku',
  chore_info: 'Szczegóły obowiązku',
  open_domownik: 'Zakładka Dom',
  shopping_list: 'Lista zakupów',
  shopping_update: 'Zmiana listy zakupów',
  send_message: 'Wysłanie wiadomości',
  search_web: 'Wyszukiwanie w Google',
  play_youtube: 'YouTube',
  shutdown_computer: 'Wyłączanie komputera',
  cancel_shutdown: 'Anulowanie wyłączenia',
  stay_silent: 'Cisza',
  clear_conversation: 'Czyszczenie pamięci rozmowy',
  open_app: 'Otwieranie',
  close_app: 'Zamykanie programu',
  media: 'Dźwięk i muzyka',
  pc: 'Komputer',
  timer: 'Minutnik',
  system_info: 'Stan komputera',
};

export function capitalize(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

/** Liczba z przecinkiem dziesiętnym. */
export function formatNumber(value, digits) {
  const text = digits == null ? String(value) : Number(value).toFixed(digits);
  return text.replace('.', ',');
}
