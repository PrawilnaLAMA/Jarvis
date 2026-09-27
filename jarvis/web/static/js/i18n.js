// Polskie nazwy i teksty używane w kilku miejscach interfejsu.

export const MONTHS = [
  'Styczeń', 'Luty', 'Marzec', 'Kwiecień', 'Maj', 'Czerwiec',
  'Lipiec', 'Sierpień', 'Wrzesień', 'Październik', 'Listopad', 'Grudzień',
];

export const MONTHS_GENITIVE = [
  'stycznia', 'lutego', 'marca', 'kwietnia', 'maja', 'czerwca',
  'lipca', 'sierpnia', 'września', 'października', 'listopada', 'grudnia',
];

// Tydzień zaczyna się w poniedziałek.
export const WEEKDAYS_SHORT = ['Pn', 'Wt', 'Śr', 'Cz', 'Pt', 'So', 'Nd'];
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

export const EVENT_TYPES = ['spotkanie', 'praca', 'nauka', 'wizyta', 'sport', 'uroczystość', 'przypomnienie'];

/** Polska odmiana liczebników: plural(5, 'wydarzenie', 'wydarzenia', 'wydarzeń'). */
export function plural(n, one, few, many) {
  const abs = Math.abs(n);
  if (abs === 1) return one;
  const mod10 = abs % 10;
  const mod100 = abs % 100;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

export function capitalize(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

/** Liczba z przecinkiem dziesiętnym. */
export function formatNumber(value, digits) {
  const text = digits == null ? String(value) : Number(value).toFixed(digits);
  return text.replace('.', ',');
}
