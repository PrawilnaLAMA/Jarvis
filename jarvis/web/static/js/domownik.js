// Zakładka „Dom”: Domownik (obowiązki, kalendarz, zakupy, grafik) w ramce z wbudowanego serwera Jarvisa.
// Domownik sam odświeża się na żywo – także po zmianach zrobionych głosem przez Jarvisa – więc ramki
// nie przeładowujemy przy każdym wejściu; wczytujemy ją od nowa tylko po zmianie adresu, awarii serwera
// albo gdy Jarvis otwiera konkretną podstronę („pokaż listę zakupów”).

import { $, h, appendChildren, clear } from './dom.js';

const START_PAGE = '/';
const RETRY_MS = 5000;

export function initDomownik({ api, socket, navigate }) {
  const frame = $('#dom-frame');
  const offline = $('#dom-offline');
  const text = $('#dom-offline-text');
  let visible = false;
  let checking = false;
  let loadedUrl = ''; // adres serwera, z którego wczytano ramkę
  let pendingPath = ''; // podstrona do otwarcia przy najbliższym pokazaniu ramki
  let timer = 0;

  $('#dom-retry').addEventListener('click', check);
  $('#dom-settings').addEventListener('click', () => navigate('settings'));
  const recheck = () => {
    if (visible) check(); // mógł się zmienić port albo serwer właśnie wstał
  };
  socket.on('settings.changed', recheck);
  socket.on('domownik.status', recheck);

  return {
    onShow() {
      visible = true;
      check();
    },
    onHide() {
      visible = false;
      clearTimeout(timer);
    },
    open(path) {
      pendingPath = path;
    },
  };

  async function check() {
    clearTimeout(timer);
    if (checking) return;
    checking = true;
    let status;
    try {
      status = await api.domownikStatus();
    } catch (err) {
      status = { ok: false, url: '', error: err.message };
    } finally {
      checking = false;
    }
    if (status && status.ok) showFrame(status.url);
    else showOffline(status || {});
  }

  function showFrame(url) {
    if (url !== loadedUrl || pendingPath) {
      frame.src = `${url}${pendingPath || START_PAGE}`;
      loadedUrl = url;
      pendingPath = '';
    }
    offline.hidden = true;
    frame.hidden = false;
  }

  function showOffline({ url, error, serve }) {
    // w ramce zostałaby strona błędu przeglądarki – po powrocie serwera wczytamy ją od nowa
    if (loadedUrl) frame.src = 'about:blank';
    loadedUrl = '';
    frame.hidden = true;
    const hint = serve
      ? 'Wbudowany serwer Domownika nie działa. '
      : 'Domownik działa na innym komputerze – sprawdź, czy jest włączony, albo popraw adres w ustawieniach. ';
    appendChildren(clear(text), [
      hint,
      'Sprawdzam ponownie co kilka sekund.',
      url || error ? h('br') : null,
      url && !serve ? h('code', null, url) : null,
      url && !serve && error ? ' — ' : null,
      error,
    ]);
    offline.hidden = false;
    if (visible) timer = setTimeout(check, RETRY_MS);
  }
}
