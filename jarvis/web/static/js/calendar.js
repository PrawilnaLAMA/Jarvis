// Widok kalendarza: siatka miesiąca (od poniedziałku) i panel wybranego dnia
// z listą wydarzeń, edycją, usuwaniem (z potwierdzeniem w miejscu) i dodawaniem.

import { $, h, icon, clear, findFocusable, onMediaChange, preserveFocus } from './dom.js';
import { MONTHS, capitalize, plural } from './i18n.js';
import {
  addDays, compareOccurrences, describeDays, expandOccurrences, formatLongDate,
  gridStart, parseISODate, toISODate, weekdayIndex,
} from './dates.js';
import { createEventForm } from './calendar-form.js';

const WIDE = window.matchMedia('(min-width: 1100px)');
const COMPACT = window.matchMedia('(max-height: 600px), (max-width: 640px)');
const TYPE_HUES = new Map([
  ['spotkanie', 190], ['praca', 212], ['nauka', 262], ['wizyta', 168],
  ['sport', 135], ['uroczystość', 42], ['przypomnienie', 24],
]);

export function initCalendar({ socket, api, onEscape }) {
  const view = $('#view-calendar');
  const titleEl = $('#cal-title');
  const grid = $('#cal-grid');
  const statusEl = $('#cal-status');
  const panel = $('#day-panel');
  const scrim = $('#day-scrim');

  const now = new Date();
  let year = now.getFullYear();
  let month = now.getMonth();
  let todayISO = toISODate(now);
  let selected = todayISO;
  let byDate = new Map(); // RRRR-MM-DD → wystąpienia
  let visible = false;
  let stale = true;
  let loadSeq = 0;
  let useFallback = false; // backend bez /occurrences → rozwijamy wydarzenia sami
  let reloadTimer = 0;

  let panelOpen = false; // szuflada na wąskich ekranach
  let mode = 'list'; // 'list' | 'form'
  let form = null;
  let editing = null;
  let confirmId = null;
  let deleteError = '';
  let busyDelete = false;
  let flash = null; // { text, kind } – krótki komunikat w panelu
  let flashTimer = 0;
  let suppressClick = false;

  $('#cal-prev').addEventListener('click', () => shiftMonth(-1));
  $('#cal-next').addEventListener('click', () => shiftMonth(1));
  $('#cal-today').addEventListener('click', goToday);
  grid.addEventListener('click', onGridClick);
  scrim.addEventListener('click', closePanel);
  setupSwipe(grid, (direction) => shiftMonth(direction));

  view.addEventListener('keydown', (e) => {
    if (e.target.closest && e.target.closest('.day-panel')) return;
    if (e.key === 'PageUp') {
      e.preventDefault();
      shiftMonth(-1);
    } else if (e.key === 'PageDown') {
      e.preventDefault();
      shiftMonth(1);
    }
  });

  socket.on('calendar.changed', () => {
    stale = true;
    if (visible) scheduleReload();
  });

  onMediaChange(WIDE, () => {
    if (WIDE.matches) setPanelOpen(false);
  });
  onMediaChange(COMPACT, renderGrid);

  onEscape(() => {
    if (!visible) return false;
    if (confirmId) {
      cancelDelete();
      return true;
    }
    if (mode === 'form') {
      backToList();
      return true;
    }
    if (panelOpen) {
      closePanel();
      return true;
    }
    return false;
  });

  renderGrid();
  renderPanel();

  return {
    onShow() {
      visible = true;
      const today = toISODate(new Date());
      if (today !== todayISO) {
        todayISO = today;
        renderGrid();
      }
      if (stale) load();
    },
    onHide() {
      visible = false;
    },
  };

  // --- dane ---

  function scheduleReload() {
    clearTimeout(reloadTimer);
    reloadTimer = setTimeout(load, 150);
  }

  async function load() {
    const seq = ++loadSeq;
    stale = false;
    const first = gridStart(year, month);
    const startISO = toISODate(first);
    const endISO = toISODate(addDays(first, 41));
    const slow = setTimeout(() => {
      if (seq === loadSeq) setStatus('Wczytywanie wydarzeń…');
    }, 300);
    try {
      const list = await fetchOccurrences(startISO, endISO);
      if (seq !== loadSeq) return;
      byDate = groupByDate(list, startISO, endISO);
      setStatus(null);
    } catch (err) {
      if (seq !== loadSeq) return;
      stale = true;
      setStatus(`Nie udało się wczytać wydarzeń: ${err.message}`, true);
    } finally {
      clearTimeout(slow);
    }
    renderGrid();
    if (mode === 'list') renderPanel();
  }

  async function fetchOccurrences(startISO, endISO) {
    if (!useFallback) {
      try {
        const res = await api.occurrences(startISO, endISO);
        return (res && Array.isArray(res.occurrences) && res.occurrences) || [];
      } catch (err) {
        if (err.status !== 404 && err.status !== 405) throw err;
        useFallback = true;
      }
    }
    const res = await api.events();
    return expandOccurrences((res && res.events) || [], startISO, endISO);
  }

  function groupByDate(list, startISO, endISO) {
    const map = new Map();
    for (const occ of list) {
      const day = occ && occ.occurrence_date;
      if (!day || day < startISO || day > endISO) continue;
      if (!map.has(day)) map.set(day, []);
      map.get(day).push(occ);
    }
    for (const items of map.values()) items.sort(compareOccurrences);
    return map;
  }

  function setStatus(text, retry = false) {
    clear(statusEl);
    statusEl.hidden = !text;
    if (!text) return;
    statusEl.classList.toggle('is-error', retry);
    statusEl.append(h('span', null, text));
    if (retry) statusEl.append(h('button', { type: 'button', class: 'btn btn-small', onClick: load }, icon('refresh'), 'Spróbuj ponownie'));
  }

  // --- nawigacja ---

  function shiftMonth(delta) {
    const d = new Date(year, month + delta, 1);
    showMonth(d.getFullYear(), d.getMonth());
  }

  function showMonth(y, m) {
    year = y;
    month = m;
    renderGrid();
    load();
  }

  function goToday() {
    const today = new Date();
    todayISO = toISODate(today);
    openDay(todayISO, false);
    showMonth(today.getFullYear(), today.getMonth());
  }

  function onGridClick(e) {
    if (suppressClick) return;
    const cell = e.target.closest('.day');
    if (cell) openDay(cell.dataset.date, true);
  }

  function openDay(iso, openDrawer) {
    selected = iso;
    mode = 'list';
    form = null;
    editing = null;
    confirmId = null;
    deleteError = '';
    setFlash(null);
    for (const cell of grid.querySelectorAll('.day')) cell.classList.toggle('is-selected', cell.dataset.date === iso);
    renderPanel();
    if (openDrawer && !WIDE.matches) {
      setPanelOpen(true);
      focusIn('close');
    }
  }

  function setPanelOpen(value) {
    panelOpen = Boolean(value) && !WIDE.matches;
    panel.classList.toggle('open', panelOpen);
    scrim.hidden = !panelOpen;
  }

  function closePanel() {
    if (mode === 'form') backToList();
    setPanelOpen(false);
    const cell = findFocusable(grid, `day:${selected}`);
    if (cell) cell.focus();
  }

  // --- siatka ---

  function renderGrid() {
    titleEl.textContent = `${MONTHS[month]} ${year}`;
    const first = gridStart(year, month);
    const limit = COMPACT.matches ? 2 : 3;
    const cells = [];
    for (let i = 0; i < 42; i++) {
      const d = addDays(first, i);
      const iso = toISODate(d);
      const items = byDate.get(iso) || [];
      const classes = ['day'];
      if (d.getMonth() !== month) classes.push('is-other');
      if (iso === todayISO) classes.push('is-today');
      if (iso === selected) classes.push('is-selected');
      if (weekdayIndex(d) >= 5) classes.push('is-weekend');
      // gdy wszystkie się nie mieszczą, „+N” zajmuje ostatni wiersz (w trybie kompaktowym jest w rogu)
      const shown = COMPACT.matches ? Math.min(items.length, limit) : items.length > limit ? limit - 1 : items.length;
      const count = items.length ? `, ${items.length} ${plural(items.length, 'wydarzenie', 'wydarzenia', 'wydarzeń')}` : '';
      cells.push(
        h(
          'button',
          {
            type: 'button',
            class: classes.join(' '),
            dataset: { date: iso, focus: `day:${iso}` },
            'aria-label': `${formatLongDate(d)}${count}`,
            'aria-current': iso === todayISO ? 'date' : null,
          },
          h('span', { class: 'day-num', 'aria-hidden': 'true' }, String(d.getDate())),
          h(
            'span',
            { class: 'day-events', 'aria-hidden': 'true' },
            items.slice(0, shown).map(chip),
            items.length > shown ? h('span', { class: 'more' }, `+${items.length - shown}`) : null,
          ),
        ),
      );
    }
    preserveFocus(grid, () => clear(grid).append(...cells));
  }

  function chip(occ) {
    const el = h(
      'span',
      { class: `chip${isRecurring(occ) ? ' is-recurring' : ''}` },
      occ.start ? h('span', { class: 'chip-time' }, occ.start) : null,
      h('span', { class: 'chip-text' }, occ.desc || occ.type || '(bez opisu)'),
    );
    el.style.setProperty('--hue', String(hueFor(occ.type)));
    return el;
  }

  // --- panel dnia ---

  function renderPanel() {
    const date = parseISODate(selected) || new Date();
    const head = h(
      'header',
      { class: 'panel-head' },
      h('h2', { class: 'panel-title' }, capitalize(formatLongDate(date))),
      h('button', { type: 'button', class: 'icon-btn panel-close', 'aria-label': 'Zamknij panel dnia', dataset: { focus: 'close' }, onClick: closePanel }, icon('close')),
    );
    const body = h('div', { class: 'panel-body' });
    if (mode === 'form' && form) body.append(form.el);
    else body.append(...listView());
    preserveFocus(panel, () => clear(panel).append(head, body), 'add');
  }

  function focusIn(key) {
    const el = findFocusable(panel, key);
    if (el) el.focus();
  }

  function listView() {
    const items = byDate.get(selected) || [];
    const parts = [];
    if (flash) parts.push(h('p', { class: `panel-flash is-${flash.kind}`, role: 'status' }, icon(flash.kind === 'ok' ? 'check' : 'info'), flash.text));
    if (items.length) parts.push(h('ul', { class: 'occ-list' }, items.map(occItem)));
    else parts.push(h('p', { class: 'panel-empty' }, 'Brak wydarzeń tego dnia.'));
    parts.push(h('button', { type: 'button', class: 'btn btn-primary btn-block', dataset: { focus: 'add' }, onClick: startAdd }, icon('plus'), 'Dodaj wydarzenie'));
    return parts;
  }

  function occItem(occ) {
    const recurring = isRecurring(occ);
    const title = occ.desc || occ.type || '(bez opisu)';
    const typeTag = occ.type ? h('span', { class: 'occ-type' }, occ.type) : null;
    if (typeTag) typeTag.style.setProperty('--hue', String(hueFor(occ.type)));
    const li = h(
      'li',
      { class: 'occ' },
      h('div', { class: 'occ-bar', 'aria-hidden': 'true' }),
      h('div', { class: 'occ-time' }, timeRange(occ)),
      h(
        'div',
        { class: 'occ-main' },
        h('p', { class: 'occ-desc' }, title),
        typeTag || recurring
          ? h('p', { class: 'occ-meta' }, typeTag, recurring ? h('span', { class: 'occ-rec' }, icon('repeat'), describeDays(occ.days)) : null)
          : null,
      ),
      h(
        'div',
        { class: 'occ-actions' },
        h('button', { type: 'button', class: 'icon-btn', 'aria-label': `Edytuj: ${title}`, title: 'Edytuj', dataset: { focus: `edit:${occ.id}` }, onClick: () => startEdit(occ) }, icon('edit')),
        h('button', { type: 'button', class: 'icon-btn icon-btn-danger', 'aria-label': `Usuń: ${title}`, title: 'Usuń', dataset: { focus: `del:${occ.id}` }, onClick: () => askDelete(occ) }, icon('trash')),
      ),
    );
    li.querySelector('.occ-bar').style.setProperty('--hue', String(hueFor(occ.type)));
    if (confirmId === occ.id) li.append(confirmBox(occ, title, recurring));
    return li;
  }

  function confirmBox(occ, title, recurring) {
    const question = recurring
      ? `Usunąć „${title}” ze wszystkich dni (${describeDays(occ.days)})?`
      : `Usunąć „${title}”?`;
    return h(
      'div',
      { class: 'occ-confirm', role: 'group', 'aria-label': 'Potwierdzenie usunięcia' },
      h('p', { class: 'occ-confirm-text' }, question),
      deleteError ? h('p', { class: 'form-error', role: 'alert' }, deleteError) : null,
      h(
        'div',
        { class: 'form-actions' },
        h('button', { type: 'button', class: 'btn btn-ghost', dataset: { focus: `cancel:${occ.id}` }, onClick: cancelDelete, 'aria-disabled': busyDelete ? 'true' : null }, 'Anuluj'),
        h('button', { type: 'button', class: 'btn btn-danger', dataset: { focus: `confirm:${occ.id}` }, onClick: () => doDelete(occ), 'aria-disabled': busyDelete ? 'true' : null }, icon('trash'), busyDelete ? 'Usuwanie…' : 'Usuń'),
      ),
    );
  }

  function askDelete(occ) {
    confirmId = occ.id;
    deleteError = '';
    renderPanel();
    focusIn(`cancel:${occ.id}`);
  }

  function cancelDelete() {
    if (busyDelete) return;
    const id = confirmId;
    confirmId = null;
    deleteError = '';
    renderPanel();
    if (id) focusIn(`del:${id}`);
  }

  async function doDelete(occ) {
    if (busyDelete) return;
    busyDelete = true;
    renderPanel();
    try {
      await api.deleteEvent(occ.id);
      confirmId = null;
      setFlash({ kind: 'ok', text: 'Usunięto wydarzenie.' });
    } catch (err) {
      if (err.status === 404) {
        confirmId = null;
        setFlash({ kind: 'info', text: 'To wydarzenie zostało już usunięte.' });
      } else {
        deleteError = err.message;
      }
    } finally {
      busyDelete = false;
    }
    renderPanel();
    load();
  }

  function startAdd() {
    openForm(null);
  }

  function startEdit(occ) {
    openForm(occ);
  }

  function openForm(event) {
    editing = event;
    confirmId = null;
    setFlash(null);
    mode = 'form';
    form = createEventForm({ event, date: selected, onSubmit: submitForm, onCancel: backToList });
    renderPanel();
    form.focus();
  }

  function backToList() {
    mode = 'list';
    form = null;
    editing = null;
    renderPanel();
    focusIn('add');
  }

  async function submitForm(data) {
    const wasEdit = Boolean(editing);
    if (wasEdit) await api.updateEvent(editing.id, data);
    else await api.createEvent(data);
    // przejdź do dnia jednorazowego wydarzenia, jeśli jest inny niż wybrany
    if (data.date && data.date !== selected) {
      selected = data.date;
      const d = parseISODate(data.date);
      if (d && (d.getFullYear() !== year || d.getMonth() !== month)) {
        year = d.getFullYear();
        month = d.getMonth();
      }
    }
    mode = 'list';
    form = null;
    editing = null;
    setFlash({ kind: 'ok', text: wasEdit ? 'Zapisano zmiany.' : 'Dodano wydarzenie.' });
    renderGrid();
    renderPanel();
    focusIn('add');
    await load();
  }

  function setFlash(value) {
    flash = value;
    clearTimeout(flashTimer);
    if (value) {
      flashTimer = setTimeout(() => {
        flash = null;
        if (mode === 'list' && !confirmId) renderPanel();
      }, 4000);
    }
  }

  // Przesunięcie palcem w poziomie zmienia miesiąc (ekrany dotykowe).
  function setupSwipe(el, onSwipe) {
    let startX = null;
    let startY = 0;
    let startTime = 0;
    let pointerId = null;
    el.addEventListener('pointerdown', (e) => {
      if (e.pointerType === 'mouse') return;
      startX = e.clientX;
      startY = e.clientY;
      startTime = Date.now();
      pointerId = e.pointerId;
    });
    el.addEventListener('pointerup', (e) => {
      if (startX === null || e.pointerId !== pointerId) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      startX = null;
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5 && Date.now() - startTime < 700) {
        suppressClick = true;
        setTimeout(() => {
          suppressClick = false;
        }, 350);
        onSwipe(dx < 0 ? 1 : -1);
      }
    });
    el.addEventListener('pointercancel', () => {
      startX = null;
    });
  }
}

function isRecurring(occ) {
  return Array.isArray(occ.days) && occ.days.length > 0 && !occ.date;
}

function timeRange(occ) {
  if (occ.start && occ.end) return `${occ.start}–${occ.end}`;
  if (occ.start) return occ.start;
  return 'Cały dzień';
}

function hueFor(type) {
  const key = String(type || '').trim().toLowerCase();
  if (TYPE_HUES.has(key)) return TYPE_HUES.get(key);
  if (!key) return 196;
  let hash = 0;
  for (const ch of key) hash = (hash * 31 + ch.codePointAt(0)) % 360;
  return hash;
}
