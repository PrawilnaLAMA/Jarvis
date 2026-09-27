// Operacje na datach lokalnych (bez stref czasowych).

import { MONTHS_GENITIVE, WEEKDAYS_LONG } from './i18n.js';

export const pad2 = (n) => String(n).padStart(2, '0');

export function toISODate(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

export function addDays(d, n) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}

/** 0 = poniedziałek … 6 = niedziela */
export function weekdayIndex(d) {
  return (d.getDay() + 6) % 7;
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
