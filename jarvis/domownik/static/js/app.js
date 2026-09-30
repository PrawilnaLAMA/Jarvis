/* Domownik — wspólna warstwa: API, modal obowiązku, toasty. */

const Domownik = (() => {
  'use strict';

  // ----------------------------------------------------------------- api --

  /* Podgląd innego dnia do testów: /?dzis=2026-12-24 — parametr doklejamy
     do każdego zapytania, żeby cała aplikacja widziała ten sam "dzisiaj". */
  const DAY_OVERRIDE = new URLSearchParams(location.search).get('dzis') || null;

  async function api(url, { method = 'GET', body, form } = {}) {
    if (DAY_OVERRIDE) {
      const parsed = new URL(url, location.origin);
      parsed.searchParams.set('dzis', DAY_OVERRIDE);
      url = parsed.pathname + parsed.search;
    }
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    if (form) opts.body = form;

    let res;
    try {
      res = await fetch(url, opts);
    } catch (err) {
      throw new Error('Brak połączenia z aplikacją. Czy serwer nadal działa?');
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Coś poszło nie tak (${res.status}).`);
    return data;
  }

  // -------------------------------------------------------------- pomoce --

  const esc = (value) =>
    String(value ?? '').replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

  const todayISO = () => {
    if (DAY_OVERRIDE) return DAY_OVERRIDE;
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };

  /** Ikona ze sprite'a w base.html (templates/_ikony.html) — nazwy tylko z kodu, nie od użytkownika. */
  const icon = (name) => `<svg class="icon" aria-hidden="true" focusable="false"><use href="#i-${name}"/></svg>`;

  /** '2026-09-14' → '14.09'. ISO rozbijamy ręcznie — new Date(iso) to północ UTC. */
  const dayShort = (iso) => {
    const parts = String(iso || '').split('-');
    return parts.length === 3 ? `${parts[2]}.${parts[1]}` : '';
  };

  function toast(message, kind = 'ok') {
    const box = document.getElementById('toasts');
    if (!box) return;
    const el = document.createElement('div');
    el.className = `toast ${kind === 'error' ? 'toast--error' : ''}`;
    el.innerHTML = `${icon(kind === 'error' ? 'warning' : 'check')}<span>${esc(message)}</span>`;
    box.appendChild(el);
    setTimeout(() => {
      el.classList.add('is-out');
      el.addEventListener('animationend', () => el.remove(), { once: true });
    }, kind === 'error' ? 5000 : 2600);
  }

  /** Informuje wszystkie widoki, że dane się zmieniły. */
  const notifyChanged = (detail = {}) =>
    document.dispatchEvent(new CustomEvent('domownik:changed', { detail }));

  // ---------------------------------------------------------- kafelek dnia --

  /** Kolumny osób z base.html: [{key, label, color}] – Leon | Wspólne | Natalia. */
  const lanes = (() => {
    try {
      return JSON.parse(document.getElementById('domLanes')?.textContent || '[]')
        .map(([key, lane]) => ({ key, ...lane }));
    } catch {
      return [];
    }
  })();

  /** Czyja kolumna: kto ma tego dnia turę, jedyna osoba, albo wspólne. */
  const laneOf = (item) => item.kto || (item.assignees?.length ? item.assignees[0] : 'wspolne');

  /** Kolor kolumny zadania – w podglądach (tydzień, kalendarz) kolor mówi „czyje”, nie „jaka kategoria”. */
  const laneColor = (item) => lanes.find((lane) => lane.key === laneOf(item))?.color || item.color;

  /** Polska odmiana: plural(5, 'dzień', 'dni', 'dni') → 'dni'. */
  function plural(n, one, few, many) {
    if (n === 1) return one;
    const tens = n % 100;
    return n % 10 >= 2 && n % 10 <= 4 && (tens < 12 || tens > 14) ? few : many;
  }

  /**
   * Buduje <li> pojedynczego obowiązku (dzień + odhaczanie + edycja).
   * `person: false` – bez imienia, gdy lista i tak jest pogrupowana po osobach (kolumny „Dziś”).
   */
  function taskElement(item, { lateBadge = false, person = true } = {}) {
    const li = document.createElement('li');
    li.className = `task${item.done ? ' is-done' : ''}`;
    li.style.setProperty('--task-color', item.color);
    li.dataset.id = item.id;
    li.dataset.date = item.date;
    li.tabIndex = 0;
    li.setAttribute('role', 'button');
    li.setAttribute('aria-pressed', String(item.done));

    const late = lateBadge && item.days_late
      ? `<span class="badge-late">${item.days_late} ${plural(item.days_late, 'dzień', 'dni', 'dni')} temu</span>` : '';
    const prio = item.priority === 'wysoki' ? '<span class="prio-high">ważne</span>' : '';
    const who = person && item.kto_label
      ? `<span class="task__person" style="--person:${item.color}">${esc(item.kto_label)}</span>` : '';
    const turn = item.na_zmiane ? `<span class="task__turn" title="${esc(item.assignees_label)}">${icon('repeat')} na zmianę</span>` : '';
    // obowiązek przesunięty przez planer — mówimy skąd i dlaczego
    const moved = item.przeniesiony_z
      ? `<span class="task__moved" title="${esc(item.powod || '')}">↷ z ${esc(dayShort(item.przeniesiony_z))}</span>` : '';
    const note = item.notes ? `<p class="task__note">${esc(item.notes)}</p>` : '';

    li.innerHTML = `
      <span class="task__check" aria-hidden="true">${icon('check')}</span>
      <span class="task__body">
        <span class="task__title"><span class="task__icon" aria-hidden="true">${esc(item.icon)}</span>${timeTag(item)}${esc(item.title)}</span>
        <span class="task__meta">
          ${who}${prio}${late}
          <span>${esc(item.repeat_label)}</span>
          ${turn}${moved}
        </span>
        ${note}
      </span>
      <button type="button" class="task__edit" title="Edytuj obowiązek" aria-label="Edytuj ${esc(item.title)}">${icon('edit')}</button>`;

    li.querySelector('.task__edit').addEventListener('click', (ev) => {
      ev.stopPropagation();
      openChore(item.id);
    });

    const toggle = () => toggleDone(li, item);
    li.addEventListener('click', toggle);
    li.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); toggle(); }
    });
    return li;
  }

  /** Odhacza (albo cofa) jedno wystąpienie obowiązku i odświeża widoki. */
  async function setDone(id, date, done) {
    const res = await api('/api/odhacz', { method: 'POST', body: { id, date, done } });
    notifyChanged({ reason: 'toggle', id, date, done, stats: res.stats });
    return res;
  }

  async function toggleDone(li, item) {
    const next = !li.classList.contains('is-done');
    li.classList.toggle('is-done', next);      // optymistycznie — bez czekania
    li.setAttribute('aria-pressed', String(next));
    try {
      await setDone(item.id, item.date, next);
      item.done = next;
    } catch (err) {
      li.classList.toggle('is-done', !next);
      li.setAttribute('aria-pressed', String(!next));
      toast(err.message, 'error');
    }
  }

  /** Godzina wpisu przed nazwą („15:00”) – pusto dla obowiązków bez godziny. */
  function timeTag(item) {
    return item.time ? `<time class="task__time">${esc(item.time)}</time>` : '';
  }

  /** Mały wpis obowiązku (kolejne dni) – kropka w kolorze osoby, której przypada. */
  function miniTask(item) {
    const el = document.createElement('div');
    el.className = `mini-task${item.done ? ' is-done' : ''}`;
    el.style.setProperty('--task-color', laneColor(item));
    el.title = item.kto_label ? `${item.title} – ${item.kto_label}` : `${item.title} – wspólne`;
    el.innerHTML = `<span class="mini-task__dot" aria-hidden="true"></span><span class="mini-task__title">${timeTag(item)}${esc(item.title)}</span>`;
    return el;
  }

  // --------------------------------------------------------------- modal --

  const modal = document.getElementById('choreModal');
  const form = document.getElementById('choreForm');
  const errorBox = document.getElementById('formError');
  const deleteBtn = document.getElementById('deleteChore');
  const titleEl = document.getElementById('modalTitle');
  let lastFocused = null;

  /* Uwaga: form.id / form.title zwracają atrybuty elementu <form>, a nie pola
     formularza — do pól trzeba wchodzić przez form.elements. */
  const fld = (name) => form.elements[name];

  function showRepeatDetails() {
    if (!form) return;
    const type = form.querySelector('input[name="repeat_type"]:checked')?.value || 'brak';
    form.querySelectorAll('.repeat-detail').forEach((box) => {
      box.hidden = box.dataset.repeat !== type;
    });
  }

  function resetForm() {
    form.reset();
    fld('id').value = '';
    fld('start_date').value = todayISO();
    form.querySelector('input[name="category"][value="inne"]').checked = true;
    setAssignees([]);
    form.querySelector('input[name="repeat_type"][value="brak"]').checked = true;
    form.querySelector('.more').open = false;
    errorBox.hidden = true;
    showRepeatDetails();
  }

  /* --- kto to robi: brak zaznaczeń = wspólne, dwie osoby = na zmianę --- */

  const assigneeBoxes = () => form.querySelectorAll('input[name="assignees"]');
  const wspolneBox = () => form.querySelector('input[name="wspolne"]');

  function setAssignees(list) {
    const wybrane = new Set(list || []);
    assigneeBoxes().forEach((box) => { box.checked = wybrane.has(box.value); });
    syncAssignees();
  }

  function syncAssignees() {
    const ile = [...assigneeBoxes()].filter((b) => b.checked).length;
    const wspolne = wspolneBox();
    if (wspolne) wspolne.checked = ile === 0;
    const hint = document.getElementById('assigneeHint');
    if (hint) hint.hidden = ile < 2;
  }

  if (form) {
    form.querySelectorAll('#assigneeChips input').forEach((box) => {
      box.addEventListener('change', () => {
        if (box.name === 'wspolne') {
          // "Wspólne" to po prostu brak osób — kliknięcie czyści resztę
          assigneeBoxes().forEach((other) => { other.checked = false; });
        }
        syncAssignees();
      });
    });
  }

  function fillForm(chore) {
    resetForm();
    fld('id').value = chore.id;
    fld('title').value = chore.title;
    fld('notes').value = chore.notes || '';
    fld('start_date').value = chore.start_date;
    fld('time').value = chore.time || '';
    fld('end_date').value = chore.end_date || '';
    fld('priority').value = chore.priority || 'normalny';
    fld('archived').checked = !!chore.archived;

    const cat = form.querySelector(`input[name="category"][value="${chore.category}"]`);
    if (cat) cat.checked = true;

    setAssignees(chore.assignees || (chore.assignee ? [chore.assignee] : []));

    const repeat = chore.repeat || { type: 'brak' };
    const type = form.querySelector(`input[name="repeat_type"][value="${repeat.type}"]`);
    if (type) type.checked = true;
    if (repeat.interval) fld('interval').value = repeat.interval;
    if (repeat.day_of_month) fld('day_of_month').value = repeat.day_of_month;
    form.querySelectorAll('input[name="weekdays"]').forEach((box) => {
      box.checked = (repeat.weekdays || []).includes(Number(box.value));
    });
    if (chore.notes || chore.end_date || chore.archived) form.querySelector('.more').open = true;
    showRepeatDetails();
  }

  function openModal() {
    lastFocused = document.activeElement;
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
    setTimeout(() => fld('title').focus(), 40);
  }

  function closeModal() {
    modal.hidden = true;
    document.body.style.overflow = '';
    if (lastFocused instanceof HTMLElement) lastFocused.focus();
  }

  /** Nowy obowiązek (opcjonalnie z datą startu z kalendarza). */
  function newChore(startDate) {
    resetForm();
    if (startDate) fld('start_date').value = startDate;
    titleEl.textContent = 'Nowy obowiązek';
    deleteBtn.hidden = true;
    openModal();
  }

  /** Edycja istniejącego obowiązku. */
  async function openChore(id) {
    try {
      const chore = await api(`/api/obowiazki/${id}`);
      fillForm(chore);
      titleEl.textContent = 'Edytuj obowiązek';
      deleteBtn.hidden = false;
      openModal();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  function readForm() {
    const fd = new FormData(form);
    const type = fd.get('repeat_type');
    const repeat = { type };
    if (type === 'co_x_dni') repeat.interval = Number(fd.get('interval') || 2);
    if (type === 'tygodniowo') repeat.weekdays = fd.getAll('weekdays').map(Number);
    if (type === 'miesiecznie') repeat.day_of_month = Number(fd.get('day_of_month') || 1);

    return {
      title: (fd.get('title') || '').trim(),
      category: fd.get('category') || 'inne',
      priority: fd.get('priority') || 'normalny',
      assignees: fd.getAll('assignees'),
      notes: fd.get('notes') || '',
      start_date: fd.get('start_date') || todayISO(),
      time: fd.get('time') || null,
      end_date: fd.get('end_date') || null,
      archived: fd.get('archived') === 'on',
      repeat,
    };
  }

  if (form) {
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const payload = readForm();
      const id = fld('id').value;

      if (!payload.title) {
        errorBox.textContent = 'Wpisz, co trzeba zrobić.';
        errorBox.hidden = false;
        fld('title').focus();
        return;
      }
      if (payload.repeat.type === 'tygodniowo' && !payload.repeat.weekdays.length) {
        errorBox.textContent = 'Zaznacz przynajmniej jeden dzień tygodnia.';
        errorBox.hidden = false;
        return;
      }

      const btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;
      try {
        await api(id ? `/api/obowiazki/${id}` : '/api/obowiazki', {
          method: id ? 'PUT' : 'POST',
          body: payload,
        });
        closeModal();
        toast(id ? 'Zapisane!' : 'Dodane do planu!');
        notifyChanged({ reason: 'save' });
      } catch (err) {
        errorBox.textContent = err.message;
        errorBox.hidden = false;
      } finally {
        btn.disabled = false;
      }
    });

    form.querySelectorAll('input[name="repeat_type"]').forEach((input) =>
      input.addEventListener('change', showRepeatDetails));

    deleteBtn.addEventListener('click', async () => {
      const id = fld('id').value;
      if (!id) return;
      if (!confirm(`Usunąć „${fld('title').value}” razem z historią odhaczeń?`)) return;
      try {
        await api(`/api/obowiazki/${id}`, { method: 'DELETE' });
        closeModal();
        toast('Usunięte.');
        notifyChanged({ reason: 'delete', id });
      } catch (err) {
        toast(err.message, 'error');
      }
    });

    modal.querySelectorAll('[data-close-modal]').forEach((el) =>
      el.addEventListener('click', closeModal));
  }

  document.addEventListener('click', (ev) => {
    if (ev.target.closest('[data-new-chore]')) newChore();
  });

  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && modal && !modal.hidden) closeModal();
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || '');
    if (ev.key.toLowerCase() === 'n' && !typing && !ev.ctrlKey && !ev.metaKey && modal?.hidden) {
      ev.preventDefault();
      newChore();
    }
  });

  // ------------------------------------------ zmiany z innych urządzeń --

  /* Dane leżą na wspólnym serwerze, więc ktoś inny może je zmienić ze swojego
     telefonu. Serwer sam odzywa się przez strumień /api/zmiany, więc zmianę widać
     od razu — bez czekania i bez klikania. Odpytywanie /api/wersja zostaje jako
     plan B: na wypadek zerwanego strumienia albo pośrednika, który tnie długie
     połączenia. */
  const POLL_MS = 20000;
  let lastStamp = null;
  let stream = null;

  /** Zderza świeży znacznik z ostatnio znanym i w razie różnicy odświeża widoki. */
  function sawStamp(stamp) {
    if (lastStamp !== null && stamp !== lastStamp) notifyChanged({ reason: 'remote' });
    lastStamp = stamp;
  }

  async function checkRemote() {
    if (document.hidden) return;   // karta w tle nie musi nic odpytywać
    try {
      const data = await api('/api/wersja');
      sawStamp(data.stamp);
    } catch (err) {
      /* brak sieci albo serwer chwilowo nie odpowiada — spróbujemy za chwilę,
         bez zasypywania ekranu komunikatami o błędach */
    }
  }

  /* Furtka dla narzędzi: ?bez-sync=1 nie otwiera strumienia. Bez tego przeglądarka
     w trybie headless czeka w nieskończoność na koniec wczytywania strony (strumień
     nigdy się nie kończy) i nie da się zrobić zrzutu ekranu. */
  const NO_SYNC = new URLSearchParams(location.search).has('bez-sync');

  function openStream() {
    if (NO_SYNC || !('EventSource' in window) || stream) return;
    stream = new EventSource('/api/zmiany');
    stream.onmessage = (ev) => sawStamp(ev.data);
    // przy zerwaniu EventSource wznawia się sam; do tego czasu pracuje plan B
    stream.onerror = () => {};
  }

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) return;
    // telefon po uśpieniu potrafi ubić strumień — sprawdzamy stan i wstajemy z nim na nowo
    checkRemote();
    if (!stream || stream.readyState === EventSource.CLOSED) {
      stream = null;
      openStream();
    }
  });

  setInterval(() => {
    if (!stream || stream.readyState !== EventSource.OPEN) checkRemote();
  }, POLL_MS);

  openStream();
  checkRemote();

  /* Service worker — dzięki niemu telefon pozwala „zainstalować" Domownika na
     ekranie głównym. Istnieje wyłącznie w bezpiecznym kontekście (HTTPS albo
     localhost), więc pod zwykłym http po prostu go tu nie ma i nic się nie dzieje. */
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      /* brak workera to nie powód, żeby cokolwiek psuć użytkownikowi */
    });
  }

  return {
    api, esc, icon, toast, taskElement, miniTask, newChore, openChore, notifyChanged, todayISO, dayShort,
    plural, setDone, lanes, laneOf, laneColor,
  };
})();
