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

export function capitalize(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

/** Liczba z przecinkiem dziesiętnym. */
export function formatNumber(value, digits) {
  const text = digits == null ? String(value) : Number(value).toFixed(digits);
  return text.replace('.', ',');
}
