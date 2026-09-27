// Operacje na datach lokalnych (bez stref czasowych – kalendarz operuje na dniach).

import { MONTHS_GENITIVE, WEEKDAYS_LONG, WEEKDAYS_SHORT } from './i18n.js';

// Nazwy dni tak, jak zapisuje je backend (Event.days), od poniedziałku.
export const WEEKDAYS_EN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

export const pad2 = (n) => String(n).padStart(2, '0');

export function toISODate(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

export function parseISODate(text) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(text || ''));
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return d.getMonth() === Number(m[2]) - 1 ? d : null;
}

export function addDays(d, n) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}

/** 0 = poniedziałek … 6 = niedziela */
export function weekdayIndex(d) {
  return (d.getDay() + 6) % 7;
}

/** Pierwszy dzień (poniedziałek) siatki 6×7 dla danego miesiąca. */
export function gridStart(year, month) {
  const first = new Date(year, month, 1);
  return addDays(first, -weekdayIndex(first));
}

/** HH:MM z uniksowego znacznika czasu w sekundach (brak = teraz). */
export function formatClock(ts) {
  const d = typeof ts === 'number' && Number.isFinite(ts) ? new Date(ts * 1000) : new Date();
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

/** „poniedziałek, 28 września 2026” */
export function formatLongDate(d, withYear = true) {
  const base = `${WEEKDAYS_LONG[weekdayIndex(d)]}, ${d.getDate()} ${MONTHS_GENITIVE[d.getMonth()]}`;
  return withYear ? `${base} ${d.getFullYear()}` : base;
}

/**
 * Normalizuje godzinę do HH:MM. Zwraca '' dla pustej wartości i null dla niepoprawnej.
 * Przyjmuje też „9”, „930”, „9.30” – przydatne, gdy przeglądarka nie ma pola typu time.
 */
export function normalizeTime(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  const m = /^(\d{1,2})(?:[:.h]?(\d{2}))?(?::\d{2})?$/.exec(text);
  if (!m) return null;
  const hours = Number(m[1]);
  const minutes = m[2] ? Number(m[2]) : 0;
  if (hours > 23 || minutes > 59) return null;
  return `${pad2(hours)}:${pad2(minutes)}`;
}

/** Normalizuje datę do RRRR-MM-DD (przyjmuje też DD.MM.RRRR). '' = pusta, null = błędna. */
export function normalizeDate(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  if (parseISODate(text)) return text;
  const m = /^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/.exec(text);
  if (!m) return null;
  const iso = `${m[3]}-${pad2(Number(m[2]))}-${pad2(Number(m[1]))}`;
  return parseISODate(iso) ? iso : null;
}

/** Opis dni cyklicznego wydarzenia: „codziennie”, „w dni robocze”, „co tydzień: pn, śr”. */
export function describeDays(days) {
  const set = new Set(days || []);
  const picked = WEEKDAYS_EN.map((name, i) => (set.has(name) ? i : -1)).filter((i) => i >= 0);
  if (picked.length === 7) return 'codziennie';
  if (picked.join() === '0,1,2,3,4') return 'w dni robocze';
  if (picked.join() === '5,6') return 'w weekendy';
  return `co tydzień: ${picked.map((i) => WEEKDAYS_SHORT[i].toLowerCase()).join(', ')}`;
}

export function compareOccurrences(a, b) {
  return (
    String(a.occurrence_date).localeCompare(String(b.occurrence_date)) ||
    String(a.start || '').localeCompare(String(b.start || '')) ||
    String(a.desc || '').localeCompare(String(b.desc || ''), 'pl')
  );
}

/**
 * Rozwija wydarzenia w wystąpienia w zakresie dat (włącznie) – zapas na wypadek,
 * gdyby backend nie udostępniał /api/calendar/occurrences.
 */
export function expandOccurrences(events, startISO, endISO) {
  const start = parseISODate(startISO);
  const end = parseISODate(endISO);
  const result = [];
  if (!start || !end) return result;
  for (const event of events || []) {
    if (event.date) {
      if (event.date >= startISO && event.date <= endISO) result.push({ ...event, occurrence_date: event.date });
      continue;
    }
    const days = new Set(event.days || []);
    if (!days.size) continue;
    for (let d = start; d <= end; d = addDays(d, 1)) {
      if (days.has(WEEKDAYS_EN[weekdayIndex(d)])) result.push({ ...event, occurrence_date: toISODate(d) });
    }
  }
  return result.sort(compareOccurrences);
}
