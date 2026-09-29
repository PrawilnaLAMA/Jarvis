// Kulka na pulpicie (Windows, okno pywebview – jarvis/ui/desktop.py). Oknem rządzi Python: w trybie kulki
// widać z niego tylko koło w miejscu --orb-x/--orb-y, a strona rysuje tam kulkę nad resztą interfejsu.
// W zwykłej przeglądarce nie ma window.pywebview, więc nic się tu nie dzieje.
//
// Rozwinięcie: Python powiększa koło (region okna), a strona w tym samym czasie rysuje na jego brzegu
// świecącą krawędź, przenosi dużą kulę z miejsca małej na jej miejsce (FLIP) i rozkłada interfejs.
// Zwijanie – odwrotnie: interfejs gaśnie, kula wraca do kulki, koło zamyka się na niej.

import { $, clamp } from './dom.js';
import { Orb } from './orb.js';
import { assistantState } from './store.js';
import { EASE_IN_OUT, cancelUI, enterUI, leaveUI, reducedMotion } from './reveal.js';

const DRAG_THRESHOLD = 4; // px – mniej to kliknięcie, więcej to przeciąganie kulki
const FLIGHT_MS = 760; // przelot kuli przy rozwijaniu (dłużej niż koło – kula dolatuje już w pełnym oknie)
const FLIGHT_EASE = 'cubic-bezier(0.22, 1, 0.36, 1)';
const RING_WIDTH = 38; // px – świecący pas przy brzegu koła
const TAU = Math.PI * 2;

export function initDesktop({ store, socket, orb: bigOrb, isOrbView }) {
  const root = document.documentElement;
  const box = $('#desk-orb');
  const wrap = $('#orb-wrap');
  const hidden = [$('.topbar'), $('#main')]; // pod kulką – bez fokusu i klawiatury
  let orb = null;
  let api = null;
  let ring = null;
  let flight = null;
  let finish = 0;

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
    ring = createRing();
    bindOrb();
    bindWindowControls();
    if (Array.isArray(state.orb)) setOrb(...state.orb);
    setMode(state.mode);
  }

  /**
   * Tryb okna. `anim` (od Pythona, piksele CSS): {cx, cy, r0, r1, ms, ease: "out"|"in_out", at} – koło o środku
   * (cx, cy) zmienia promień z r0 na r1 w ms milisekund od chwili `at` (ms czasu ściennego, jak Date.now()).
   */
  function setMode(mode, anim) {
    const collapsed = mode === 'orb';
    const animate = Boolean(anim) && !reducedMotion.matches;
    const wait = animate && anim.at ? clamp(anim.at - Date.now(), 0, 200) : 0;
    clearTimeout(finish);
    flight?.cancel();
    flight = null;
    for (const el of hidden) el.inert = collapsed;
    if (collapsed) document.activeElement?.blur?.();

    if (!collapsed) {
      root.dataset.mode = 'full';
      orb?.setActive(false);
      const showOrb = isOrbView();
      bigOrb.setActive(showOrb);
      if (!animate) {
        delete root.dataset.anim;
        cancelUI();
        return;
      }
      root.dataset.anim = 'open';
      // krawędź minimalnie za regionem – strona pokazuje klatkę później niż system okno, więc i tak jest w kole
      ring?.play(anim, wait + 6);
      if (showOrb) {
        bigOrb.playIntro(1150);
        const from = flightFrom();
        if (from) {
          flight = wrap.animate([{ transform: from }, { transform: 'none' }], {
            duration: FLIGHT_MS,
            delay: wait,
            easing: FLIGHT_EASE,
            fill: 'backwards',
          });
        }
      }
      enterUI(wait + (showOrb ? 60 : 0));
      finish = setTimeout(() => delete root.dataset.anim, wait + Math.max(anim.ms, FLIGHT_MS));
      return;
    }

    if (!animate) {
      root.dataset.mode = 'orb';
      delete root.dataset.anim;
      cancelUI();
      bigOrb.setActive(false);
      orb?.setActive(true);
      return;
    }
    // zwijanie: interfejs gaśnie, kula leci do kulki razem z zamykającym się kołem
    root.dataset.anim = 'close';
    orb?.setActive(true);
    leaveUI(Math.min(220, anim.ms / 2));
    // przy zamykaniu krawędź trochę wyprzedza region – spóźniona wypadłaby poza koło i zniknęła
    ring?.play(anim, wait - 24);
    const to = isOrbView() && flightFrom();
    if (to) {
      flight = wrap.animate([{ transform: 'none' }, { transform: to }], {
        duration: anim.ms,
        delay: wait,
        easing: EASE_IN_OUT,
        fill: 'forwards',
      });
    }
    finish = setTimeout(() => {
      // kula doleciała – kulka pojawia się w tej samej klatce, bez przenikania
      box.style.transition = 'none';
      root.dataset.mode = 'orb';
      delete root.dataset.anim;
      void box.offsetWidth;
      box.style.transition = '';
      flight?.cancel();
      flight = null;
      cancelUI();
      bigOrb.setActive(false);
    }, wait + anim.ms);
  }

  function setOrb(x, y, size) {
    root.style.setProperty('--orb-x', `${x}px`);
    root.style.setProperty('--orb-y', `${y}px`);
    root.style.setProperty('--orb-size', `${size}px`);
  }

  /** Transform, który stawia dużą kulę dokładnie na małej (środek i rozmiar kuli). */
  function flightFrom() {
    if (!wrap || !wrap.clientWidth) return null;
    const rect = wrap.getBoundingClientRect();
    const style = getComputedStyle(root);
    const x = parseFloat(style.getPropertyValue('--orb-x'));
    const y = parseFloat(style.getPropertyValue('--orb-y'));
    const size = parseFloat(style.getPropertyValue('--orb-size'));
    if (![x, y, size].every(Number.isFinite)) return null;
    const scale = size / Math.min(wrap.clientWidth, wrap.clientHeight); // kula = ¼ krótszego boku w obu
    const dx = x - (rect.left + rect.width / 2);
    const dy = y - (rect.top + rect.height / 2);
    return `translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px) scale(${scale.toFixed(4)})`;
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

/** Świecąca krawędź koła, które otwiera (zamyka) okno – przykrywa ostrą, pikselową krawędź regionu. */
function createRing() {
  const canvas = document.createElement('canvas');
  canvas.className = 'desk-reveal';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.append(canvas);
  const ctx = canvas.getContext('2d');
  let raf = 0;

  /** Krawędź koła z animacji Pythona; `delay` – ms od teraz do startu (ujemne: zaczyna „w biegu”). */
  function play({ cx, cy, r0, r1, ms, ease }, delay) {
    cancelAnimationFrame(raf);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = window.innerWidth;
    const height = window.innerHeight;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const curve = ease === 'in_out' ? easeInOut : easeOut;
    const opening = r1 > r0;
    const start = performance.now() + delay;
    canvas.hidden = false;

    const frame = (now) => {
      const t = clamp((now - start) / ms, 0, 1);
      const r = r0 + (r1 - r0) * curve(t) - 2;
      // przy otwieraniu gaśnie pod koniec (brzeg ucieka za rogi okna), przy zamykaniu – tuż przed kulką
      const strength = opening ? 1 - Math.pow(t, 3) : Math.sin(Math.PI * Math.min(1, t * 1.08)) ** 0.6;
      ctx.clearRect(0, 0, width, height);
      if (r > 1 && strength > 0.01) drawRing(ctx, cx, cy, r, strength);
      if (t < 1) raf = requestAnimationFrame(frame);
      else {
        ctx.clearRect(0, 0, width, height);
        canvas.hidden = true;
      }
    };
    raf = requestAnimationFrame(frame);
  }

  canvas.hidden = true;
  return { play };
}

function drawRing(ctx, cx, cy, r, strength) {
  const inner = Math.max(0, r - RING_WIDTH);
  const glow = ctx.createRadialGradient(cx, cy, inner, cx, cy, r);
  glow.addColorStop(0, 'rgba(56, 232, 255, 0)');
  glow.addColorStop(0.7, `rgba(56, 232, 255, ${(0.22 * strength).toFixed(3)})`);
  glow.addColorStop(0.94, `rgba(125, 241, 255, ${(0.7 * strength).toFixed(3)})`);
  glow.addColorStop(1, `rgba(225, 252, 255, ${(0.95 * strength).toFixed(3)})`);
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, TAU);
  ctx.arc(cx, cy, inner, 0, TAU, true);
  ctx.fill();
}

function easeOut(t) {
  return 1 - Math.pow(1 - t, 3);
}

function easeInOut(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}
