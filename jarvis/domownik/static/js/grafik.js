/* Okno wczytywania grafiku pracy: plik → kolumna Natalii → zapis.

   Grafik ze sklepu ma w domu tylko Natalia, więc jej kolumnę rozpoznajemy po imieniu
   z nagłówka i zapisujemy od razu, bez pytania. Wybór ręczny zostaje wyłącznie na
   wypadek, gdy imienia w pliku nie ma — zgadywanie kolumny wpisałoby jej cudze godziny. */

const Grafik = (() => {
  'use strict';
  const { api, esc, toast, notifyChanged } = Domownik;

  // Jedyna osoba z grafikiem pracy — gdyby kiedyś doszła druga, to jest to miejsce.
  const OSOBA = 'natalia';

  const el = {
    modal: document.getElementById('grafikModal'),
    drop: document.getElementById('grafikDrop'),
    pick: document.getElementById('grafikPick'),
    file: document.getElementById('grafikFile'),
    error: document.getElementById('grafikError'),
    preview: document.getElementById('grafikPreview'),
    previewLead: document.getElementById('grafikPreviewLead'),
    people: document.getElementById('grafikPeople'),
    loaded: document.getElementById('grafikLoaded'),
  };

  if (!el.modal) return { open: () => {} };

  // mianownik, bo używamy ich po „na …": „na wrzesień 2026"
  const MIESIACE = ['styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec',
    'lipiec', 'sierpień', 'wrzesień', 'październik', 'listopad', 'grudzień'];

  let domownicy = null;      // {klucz: {label, initial, color}} z /api/slowniki
  let biezacy = null;        // {rok, miesiac} pokazywane w kalendarzu
  let podglad = null;        // ostatnio wczytany plik

  const nazwaMiesiaca = (iso) => {
    const [rok, mies] = String(iso).split('-');
    return `${MIESIACE[Number(mies) - 1] || iso} ${rok}`;
  };

  const etykieta = () => domownicy?.[OSOBA]?.label || 'Natalia';

  function blad(tekst) {
    el.error.textContent = tekst || '';
    el.error.hidden = !tekst;
  }

  // ------------------------------------------------------------- otwieranie --

  async function open(ctx) {
    biezacy = ctx || biezacy;
    podglad = null;
    blad('');
    el.preview.hidden = true;
    el.modal.hidden = false;
    document.body.style.overflow = 'hidden';
    if (!domownicy) {
      try {
        domownicy = (await api('/api/slowniki')).people;
      } catch { domownicy = {}; }
    }
    odswiezWczytane();
  }

  function close() {
    el.modal.hidden = true;
    document.body.style.overflow = '';
  }

  // -------------------------------------------------------- co już wczytane --

  async function odswiezWczytane() {
    if (!biezacy) return;
    let dane;
    try {
      dane = await api(`/api/grafik?rok=${biezacy.rok}&miesiac=${biezacy.miesiac}`);
    } catch (err) {
      el.loaded.replaceChildren();
      return;
    }
    const wczytane = Object.entries(dane.wczytany || {}).filter(([, jest]) => jest);
    if (!wczytane.length) {
      el.loaded.innerHTML = `<p class="hint">Na ${esc(nazwaMiesiaca(dane.miesiac))} nie ma jeszcze żadnego grafiku.</p>`;
      return;
    }
    el.loaded.innerHTML = `
      <p class="field__label">Wczytane na ${esc(nazwaMiesiaca(dane.miesiac))}</p>
      <ul class="grafik-people">
        ${wczytane.map(([osoba]) => `
          <li class="grafik-person">
            <span class="grafik-person__name">${esc(domownicy?.[osoba]?.label || osoba)}</span>
            <button type="button" class="btn btn--danger-ghost btn--sm" data-usun="${esc(osoba)}">Usuń</button>
          </li>`).join('')}
      </ul>`;
    el.loaded.querySelectorAll('[data-usun]').forEach((btn) => {
      btn.addEventListener('click', () => usun(btn.dataset.usun, dane.miesiac));
    });
  }

  async function usun(osoba, miesiac) {
    try {
      await api(`/api/grafik/${osoba}/${miesiac}`, { method: 'DELETE' });
      toast('Grafik usunięty.');
      notifyChanged({ reason: 'grafik' });
      odswiezWczytane();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  // ------------------------------------------------------------ wczytywanie --

  async function wczytaj(plik) {
    if (!plik) return;
    blad('');
    el.preview.hidden = true;
    el.drop.classList.add('is-busy');
    try {
      const form = new FormData();
      form.append('plik', plik, plik.name);
      podglad = await api('/api/grafik/wczytaj', { method: 'POST', form });
      // jedna kolumna z jej imieniem = pewna sprawa, zapisujemy bez pytania
      const nasze = podglad.osoby.filter((osoba) => osoba.domownik === OSOBA);
      if (nasze.length === 1 && await zapisz(nasze[0])) return;
      pokazPodglad();
    } catch (err) {
      blad(err.message);
    } finally {
      el.drop.classList.remove('is-busy');
    }
  }

  // Awaryjnie: w pliku nie ma kolumny z jej imieniem (albo jest kilka takich).
  // Wtedy pytamy, bo pomyłka wpisałaby Natalii godziny koleżanki.
  function pokazPodglad() {
    el.previewLead.textContent =
      `Grafik na ${nazwaMiesiaca(podglad.miesiac)}. Która kolumna to ${etykieta()}?`;
    el.people.replaceChildren(...podglad.osoby.map(wierszOsoby));
    el.preview.hidden = false;
  }

  function wierszOsoby(osoba) {
    const li = document.createElement('li');
    li.className = 'grafik-person';
    const opis = `${osoba.pracujace} dni pracy`
      + (osoba.wolne_z_kodem ? `, ${osoba.wolne_z_kodem} wolnych z grafiku` : '');
    li.innerHTML = `
      <span class="grafik-person__name">${esc(osoba.nazwa)}</span>
      <span class="grafik-person__info">${esc(opis)}</span>
      <span class="grafik-person__actions">
        <button type="button" class="btn btn--soft btn--sm" data-zapisz>
          To ${esc(etykieta())}
        </button>
      </span>`;
    li.querySelector('[data-zapisz]').addEventListener('click', () => zapisz(osoba));
    return li;
  }

  async function zapisz(kolumna) {
    try {
      const wynik = await api(`/api/grafik/${OSOBA}/${podglad.miesiac}`, {
        method: 'PUT',
        body: { dni: kolumna.dni, plik: podglad.plik },
      });
      toast(`Grafik na ${nazwaMiesiaca(podglad.miesiac)}: ${wynik.dni} dni.`);
      notifyChanged({ reason: 'grafik' });
      close();
      return true;
    } catch (err) {
      blad(err.message);
      return false;
    }
  }

  // ---------------------------------------------------------------- wejścia --

  el.pick.addEventListener('click', () => el.file.click());
  el.file.addEventListener('change', () => {
    wczytaj(el.file.files[0]);
    el.file.value = '';           // ten sam plik musi dać się wybrać drugi raz
  });

  ['dragenter', 'dragover'].forEach((zdarzenie) => {
    el.drop.addEventListener(zdarzenie, (ev) => {
      ev.preventDefault();
      el.drop.classList.add('is-over');
    });
  });
  ['dragleave', 'drop'].forEach((zdarzenie) => {
    el.drop.addEventListener(zdarzenie, () => el.drop.classList.remove('is-over'));
  });
  el.drop.addEventListener('drop', (ev) => {
    ev.preventDefault();
    wczytaj(ev.dataTransfer?.files?.[0]);
  });

  document.addEventListener('paste', (ev) => {
    if (el.modal.hidden) return;
    const plik = [...(ev.clipboardData?.files || [])][0];
    if (plik) { ev.preventDefault(); wczytaj(plik); }
  });

  el.modal.querySelectorAll('[data-close-grafik]').forEach((btn) => {
    btn.addEventListener('click', close);
  });
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && !el.modal.hidden) close();
  });

  return { open, close };
})();
