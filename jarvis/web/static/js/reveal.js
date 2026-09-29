// Wejście i wyjście interfejsu: części widoku pojawiają się po kolei (pasek, czat, napisy, przyciski).
// Używa tego start strony (app.js) i rozwijanie kulki na pulpicie (desktop.js). Przy ograniczonym ruchu – nic.

import { $ } from './dom.js';

export const EASE_OUT = 'cubic-bezier(0.16, 1, 0.3, 1)';
export const EASE_IN_OUT = 'cubic-bezier(0.65, 0, 0.35, 1)';
export const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

const FROM = {
  down: 'translateY(-14px)',
  up: 'translateY(16px)',
  left: 'translateX(32px)',
  zoom: 'scale(0.985)',
};

let running = [];

/** Części widocznego widoku: [element, skąd wjeżdża, opóźnienie ms]. */
function parts() {
  const view = document.querySelector('.view:not([hidden])');
  if (view && view.id === 'view-jarvis') {
    const chatColumn = window.matchMedia('(min-width: 1000px)').matches; // węziej czat jest szufladą
    return [
      [$('.topbar'), 'down', 80],
      [$('#setup-banner'), 'down', 160],
      [chatColumn ? $('#chat') : null, 'left', 200],
      [$('#captions'), 'up', 300],
      [$('#controls'), 'up', 370],
      [$('#timer-edit-controls'), 'up', 370],
    ];
  }
  return [
    [$('.topbar'), 'down', 80],
    [view, 'zoom', 160],
  ];
}

function play(el, keyframes, options) {
  if (!el || el.hidden || typeof el.animate !== 'function') return;
  running.push(el.animate(keyframes, options));
}

export function cancelUI() {
  for (const animation of running) animation.cancel();
  running = [];
}

/** Interfejs wchodzi po kolei; `delay` przesuwa całą sekwencję. */
export function enterUI(delay = 0) {
  cancelUI();
  if (reducedMotion.matches) return;
  for (const [el, from, at] of parts()) {
    play(el, [{ opacity: 0, transform: FROM[from] }, { opacity: 1, transform: 'none' }], {
      duration: 620,
      delay: delay + at,
      easing: EASE_OUT,
      fill: 'backwards',
    });
  }
}

/** Interfejs szybko znika (zwijanie do kulki); zostaje niewidoczny aż do cancelUI(). */
export function leaveUI(duration = 200) {
  cancelUI();
  if (reducedMotion.matches) return;
  for (const [el, from] of parts()) {
    play(el, [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: FROM[from] }], {
      duration,
      easing: 'ease-in',
      fill: 'forwards',
    });
  }
}
