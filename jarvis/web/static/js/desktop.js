// Kulka na pulpicie (Windows, okno pywebview – jarvis/ui/desktop.py). Oknem rządzi Python: w trybie kulki
// widać z niego tylko koło w miejscu --orb-x/--orb-y, a strona rysuje tam kulkę nad resztą interfejsu.
// W zwykłej przeglądarce nie ma window.pywebview, więc nic się tu nie dzieje.

import { $ } from './dom.js';
import { Orb } from './orb.js';
import { assistantState } from './store.js';

const DRAG_THRESHOLD = 4; // px – mniej to kliknięcie, więcej to przeciąganie kulki

export function initDesktop({ store, socket, onModeChange }) {
  const root = document.documentElement;
  const box = $('#desk-orb');
  const hidden = [$('.topbar'), $('#main')]; // pod kulką – bez fokusu i klawiatury
  let orb = null;
  let api = null;

  window.jarvisDesktop = { setMode, setOrb };

  if (window.pywebview && window.pywebview.api) start();
  else window.addEventListener('pywebviewready', start, { once: true });

  async function start() {
    api = window.pywebview && window.pywebview.api;
    if (!api || typeof api.desktop_state !== 'function') return;
    let state;
    try {
      state = await api.desktop_state();
    } catch {
      return;
    }
    if (!state || !state.desktop) return;
    root.dataset.desktop = '';
    orb = new Orb($('#desk-orb-canvas'));
    socket.on('audio.level', (data) => orb.setLevel(data.source, data.level));
    const syncState = (s) => orb.setState(assistantState(s));
    store.subscribe(syncState);
    syncState(store.get());
    bindOrb();
    bindWindowControls();
    if (Array.isArray(state.orb)) setOrb(...state.orb);
    setMode(state.mode);
  }

  function setMode(mode) {
    root.dataset.mode = mode;
    const collapsed = mode === 'orb';
    for (const el of hidden) el.inert = collapsed;
    if (collapsed) document.activeElement?.blur?.();
    orb?.setActive(collapsed);
    onModeChange?.(mode);
  }

  function setOrb(x, y, size) {
    root.style.setProperty('--orb-x', `${x}px`);
    root.style.setProperty('--orb-y', `${y}px`);
    root.style.setProperty('--orb-size', `${size}px`);
  }

  function bindOrb() {
    let press = null;
    box.addEventListener('pointerdown', (event) => {
      if (event.button === 0) press = { x: event.screenX, y: event.screenY, moved: false };
    });
    window.addEventListener('pointermove', (event) => {
      if (press && Math.hypot(event.screenX - press.x, event.screenY - press.y) > DRAG_THRESHOLD) press.moved = true;
    });
    window.addEventListener('pointerup', (event) => {
      if (!press || event.button !== 0) return;
      const moved = press.moved || Math.hypot(event.screenX - press.x, event.screenY - press.y) > DRAG_THRESHOLD;
      press = null;
      if (moved) api.orb_moved();
      else if (root.dataset.mode === 'orb') api.expand();
    });
    box.addEventListener('contextmenu', (event) => {
      event.preventDefault();
      api.orb_menu();
    });
    box.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        api.expand();
      }
    });
  }

  function bindWindowControls() {
    $('#win-collapse').addEventListener('click', () => api.collapse());
    $('#win-close').addEventListener('click', () => api.quit());
    // okno bez ramki nie ma krawędzi do rozciągania – podwójne kliknięcie paska: cały ekran / z powrotem
    $('.topbar').addEventListener('dblclick', (event) => {
      if (!event.target.closest('a, button, input')) api.toggle_maximize();
    });
  }
}
