// Minutnik w kuli Jarvisa (services/timers.py). Serwer przysyła całą listę (`timers`) po każdej zmianie,
// a strona odlicza dalej sama od „ile zostało”. Kula pokazuje najbliższy minutnik: cyfry Oxanium w
// przyciemnionym środku, a postęp na cewkach reaktora i sekundnik na skali (Orb.setTimer). To samo, tylko
// same cyfry, pokazuje kulka na pulpicie.
//
// Nastawianie co do sekundy odbywa się w samej kuli: godziny, minuty i sekundy zmienia kółko myszy,
// przeciąganie w górę lub w dół, strzałki albo wpisane cyfry. Przyciski (pauza, +1 min, anuluj, start)
// są w rzędzie pod kulą, w miejscu sterowania głosem.

import { $, $$, h, setIconHref } from './dom.js';
import { Clock, formatClock } from './clock.js';

const RING_MS = 60000; // tyle kula błyska po końcu czasu, jeśli nikt nie kliknie „OK”
const DEFAULT_SECONDS = 300;
const MAX_SECONDS = 24 * 3600 - 1;
const LAST_KEY = 'jarvis.timer.last';
const DRAG_STEP_PX = 16;
const WHEEL_MIN = 30; // mniejsze ruchy touchpada się sumują
const UNITS = [
  { key: 'h', label: 'Godziny', max: 23, forms: ['godzina', 'godziny', 'godzin'] },
  { key: 'm', label: 'Minuty', max: 59, forms: ['minuta', 'minuty', 'minut'] },
  { key: 's', label: 'Sekundy', max: 59, forms: ['sekunda', 'sekundy', 'sekund'] },
];

export function initTimer({ socket, api, onEscape }) {
  const face = {
    root: $('#orb-face'),
    label: $('#face-label'),
    name: $('#face-name'),
    clock: new Clock($('#face-clock')),
    edit: $('#face-edit'),
    status: $('#face-status'),
    more: $('#face-more'),
  };
  const controls = $('#controls');
  const editControls = $('#timer-edit-controls');
  const timerBtn = $('#btn-timer');
  const actions = $('#timer-actions');
  const pauseBtn = $('#timer-pause');
  const pauseUse = pauseBtn.querySelector('use');
  const addBtn = $('#timer-add');
  const cancelBtn = $('#timer-cancel');

  const minis = []; // kulka na pulpicie: {root, clock}
  let timers = []; // z serwera, z końcem na zegarze strony (endAt)
  let ringing = null; // {id, label, total, until}
  let focusId = null; // który minutnik pokazuje kula, gdy jest ich kilka
  let editor = null;
  let mode = '';
  let raf = 0;
  let flash = 0;

  // --- dane z serwera ---

  socket.on('hello', (data) => apply(data.timers));
  socket.on('timers', (data) => apply(data.timers));
  socket.on('timer.ring', (data) => {
    ringing = { ...data, until: performance.now() + RING_MS };
    focusId = null;
    kick();
  });

  function apply(list) {
    const now = performance.now();
    timers = (Array.isArray(list) ? list : []).map((t) => ({
      ...t,
      endAt: t.paused ? null : now + Number(t.remaining) * 1000,
    }));
    if (!timers.some((t) => t.id === focusId)) focusId = null;
    kick();
  }

  /** Co pokazuje kula: dzwoniący minutnik, wybrany albo najbliższy (serwer sortuje po końcu). */
  function current(now) {
    if (ringing && now > ringing.until) ringing = null;
    if (ringing) return { ...ringing, remaining: 0, paused: false, ringing: true };
    const t = timers.find((x) => x.id === focusId) || timers[0];
    if (!t) return null;
    const remaining = t.paused ? Number(t.remaining) : Math.max(0, (t.endAt - now) / 1000);
    return { ...t, remaining, ringing: false };
  }

  // --- rysowanie ---

  /** Stan dla kuli (orb.js): postęp 0..1 (ile zostało), sekundy od startu, pauza, dzwonienie, nastawianie. */
  function orbState(now) {
    if (editor) return { progress: 1, elapsed: null, paused: false, ringing: false, editing: true };
    const t = current(now);
    if (!t) return null;
    const progress = t.ringing || !(t.total > 0) ? 0 : Math.min(1, t.remaining / t.total);
    const elapsed = t.ringing ? null : Math.max(0, t.total - t.remaining);
    return { progress, elapsed, paused: t.paused, ringing: t.ringing, editing: false };
  }

  function kick() {
    if (!raf) raf = requestAnimationFrame(frame);
  }

  function frame(now) {
    raf = 0;
    const t = current(now);
    render(t);
    if (t || editor) raf = requestAnimationFrame(frame);
  }

  function render(t) {
    const next = editor ? 'edit' : t ? (t.ringing ? 'ring' : t.paused ? 'paused' : 'run') : '';
    if (next !== mode) setMode(next);
    if (!t || editor) return;

    const text = formatClock(t.remaining);
    face.clock.set(text, -1);
    // dwukropek przygasa w drugiej połowie każdej sekundy – zegar „tyka”
    const tick = !t.paused && !t.ringing && t.remaining % 1 < 0.5 && t.remaining > 0;
    face.clock.el.toggleAttribute('data-tick', tick);
    for (const mini of minis) {
      mini.clock.set(text, -1);
      mini.clock.el.toggleAttribute('data-tick', tick);
    }

    const label = t.label ? capitalize(t.label) : 'Minutnik';
    setText(face.label, label);
    if (!flash) setText(face.status, t.ringing ? 'Czas minął' : t.paused ? 'Wstrzymany' : '');
    const others = t.ringing ? 0 : timers.filter((x) => x.id !== t.id).length;
    face.more.hidden = !others;
    setText(face.more, others ? `+${others} ${plural(others, ['minutnik', 'minutniki', 'minutników'])}` : '');
    face.clock.el.setAttribute('aria-label', `${label}: ${text}`);
  }

  function setMode(next) {
    mode = next;
    face.root.hidden = !next;
    face.root.dataset.mode = next;
    for (const mini of minis) {
      mini.root.hidden = !next || next === 'edit';
      mini.root.dataset.mode = next;
    }
    const editing = next === 'edit';
    face.name.hidden = !editing;
    face.label.hidden = editing;
    face.clock.el.hidden = editing;
    face.edit.hidden = !editing;
    controls.hidden = editing;
    editControls.hidden = !editing;

    actions.hidden = !next || editing;
    timerBtn.classList.toggle('is-active', Boolean(next) && !editing);
    timerBtn.title = next && !editing ? 'Nowy minutnik' : 'Nastaw minutnik';
    cancelBtn.hidden = next === 'ring';
    const ring = next === 'ring';
    setIconHref(pauseUse, ring ? 'check' : next === 'paused' ? 'play' : 'pause');
    pauseBtn.setAttribute('aria-label', ring ? 'OK, wyłącz' : next === 'paused' ? 'Wznów minutnik' : 'Wstrzymaj minutnik');
    pauseBtn.title = pauseBtn.getAttribute('aria-label');
    addBtn.title = ring ? 'Jeszcze minuta' : 'Dodaj minutę';
    if (editing) face.more.hidden = true;
  }

  // kilka minutników – „+1 minutnik” pokazuje następny
  face.more.addEventListener('click', () => {
    const shown = current(performance.now());
    const i = timers.findIndex((t) => t.id === shown?.id);
    if (timers.length > 1) focusId = timers[(i + 1) % timers.length].id;
    kick();
  });

  // --- przyciski pod kulą ---

  timerBtn.addEventListener('click', () => (editor ? closeEditor() : openEditor()));

  pauseBtn.addEventListener('click', () => {
    const t = current(performance.now());
    if (!t) return;
    if (t.ringing) return dismiss();
    act(t.id, t.paused ? 'resume' : 'pause');
  });

  addBtn.addEventListener('click', () => {
    const t = current(performance.now());
    if (!t) return;
    if (t.ringing) {
      // „jeszcze minuta” – ten sam podpis, nowa minuta
      dismiss();
      call(api.timerStart(60, t.label || ''));
      return;
    }
    act(t.id, 'add', 60);
  });

  cancelBtn.addEventListener('click', () => {
    const t = current(performance.now());
    if (t && !t.ringing) act(t.id, 'cancel');
  });

  function act(id, action, seconds) {
    focusId = action === 'cancel' ? null : id; // kula zostaje przy minutniku, którym ktoś właśnie steruje
    call(api.timerAction(id, action, seconds));
  }

  function call(promise) {
    promise.then((data) => data && apply(data.timers)).catch((err) => showError(err.message));
  }

  function dismiss() {
    ringing = null;
    kick();
    render(current(performance.now()));
  }

  function showError(message) {
    clearTimeout(flash);
    face.status.textContent = message;
    face.status.classList.add('is-error');
    flash = setTimeout(() => {
      flash = 0;
      face.status.classList.remove('is-error');
      face.status.textContent = '';
      kick();
    }, 4000);
  }

  // Esc: najpierw zamyka nastawianie, potem wyłącza dzwoniący minutnik
  onEscape(() => {
    if (editor) {
      closeEditor();
      return true;
    }
    if (ringing) {
      dismiss();
      return true;
    }
    return false;
  });

  // --- nastawianie w kuli ---

  const spins = UNITS.map((unit, index) => {
    const el = h('span', {
      class: 'spin',
      role: 'spinbutton',
      tabindex: '0',
      'aria-label': unit.label,
      'aria-valuemin': '0',
      'aria-valuemax': String(unit.max),
      dataset: { unit: unit.key },
    });
    const clock = new Clock(el);
    bindSpin(el, index);
    return { el, clock, unit };
  });
  face.edit.replaceChildren(
    spins[0].el,
    h('span', { class: 'clock-cell is-sep', 'aria-hidden': 'true' }, h('span', { class: 'clock-glyph' }, ':')),
    spins[1].el,
    h('span', { class: 'clock-cell is-sep', 'aria-hidden': 'true' }, h('span', { class: 'clock-glyph' }, ':')),
    spins[2].el,
  );

  for (const btn of $$('[data-add]', editControls)) {
    btn.addEventListener('click', () => addToEditor(Number(btn.dataset.add)));
  }
  $('#timer-edit-cancel').addEventListener('click', closeEditor);
  $('#timer-start').addEventListener('click', startFromEditor);
  face.name.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      startFromEditor();
    }
  });

  function openEditor() {
    editor = { total: readLast(), typing: null };
    face.name.value = '';
    showEditor(0);
    setMode('edit');
    kick();
    spins[editor.total >= 3600 ? 0 : 1].el.focus({ preventScroll: true });
  }

  function closeEditor() {
    if (!editor) return;
    const hadFocus = face.root.contains(document.activeElement) || editControls.contains(document.activeElement);
    editor = null;
    setMode('');
    kick();
    render(current(performance.now()));
    if (hadFocus) timerBtn.focus({ preventScroll: true });
  }

  function startFromEditor() {
    if (!editor) return;
    const total = editor.total;
    if (total < 1) {
      face.edit.animate(
        [{ transform: 'none' }, { transform: 'translateX(-0.06em)' }, { transform: 'translateX(0.06em)' }, { transform: 'none' }],
        { duration: 260, iterations: 2 },
      );
      return;
    }
    const label = face.name.value.trim();
    try {
      localStorage.setItem(LAST_KEY, String(total));
    } catch {
      // bez pamięci przeglądarki następnym razem po prostu 5 minut
    }
    closeEditor();
    call(api.timerStart(total, label));
  }

  /** Wartość w kuli – `direction` przewija zmienione cyfry (1 w górę, -1 w dół, 0 bez animacji). */
  function showEditor(direction) {
    const parts = split(editor.total);
    spins.forEach(({ el, clock, unit }) => {
      const value = parts[unit.key];
      clock.set(unit.key === 'h' ? String(value) : String(value).padStart(2, '0'), direction);
      el.setAttribute('aria-valuenow', String(value));
      el.setAttribute('aria-valuetext', `${value} ${plural(value, unit.forms)}`);
      el.classList.toggle('is-zero', unit.key === 'h' && value === 0);
    });
    face.edit.style.setProperty('--em', (editorWidth(parts) + 0.12).toFixed(3));
    if (!flash) setText(face.status, 'Przewiń, przeciągnij lub wpisz');
  }

  function setUnit(index, value, direction) {
    const parts = split(editor.total);
    const unit = UNITS[index];
    parts[unit.key] = ((value % (unit.max + 1)) + unit.max + 1) % (unit.max + 1);
    editor.total = parts.h * 3600 + parts.m * 60 + parts.s;
    showEditor(direction);
  }

  function step(index, delta) {
    if (!editor) return;
    editor.typing = null;
    setUnit(index, split(editor.total)[UNITS[index].key] + delta, Math.sign(delta));
  }

  function addToEditor(seconds) {
    if (!editor) return;
    editor.typing = null;
    editor.total = Math.min(MAX_SECONDS, editor.total + seconds);
    showEditor(1);
  }

  /** Cyfra wpisana w pole: pierwsza zastępuje wartość, druga dopisuje się i przechodzi do następnego pola. */
  function typeDigit(index, digit) {
    const unit = UNITS[index];
    const typing = editor.typing && editor.typing.index === index ? editor.typing : null;
    let value = typing ? typing.value * 10 + digit : digit;
    if (value > unit.max) value = digit;
    const old = split(editor.total)[unit.key];
    setUnit(index, value, value >= old ? 1 : -1);
    const done = value * 10 > unit.max || (typing && typing.count >= 1);
    editor.typing = done ? null : { index, value, count: typing ? typing.count + 1 : 1 };
    if (done && index < spins.length - 1) spins[index + 1].el.focus({ preventScroll: true });
  }

  function bindSpin(el, index) {
    el.addEventListener('focus', () => {
      if (editor) editor.typing = null;
    });
    el.addEventListener('keydown', (event) => {
      if (!editor) return;
      const unit = UNITS[index];
      const handled = {
        ArrowUp: () => step(index, 1),
        ArrowDown: () => step(index, -1),
        PageUp: () => step(index, 10),
        PageDown: () => step(index, -10),
        Home: () => setUnit(index, 0, -1),
        End: () => setUnit(index, unit.max, 1),
        ArrowLeft: () => spins[Math.max(0, index - 1)].el.focus(),
        ArrowRight: () => spins[Math.min(spins.length - 1, index + 1)].el.focus(),
        Backspace: () => setUnit(index, Math.floor(split(editor.total)[unit.key] / 10), -1),
        Enter: startFromEditor,
      }[event.key];
      if (handled) {
        event.preventDefault();
        handled();
      } else if (/^\d$/.test(event.key)) {
        event.preventDefault();
        typeDigit(index, Number(event.key));
      }
    });

    let wheel = 0;
    el.addEventListener(
      'wheel',
      (event) => {
        event.preventDefault();
        wheel += event.deltaY;
        if (Math.abs(wheel) < WHEEL_MIN) return;
        step(index, wheel < 0 ? 1 : -1);
        wheel = 0;
      },
      { passive: false },
    );

    // przeciąganie w górę dodaje, w dół odejmuje – palcem na ekranie dotykowym też
    let drag = null;
    el.addEventListener('pointerdown', (event) => {
      if (!editor || event.button !== 0) return;
      drag = { y: event.clientY, steps: 0 };
      el.setPointerCapture(event.pointerId);
      el.classList.add('is-dragging');
    });
    el.addEventListener('pointermove', (event) => {
      if (!drag) return;
      const steps = Math.trunc((drag.y - event.clientY) / DRAG_STEP_PX);
      if (steps !== drag.steps) {
        step(index, steps - drag.steps);
        drag.steps = steps;
      }
    });
    const end = () => {
      if (!drag) return;
      drag = null;
      el.classList.remove('is-dragging');
      el.focus({ preventScroll: true });
    };
    el.addEventListener('pointerup', end);
    el.addEventListener('pointercancel', end);
  }

  return {
    /** Podłącza kulę (dużą albo kulkę na pulpicie) i – opcjonalnie – jej cyfry. */
    attach(orb, root) {
      orb.setTimer(orbState);
      if (root) {
        const mini = { root, clock: new Clock($('.clock', root)) };
        minis.push(mini);
        mode = null; // przerysuj z nową kulką
        kick();
      }
    },
  };
}

function readLast() {
  try {
    const value = Number(localStorage.getItem(LAST_KEY));
    if (Number.isFinite(value) && value >= 1 && value <= MAX_SECONDS) return Math.round(value);
  } catch {
    // prywatne okno – domyślnie
  }
  return DEFAULT_SECONDS;
}

function split(total) {
  return { h: Math.floor(total / 3600), m: Math.floor((total % 3600) / 60), s: total % 60 };
}

function editorWidth(parts) {
  // godziny 1–2 cyfry, minuty i sekundy po 2, dwa dwukropki (jak w clock.js)
  return (String(parts.h).length + 4) * 0.62 + 2 * 0.3;
}

function plural(n, [one, few, many]) {
  if (n === 1) return one;
  return n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? few : many;
}

function setText(el, text) {
  if (el.textContent !== text) el.textContent = text;
}

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
