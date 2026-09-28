// Start aplikacji: połączenie WebSocket, wspólny stan, przełączanie widoków i pasek statusu.

import { JarvisSocket } from './ws.js';
import { api } from './api.js';
import { createStore, assistantState } from './store.js';
import { $, $$ } from './dom.js';
import { STATE_LABELS } from './i18n.js';
import { Orb } from './orb.js';
import { initSubtitles } from './subtitles.js';
import { initControls } from './controls.js';
import { initChat } from './chat.js';
import { initDomownik } from './domownik.js';
import { initSettings } from './settings.js';
import { initDesktop } from './desktop.js';

const VIEWS = ['jarvis', 'dom', 'settings'];

const store = createStore({
  connected: false,
  serverState: 'offline',
  status: null,
  view: 'jarvis',
});
const socket = new JarvisSocket(socketUrl());

// Esc: zamyka najpierw panele, potem przerywa mówienie – pierwszy handler, który zwróci true, wygrywa.
const escapeHandlers = [];
const onEscape = (handler) => escapeHandlers.push(handler);

const ctx = { store, socket, api, onEscape, navigate };

// --- zdarzenia serwera wpływające na wspólny stan ---

socket.on('socket:open', () => store.set({ connected: true }));
socket.on('socket:close', () => store.set({ connected: false }));
socket.on('hello', (data) => {
  const patch = { serverState: data.state || 'idle' };
  if (data.status) patch.status = data.status;
  store.set(patch);
  if (!data.status) refreshStatus();
});
socket.on('state', (data) => {
  if (data.state) store.set({ serverState: data.state });
});
socket.on('status', (data) => {
  const patch = { status: data };
  if (data.state) patch.serverState = data.state;
  store.set(patch);
});
socket.on('ui.navigate', (data) => {
  if (data.path) views[data.view]?.open?.(data.path); // podstrona Domownika, np. /zakupy
  navigate(data.view);
});

// --- komponenty ---

const orb = new Orb($('#orb'));
socket.on('audio.level', (data) => orb.setLevel(data.source, data.level));

initSubtitles(ctx);
initChat(ctx);

const views = {
  jarvis: {
    onShow: () => orb.setActive(true),
    onHide: () => orb.setActive(false),
  },
  dom: initDomownik(ctx),
  settings: initSettings({
    ...ctx,
    onDirtyChange: (dirty) => {
      $('#nav-settings-dot').hidden = !dirty;
    },
  }),
};

initControls(ctx); // na końcu – Esc najpierw zamyka panele, dopiero potem przerywa mówienie
initDesktop({
  ...ctx,
  // pod zwiniętą kulką duża kula stoi (ostatnia klatka zostaje – rozwinięcie ją tylko odsłania)
  onModeChange: (mode) => orb.setActive(mode === 'full' && store.get().view === 'jarvis'),
});

store.subscribe(render);
render(store.get());

// --- widoki (routing przez #hash, żeby odświeżenie strony zostawiało ten sam widok) ---

window.addEventListener('hashchange', () => showView(viewFromHash()));

function viewFromHash() {
  const name = window.location.hash.replace(/^#\/?/, '');
  return VIEWS.includes(name) ? name : 'jarvis';
}

function navigate(view) {
  if (!VIEWS.includes(view)) return;
  if (window.location.hash !== `#${view}`) window.location.hash = view;
  else showView(view);
}

function showView(view) {
  const previous = store.get().view;
  for (const section of $$('.view')) section.hidden = section.dataset.view !== view;
  for (const link of $$('.nav-link')) {
    if (link.dataset.view === view) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  if (previous !== view && views[previous]) views[previous].onHide();
  store.set({ view });
  views[view].onShow();
}

// --- pasek statusu i banery ---

function render(s) {
  const state = assistantState(s);
  document.body.dataset.state = state;

  $('#conn').classList.toggle('is-online', s.connected);
  $('#conn-main').textContent = s.connected ? 'Połączono' : 'Łączenie…';
  $('#conn-sep').hidden = !s.connected;
  $('#conn-state').textContent = s.connected ? STATE_LABELS[state] || state : '';
  $('#conn').title = s.connected ? `Połączono · ${STATE_LABELS[state] || state}` : 'Łączenie z Jarvisem…';

  orb.setState(state);

  const llmMissing = s.connected && s.status != null && s.status.llm_configured === false;
  $('#setup-banner').hidden = !llmMissing;
}

async function refreshStatus() {
  try {
    const status = await api.status();
    if (status) store.set({ status });
  } catch (err) {
    console.warn('Nie udało się pobrać statusu:', err.message);
  }
}

function socketUrl() {
  const url = new URL('ws', window.location.href);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.search = '';
  url.hash = '';
  return url.href;
}

// --- globalne skróty i wznawianie połączenia ---

$('#setup-banner-btn').addEventListener('click', () => {
  navigate('settings');
  views.settings.focusSecret('GROQ_API_KEY');
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || event.defaultPrevented) return;
  for (const handler of escapeHandlers) {
    if (handler()) {
      event.preventDefault();
      return;
    }
  }
});

window.addEventListener('online', () => socket.reconnectNow());
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) socket.reconnectNow();
});

showView(viewFromHash());
socket.connect();
