// Cyfry minutnika w kuli. Każdy znak ma własną komórkę o stałej szerokości, więc liczby nie „skaczą”
// przy zmianie cyfr. Zmieniona cyfra przewija się jak w liczniku: przy odliczaniu nowa wjeżdża z góry,
// przy dodawaniu czasu z dołu. Czcionka Oxanium (fonts/, licencja OFL).

import { reducedMotion } from './reveal.js';

export const DIGIT_EM = 0.62;
export const SEP_EM = 0.3;
const ROLL_MS = 420;
const ROLL_EASE = 'cubic-bezier(0.2, 0.8, 0.2, 1)';
const SHIFT = '0.5em';

/** „4:59”, „12:05”, „1:02:07”. Sekundy zaokrąglone w górę: przez ostatnią sekundę widać „0:01”. */
export function formatClock(seconds) {
  const total = Math.max(0, Math.ceil(seconds - 1e-3));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
}

/** Szerokość tekstu w em – CSS dopasowuje do niej wielkość cyfr, żeby zmieściły się w kuli. */
export function clockWidth(text) {
  let em = 0;
  for (const ch of text) em += ch === ':' ? SEP_EM : DIGIT_EM;
  return em;
}

export class Clock {
  constructor(el) {
    this.el = el;
    this.text = null;
    this.cells = [];
  }

  /** `direction`: -1 – odliczanie (nowa cyfra z góry), 1 – w górę (z dołu), 0 – bez animacji. */
  set(text, direction = -1) {
    if (text === this.text) return;
    const prev = this.text;
    this.text = text;
    if (prev == null || shape(prev) !== shape(text)) {
      // inny układ („10:00” → „9:59”) – komórki od nowa, a całość tylko lekko przygasa
      this._build(text);
      this.el.style.setProperty('--em', clockWidth(text).toFixed(3));
      if (prev != null && direction && !reducedMotion.matches) {
        this.el.animate([{ opacity: 0.4 }, { opacity: 1 }], { duration: 320, easing: 'ease-out' });
      }
      return;
    }
    [...text].forEach((ch, i) => {
      if (ch !== prev[i]) this._roll(this.cells[i], ch, direction);
    });
  }

  _build(text) {
    this.cells = [...text].map((ch) => {
      const cell = document.createElement('span');
      cell.className = ch === ':' ? 'clock-cell is-sep' : 'clock-cell';
      cell.append(glyph(ch));
      return cell;
    });
    this.el.replaceChildren(...this.cells);
  }

  _roll(cell, ch, direction) {
    // szybkie zmiany (kółko myszy) – starsze cyfry znikają od razu, zostaje tylko ostatnia
    while (cell.children.length > 1) cell.firstElementChild.remove();
    const old = cell.firstElementChild;
    const next = glyph(ch);
    cell.append(next);
    if (!old) return;
    if (!direction || reducedMotion.matches) {
      old.remove();
      return;
    }
    const from = direction < 0 ? `-${SHIFT}` : SHIFT;
    const to = direction < 0 ? SHIFT : `-${SHIFT}`;
    const timing = { duration: ROLL_MS, easing: ROLL_EASE, fill: 'forwards' };
    old.animate(
      [{ transform: 'none', opacity: 1, filter: 'blur(0)' }, { transform: `translateY(${to})`, opacity: 0, filter: 'blur(0.04em)' }],
      timing,
    ).onfinish = () => old.remove();
    next.animate(
      [{ transform: `translateY(${from})`, opacity: 0, filter: 'blur(0.04em)' }, { transform: 'none', opacity: 1, filter: 'blur(0)' }],
      { ...timing, fill: 'none' },
    );
  }
}

function glyph(ch) {
  const span = document.createElement('span');
  span.className = 'clock-glyph';
  span.textContent = ch;
  return span;
}

function shape(text) {
  return text.replace(/\d/g, '0');
}
