// Wskaźnik na żywo: aktualny wynik detektora „Hej Jarvis” (audio.level z polem wake)
// na tle ustawionego progu. Animowany tylko, gdy widok ustawień jest widoczny.

import { h, clamp } from './dom.js';
import { formatNumber } from './i18n.js';

const ATTACK = 0.6;
const RELEASE = 0.06;
const STALE_MS = 400;
const NO_SIGNAL_MS = 3000;
const PEAK_HOLD_MS = 1200;

export function createWakeMeter() {
  const fill = h('div', { class: 'meter-fill' });
  const peak = h('div', { class: 'meter-peak' });
  const mark = h('div', { class: 'meter-mark' }, h('span', { class: 'meter-mark-label' }, 'próg'));
  const valueEl = h('span', { class: 'meter-value' }, '0,00');
  const caption = h('p', { class: 'meter-caption' });
  const el = h(
    'div',
    { class: 'meter', 'aria-hidden': 'true' },
    h('div', { class: 'meter-head' }, h('span', null, 'Wynik słowa wywołania na żywo'), valueEl),
    h('div', { class: 'meter-bar' }, fill, peak, mark),
    caption,
  );

  let target = 0;
  let value = 0;
  let peakValue = 0;
  let peakAt = 0;
  let lastAt = -Infinity;
  let threshold = 0.5;
  let running = false;
  let raf = 0;
  let lastFrame = 0;
  let shownText = '';
  let shownCaption = '';

  function frame(now) {
    if (!running) return;
    const dt = Math.min(0.1, Math.max(0.001, (now - lastFrame) / 1000));
    lastFrame = now;
    const goal = now - lastAt < STALE_MS ? target : 0;
    const rate = goal > value ? ATTACK : RELEASE;
    value += (goal - value) * (1 - Math.pow(1 - rate, dt * 60));
    if (value >= peakValue) {
      peakValue = value;
      peakAt = now;
    } else if (now - peakAt > PEAK_HOLD_MS) {
      peakValue = Math.max(value, peakValue - dt * 0.5);
    }

    fill.style.transform = `scaleX(${value.toFixed(4)})`;
    peak.style.left = `${(peakValue * 100).toFixed(2)}%`;
    el.classList.toggle('is-hot', value >= threshold);

    const text = formatNumber(value, 2);
    if (text !== shownText) valueEl.textContent = shownText = text;
    const noSignal = now - lastAt > NO_SIGNAL_MS;
    const captionText = noSignal
      ? 'Brak danych z mikrofonu. Gdy Jarvis nasłuchuje, powiedz „Hej Jarvis”, aby sprawdzić próg.'
      : 'Powiedz „Hej Jarvis” — wynik powinien przekraczać próg, a zwykła mowa nie.';
    if (captionText !== shownCaption) caption.textContent = shownCaption = captionText;

    raf = requestAnimationFrame(frame);
  }

  return {
    el,
    /** Nowy pomiar wyniku 0..1. */
    push(score) {
      const v = Number(score);
      if (!Number.isFinite(v)) return;
      target = clamp(v, 0, 1);
      lastAt = performance.now();
    },
    setThreshold(v) {
      const n = Number(v);
      threshold = Number.isFinite(n) ? clamp(n, 0, 1) : 0.5;
      mark.style.left = `${(threshold * 100).toFixed(2)}%`;
    },
    start() {
      if (running) return;
      running = true;
      lastFrame = performance.now();
      raf = requestAnimationFrame(frame);
    },
    stop() {
      running = false;
      cancelAnimationFrame(raf);
    },
  };
}
