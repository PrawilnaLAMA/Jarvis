// Panel rozmowy: dziennik zdarzeń (polecenia, odpowiedzi, narzędzia, Discord, komunikaty) i pole do wpisywania poleceń. Na wąskich ekranach działa jako wysuwana szuflada.

import { $, h, icon, clear, onMediaChange } from './dom.js';
import { formatClock, formatLongDate, toISODate, addDays } from './dates.js';
import { capitalize } from './i18n.js';
import { assistantState } from './store.js';

const CHAT_TOPICS = ['transcript', 'reply', 'tool', 'discord.message', 'messenger.message', 'notice'];
const MAX_ITEMS = 300;
const MAX_DETAILS = 1500;
const NOTICE_ICONS = { info: 'info', warning: 'warning', error: 'error' };
const WIDE = window.matchMedia('(min-width: 1000px)');
const FINE_POINTER = window.matchMedia('(pointer: fine)');

export function initChat({ socket, store, onEscape }) {
  const panel = $('#chat');
  const log = $('#chat-log');
  const emptyEl = $('#chat-empty');
  const jumpBtn = $('#chat-jump');
  const thinkingEl = $('#chat-thinking');
  const form = $('#chat-form');
  const input = $('#chat-input');
  const errorEl = $('#chat-error');
  const toggleBtn = $('#btn-chat');
  const badge = $('#chat-badge');
  const scrim = $('#chat-scrim');
  const closeBtn = $('#chat-close');

  let stick = true; // przewijaj do dołu, dopóki użytkownik sam nie przewinie w górę
  let unread = 0;
  let open = false;
  let lastDay = null;
  const sent = []; // historia wysłanych poleceń (strzałki ↑/↓)
  let recall = -1;

  // --- zdarzenia z serwera ---

  socket.on('hello', (data) => {
    reset();
    for (const item of Array.isArray(data.history) ? data.history : []) {
      if (item && CHAT_TOPICS.includes(item.topic)) add(item.topic, item.data || {}, item.ts, true);
    }
    scrollToBottom();
  });

  for (const topic of CHAT_TOPICS) {
    socket.on(topic, (data, message) => add(topic, data, message && message.ts, false));
  }

  store.subscribe((s, prev) => {
    const thinking = assistantState(s) === 'thinking';
    if (thinkingEl.hidden === thinking) {
      thinkingEl.hidden = !thinking;
      if (thinking && stick) scrollToBottom();
    }
    if (s.view !== prev.view && s.view === 'jarvis') {
      requestAnimationFrame(() => {
        if (stick) scrollToBottom();
        if (isVisible()) markRead();
      });
    }
  });

  // --- wysyłanie poleceń ---

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    if (!socket.send({ type: 'command', text })) {
      showError('Brak połączenia z Jarvisem — polecenie nie zostało wysłane.');
      return;
    }
    if (sent[sent.length - 1] !== text) sent.push(text);
    if (sent.length > 50) sent.shift();
    recall = -1;
    input.value = '';
    hideError();
    scrollToBottom();
  });

  input.addEventListener('input', () => {
    recall = -1;
    hideError();
  });

  input.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowUp' && sent.length && (input.value === '' || recall !== -1)) {
      event.preventDefault();
      recall = recall === -1 ? sent.length - 1 : Math.max(0, recall - 1);
      input.value = sent[recall];
    } else if (event.key === 'ArrowDown' && recall !== -1) {
      event.preventDefault();
      recall += 1;
      if (recall >= sent.length) {
        recall = -1;
        input.value = '';
      } else {
        input.value = sent[recall];
      }
    }
  });

  // --- przewijanie ---

  log.addEventListener(
    'scroll',
    () => {
      stick = log.scrollHeight - log.scrollTop - log.clientHeight < 48;
      if (stick) jumpBtn.hidden = true;
    },
    { passive: true },
  );
  jumpBtn.addEventListener('click', scrollToBottom);
  if (typeof ResizeObserver === 'function') {
    new ResizeObserver(() => {
      if (stick) scrollToBottom();
    }).observe(log);
  }

  // --- szuflada na wąskich ekranach ---

  toggleBtn.addEventListener('click', () => setOpen(!open));
  closeBtn.addEventListener('click', () => setOpen(false));
  scrim.addEventListener('click', () => setOpen(false));
  onMediaChange(WIDE, () => {
    if (WIDE.matches) setOpen(false, false);
    if (isVisible()) markRead();
  });
  onEscape(() => {
    if (!open || store.get().view !== 'jarvis') return false;
    setOpen(false);
    return true;
  });

  function setOpen(value, moveFocus = true) {
    open = Boolean(value) && !WIDE.matches;
    panel.classList.toggle('open', open);
    scrim.hidden = !open;
    toggleBtn.setAttribute('aria-expanded', String(open));
    if (open) {
      markRead();
      if (stick) requestAnimationFrame(scrollToBottom);
      // na ekranach dotykowych nie wywołujemy klawiatury ekranowej bez potrzeby
      if (moveFocus) (FINE_POINTER.matches ? input : closeBtn).focus();
    } else if (moveFocus && panel.contains(document.activeElement)) {
      toggleBtn.focus();
    }
  }

  // --- renderowanie ---

  function reset() {
    clear(log);
    lastDay = null;
    stick = true;
    jumpBtn.hidden = true;
    emptyEl.hidden = false;
    markRead();
  }

  function add(topic, data, ts, replay) {
    const item = RENDERERS[topic](data || {}, ts, replay);
    if (!item) return;
    const day = dayKey(ts);
    if (day !== lastDay) {
      if (lastDay !== null || day !== toISODate(new Date())) log.append(daySeparator(ts));
      lastDay = day;
    }
    log.append(item);
    while (log.children.length > MAX_ITEMS) log.removeChild(log.firstElementChild);
    emptyEl.hidden = true;
    if (stick) scrollToBottom();
    else jumpBtn.hidden = false;
    if (!replay && !isVisible()) {
      unread += 1;
      renderBadge();
    }
  }

  function scrollToBottom() {
    log.scrollTop = log.scrollHeight;
    stick = true;
    jumpBtn.hidden = true;
  }

  function isVisible() {
    return store.get().view === 'jarvis' && (WIDE.matches || open);
  }

  function markRead() {
    unread = 0;
    renderBadge();
  }

  function renderBadge() {
    badge.hidden = unread === 0;
    badge.textContent = unread > 99 ? '99+' : String(unread);
    toggleBtn.setAttribute('aria-label', unread ? `Czat, nowe wiadomości: ${unread}` : 'Czat');
  }

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = false;
  }

  function hideError() {
    errorEl.hidden = true;
  }
}

// --- elementy dziennika ---

const RENDERERS = {
  transcript(data, ts) {
    const voice = data.source === 'voice';
    return h(
      'li',
      { class: 'msg msg-user' },
      h('div', { class: 'msg-meta' }, h('span', { class: `tag ${voice ? 'tag-voice' : ''}` }, voice ? 'głos' : 'tekst'), timeEl(ts)),
      h('p', { class: 'msg-text' }, str(data.text)),
    );
  },

  reply(data, ts) {
    return h(
      'li',
      { class: 'msg msg-jarvis' },
      h('div', { class: 'msg-meta' }, h('span', { class: 'msg-author' }, 'Jarvis'), timeEl(ts)),
      h('p', { class: 'msg-text' }, str(data.text)),
    );
  },

  tool(data, ts) {
    const head = [icon('wrench'), h('code', { class: 'tool-name' }, str(data.name) || 'narzędzie'), timeEl(ts)];
    const details = describeTool(data);
    if (!details) return h('li', { class: 'sys sys-tool' }, h('div', { class: 'sys-line' }, head));
    return h(
      'li',
      { class: 'sys sys-tool' },
      h('details', null, h('summary', { class: 'sys-line' }, head), h('pre', { class: 'tool-details' }, details)),
    );
  },

  'discord.message'(data, ts) {
    return incoming('discord', 'Discord', data, ts);
  },

  'messenger.message'(data, ts) {
    return incoming('messenger', 'Messenger', data, ts);
  },

  notice(data, ts) {
    const level = NOTICE_ICONS[data.level] ? data.level : 'info';
    return h(
      'li',
      { class: `sys notice notice-${level}` },
      h('div', { class: 'sys-line' }, icon(NOTICE_ICONS[level]), h('span', { class: 'notice-text' }, str(data.text)), timeEl(ts)),
    );
  },
};

/** Wiadomość od kontaktu z komunikatora (Discord, Messenger). */
function incoming(app, label, data, ts) {
  return h(
    'li',
    { class: `entry entry-${app}` },
    h(
      'div',
      { class: 'entry-head' },
      icon('message'),
      h('span', { class: 'entry-label' }, `${label} · `, h('strong', null, str(data.author) || 'nieznany')),
      timeEl(ts),
    ),
    h('p', { class: 'entry-text' }, str(data.content) || 'załącznik'),
  );
}

function str(value) {
  return value == null ? '' : String(value);
}

function timeEl(ts) {
  const valid = typeof ts === 'number' && Number.isFinite(ts);
  return h('time', { class: 'msg-time', datetime: valid ? new Date(ts * 1000).toISOString() : null }, formatClock(ts));
}

function dayKey(ts) {
  const valid = typeof ts === 'number' && Number.isFinite(ts);
  return toISODate(valid ? new Date(ts * 1000) : new Date());
}

function daySeparator(ts) {
  const day = dayKey(ts);
  const today = new Date();
  let label;
  if (day === toISODate(today)) label = 'Dziś';
  else if (day === toISODate(addDays(today, -1))) label = 'Wczoraj';
  else label = capitalize(formatLongDate(new Date(ts * 1000), false));
  return h('li', { class: 'day-sep', role: 'separator' }, h('span', null, label));
}

function describeTool(data) {
  const parts = [];
  const args = data.args;
  if (args && typeof args === 'object' && Object.keys(args).length) parts.push(`Argumenty: ${stringify(args)}`);
  else if (typeof args === 'string' && args.trim()) parts.push(`Argumenty: ${args}`);
  if (data.result != null && data.result !== '') parts.push(`Wynik: ${stringify(data.result)}`);
  const text = parts.join('\n');
  return text.length > MAX_DETAILS ? `${text.slice(0, MAX_DETAILS)}…` : text;
}

function stringify(value) {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
