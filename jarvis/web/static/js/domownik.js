// Zakładka „Kalendarz”: aplikacja Domownik (obowiązki, zakupy, grafik) osadzona w ramce z jej serwera.
// Domownik sam odświeża się na żywo – także po zmianach zrobionych głosem przez Jarvisa – więc ramki
// nie przeładowujemy przy każdym wejściu; wczytujemy ją od nowa tylko po zmianie adresu lub awarii serwera.

import { $, h, appendChildren, clear } from './dom.js';

const START_PAGE = '/kalendarz';
const RETRY_MS = 5000;

export function initDomownik({ api, socket, navigate }) {
  const frame = $('#dom-frame');
  const offline = $('#dom-offline');
  const text = $('#dom-offline-text');
  let visible = false;
  let checking = false;
  let loadedUrl = ''; // adres serwera, z którego wczytano ramkę
  let timer = 0;

  $('#dom-retry').addEventListener('click', check);
  $('#dom-settings').addEventListener('click', () => navigate('settings'));
  socket.on('settings.changed', () => {
    if (visible) check(); // mógł się zmienić adres Domownika
  });

  return {
    onShow() {
      visible = true;
      check();
    },
    onHide() {
      visible = false;
      clearTimeout(timer);
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
    if (url !== loadedUrl) {
      frame.src = `${url}${START_PAGE}`;
      loadedUrl = url;
    }
    offline.hidden = true;
    frame.hidden = false;
  }

  function showOffline({ url, error }) {
    // w ramce zostałaby strona błędu przeglądarki – po powrocie serwera wczytamy ją od nowa
    if (loadedUrl) frame.src = 'about:blank';
    loadedUrl = '';
    frame.hidden = true;
    appendChildren(clear(text), [
      'Uruchom serwer Domownika (start-serwer.bat) albo popraw jego adres w ustawieniach. ',
      'Sprawdzam ponownie co kilka sekund.',
      url || error ? h('br') : null,
      url ? h('code', null, url) : null,
      url && error ? ' — ' : null,
      error,
    ]);
    offline.hidden = false;
    if (visible) timer = setTimeout(check, RETRY_MS);
  }
}
