// Przyciski pod kulą: wyciszenie mikrofonu, „Mów” (jak słowo wywołania) i „Przerwij”.

import { $, setIconHref } from './dom.js';
import { assistantState, isMuted, voiceInfo } from './store.js';

export function initControls({ socket, store, onEscape }) {
  const micBtn = $('#btn-mic');
  const micIcon = micBtn.querySelector('use');
  const talkBtn = $('#btn-talk');
  const stopBtn = $('#btn-stop');

  micBtn.addEventListener('click', () => {
    const s = store.get();
    const muted = isMuted(s);
    if (!socket.send({ type: 'voice', action: muted ? 'unmute' : 'mute' })) return;
    // natychmiastowa informacja zwrotna – serwer i tak przyśle nowy status
    const status = s.status || {};
    store.set({ status: { ...status, voice: { ...(status.voice || {}), muted: !muted } } });
  });

  talkBtn.addEventListener('click', () => socket.send({ type: 'voice', action: 'listen' }));
  stopBtn.addEventListener('click', stopSpeaking);

  // Esc przerywa mówienie (o ile wcześniej nie zamknięto nim panelu)
  onEscape(() => {
    if (assistantState(store.get()) !== 'speaking') return false;
    stopSpeaking();
    return true;
  });

  store.subscribe(render);
  render(store.get());

  function stopSpeaking() {
    socket.send({ type: 'voice', action: 'stop' });
  }

  function render(s) {
    const state = assistantState(s);
    const voiceOk = s.connected && voiceInfo(s).available !== false;
    const muted = isMuted(s);

    micBtn.disabled = !voiceOk;
    micBtn.setAttribute('aria-pressed', String(muted));
    micBtn.title = muted ? 'Włącz mikrofon' : 'Wycisz mikrofon';
    setIconHref(micIcon, muted ? 'mic-off' : 'mic');

    talkBtn.disabled = !voiceOk;
    talkBtn.classList.toggle('is-active', state === 'listening' || state === 'follow_up');

    stopBtn.disabled = !(s.connected && state === 'speaking');
  }
}
