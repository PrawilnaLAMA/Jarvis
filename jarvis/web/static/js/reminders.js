// Przypomnienia z kalendarza: dopóki jakieś czeka nieodebrane, kula (i kulka na pulpicie) świeci na czerwono.
// Kliknięcie kuli odbiera wszystkie (POST /api/reminders/ack) – serwer rozsyła pustą listę i kolor wraca.

import { $ } from './dom.js';

export function initReminders({ socket, api }) {
  const wrap = $('#orb-wrap');
  const orbs = [];
  let pending = [];

  socket.on('hello', (data) => apply(data.reminders));
  socket.on('reminders', (data) => apply(data.pending));

  wrap.addEventListener('click', () => ack());

  function apply(list) {
    pending = Array.isArray(list) ? list : [];
    for (const orb of orbs) orb.setAlert(pending.length > 0);
    const text = pending.map((r) => r.text).join('\n');
    wrap.classList.toggle('has-reminder', pending.length > 0);
    if (text) wrap.title = `${text}\nKliknij, żeby odebrać.`;
    else wrap.removeAttribute('title');
  }

  /** Odbiera przypomnienia; bez oczekujących nic nie wysyła. */
  function ack() {
    if (!pending.length) return;
    apply([]); // od razu – serwer i tak potwierdzi zdarzeniem „reminders”
    api.remindersAck().catch(() => {});
  }

  return {
    attach(orb) {
      orbs.push(orb);
      orb.setAlert(pending.length > 0);
    },
    ack,
  };
}
