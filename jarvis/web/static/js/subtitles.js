// Napisy pod kulą: tekst mowy Jarvisa rozjaśniany słowo po słowie, ostatnie rozpoznane
// polecenie użytkownika oraz podpowiedź zależna od stanu asystenta.

import { $ } from './dom.js';
import { STATE_HINTS } from './i18n.js';
import { assistantState, voiceInfo } from './store.js';

const FADE_AFTER_MS = 2000;
const HEARD_VISIBLE_MS = 9000;

export function initSubtitles({ socket, store }) {
  const captions = $('#captions');
  const subtitle = $('#subtitle');
  const spokenEl = $('#subtitle-spoken');
  const pendingEl = $('#subtitle-pending');
  const caret = $('#subtitle-caret');
  const liveEl = $('#subtitle-live');
  const heard = $('#heard');
  const heardText = $('#heard-text');
  const hint = $('#hint');
  const hintSub = $('#hint-sub');

  let text = '';
  let progress = 0; // ile znaków już wypowiedziano
  let cursor = 0; // pozycja wyszukiwania słów, gdy brak char_end
  let active = false;
  let fadeTimer = 0;
  let heardTimer = 0;

  socket.on('tts.start', (data) => {
    text = String(data.text || '');
    progress = 0;
    cursor = 0;
    active = true;
    clearTimeout(fadeTimer);
    subtitle.classList.remove('is-interrupted');
    spokenEl.textContent = '';
    pendingEl.textContent = text;
    subtitle.scrollTop = 0;
    liveEl.textContent = text; // czytniki ekranu dostają całe zdanie jednorazowo
    setVisible(text.length > 0);
  });

  socket.on('tts.word', (data) => {
    if (!active) return;
    const end = typeof data.char_end === 'number' ? data.char_end : locateWord(data.text);
    setProgress(end);
  });

  socket.on('tts.end', (data) => {
    if (!active) return;
    active = false;
    if (data.interrupted) subtitle.classList.add('is-interrupted');
    else setProgress(text.length);
    clearTimeout(fadeTimer);
    fadeTimer = setTimeout(() => setVisible(false), FADE_AFTER_MS);
  });

  socket.on('transcript', (data) => {
    if (data.source === 'text') return; // wpisane polecenia widać w czacie
    const value = String(data.text || '').trim();
    if (!value) return;
    heardText.textContent = `„${value}”`;
    heard.classList.add('visible');
    clearTimeout(heardTimer);
    heardTimer = setTimeout(() => heard.classList.remove('visible'), HEARD_VISIBLE_MS);
  });

  socket.on('socket:close', () => {
    active = false;
    clearTimeout(fadeTimer);
    setVisible(false);
    heard.classList.remove('visible');
  });

  store.subscribe(renderHint);
  renderHint(store.get());

  function setVisible(visible) {
    subtitle.classList.toggle('visible', visible);
    captions.classList.toggle('has-subtitle', visible);
  }

  function setProgress(end) {
    const next = Math.max(progress, Math.min(text.length, Math.round(Number(end)) || 0));
    if (next === progress) return;
    progress = next;
    spokenEl.textContent = text.slice(0, progress);
    pendingEl.textContent = text.slice(progress);
    // bieżąca linia jako druga od góry – widać też kontekst poprzedniej
    const line = caret.offsetHeight || 24;
    subtitle.scrollTop = Math.max(0, caret.offsetTop - line);
  }

  // Zapas, gdy serwer nie przysyła char_end: szukamy słowa w tekście od ostatniej pozycji.
  function locateWord(word) {
    const w = String(word || '').trim();
    if (!w) return progress;
    let index = text.indexOf(w, cursor);
    if (index === -1) index = text.toLowerCase().indexOf(w.toLowerCase(), cursor);
    if (index === -1) return progress;
    cursor = index + w.length;
    return cursor;
  }

  function renderHint(s) {
    const state = assistantState(s);
    const voice = voiceInfo(s);
    let main = STATE_HINTS[state] || '';
    let sub = '';
    if (!s.connected) {
      main = 'Łączenie z Jarvisem…';
    } else if (voice.available === false && state !== 'thinking' && state !== 'speaking') {
      main = STATE_HINTS.offline;
      sub = voice.error ? String(voice.error) : '';
    } else if (state === 'idle' && voice.listening === false) {
      main = 'Nasłuch wyłączony — naciśnij „Mów” albo napisz na czacie.';
    }
    hint.textContent = main;
    hintSub.textContent = sub;
    hintSub.hidden = !sub;
  }
}
