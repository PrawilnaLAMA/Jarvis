// Pomocnicze funkcje DOM. Tekst trafia do dokumentu wyłącznie przez textContent/append,
// nigdy przez innerHTML – dane z serwera i od użytkownika są więc zawsze bezpieczne.

const SVG_NS = 'http://www.w3.org/2000/svg';
const XLINK_NS = 'http://www.w3.org/1999/xlink';

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

/**
 * Tworzy element, np. h('button', { class: 'btn', onClick: fn }, 'Zapisz').
 * Wartości null/false są pomijane; `value`, `checked` i `selected` ustawiane jako właściwości.
 */
export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  if (props) setProps(el, props);
  appendChildren(el, children);
  return el;
}

function setProps(el, props) {
  for (const key of Object.keys(props)) {
    const value = props[key];
    if (value == null || value === false) continue;
    if (key === 'class') {
      el.className = value;
    } else if (key === 'text') {
      el.textContent = value;
    } else if (key === 'dataset') {
      Object.assign(el.dataset, value);
    } else if (key === 'style' && typeof value === 'object') {
      for (const name of Object.keys(value)) el.style.setProperty(name, value[name]);
    } else if (key.startsWith('on') && typeof value === 'function') {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === 'value' || key === 'checked' || key === 'selected') {
      el[key] = value;
    } else {
      el.setAttribute(key, value === true ? '' : String(value));
    }
  }
}

export function appendChildren(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false || child === true) continue;
    el.append(child instanceof Node ? child : String(child));
  }
  return el;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

/** Ikona z duszka SVG w index.html (symbol #i-<name>). */
export function icon(name, className = 'icon') {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', className);
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const use = document.createElementNS(SVG_NS, 'use');
  setIconHref(use, name);
  svg.append(use);
  return svg;
}

export function setIconHref(use, name) {
  use.setAttribute('href', `#i-${name}`);
  use.setAttributeNS(XLINK_NS, 'xlink:href', `#i-${name}`); // starsze WebKity
}

let idCounter = 0;
export function uid(prefix = 'id') {
  idCounter += 1;
  return `${prefix}-${idCounter}`;
}

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

/**
 * Przebudowuje zawartość kontenera, zachowując fokus na elemencie o tym samym data-focus
 * (np. po odświeżeniu listy). Gdy go już nie ma, fokus trafia do `fallback` (jeśli podano).
 */
export function preserveFocus(container, rebuild, fallback) {
  const active = document.activeElement;
  const key = active && container.contains(active) && active.dataset ? active.dataset.focus : null;
  rebuild();
  if (!key) return;
  const target = findFocusable(container, key) || (fallback && findFocusable(container, fallback));
  if (target) target.focus();
}

export function findFocusable(container, key) {
  return Array.from(container.querySelectorAll('[data-focus]')).find((el) => el.dataset.focus === key) || null;
}

/** Nasłuch zmian media query działający także w starszych silnikach. */
export function onMediaChange(query, handler) {
  if (typeof query.addEventListener === 'function') query.addEventListener('change', handler);
  else if (typeof query.addListener === 'function') query.addListener(handler);
}
