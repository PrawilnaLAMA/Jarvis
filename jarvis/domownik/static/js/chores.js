/* Zakładka "Obowiązki": lista definicji, filtry, eksport/import JSON. */

(() => {
  'use strict';
  const { api, esc, icon, toast, openChore } = Domownik;

  const el = {
    list: document.getElementById('choreList'),
    empty: document.getElementById('choresEmpty'),
    counter: document.getElementById('choresCounter'),
    search: document.getElementById('choreSearch'),
    filter: document.getElementById('categoryFilter'),
    personFilter: document.getElementById('personFilter'),
    importBtn: document.getElementById('importBtn'),
    importInput: document.getElementById('importInput'),
  };

  let chores = [];
  const filters = { text: '', category: '', person: '' };

  const WEEKDAY_MS = 86400000;

  function nextLabel(iso) {
    if (!iso) return 'już nie wypada';
    const today = new Date(Domownik.todayISO());
    const diff = Math.round((new Date(iso) - today) / WEEKDAY_MS);
    if (diff === 0) return 'dziś';
    if (diff === 1) return 'jutro';
    if (diff < 7) return `za ${diff} dni`;
    return new Date(iso).toLocaleDateString('pl-PL', { day: 'numeric', month: 'long' });
  }

  function row(chore) {
    const li = document.createElement('li');
    li.className = `chore-row${chore.archived ? ' is-archived' : ''}`;
    li.style.setProperty('--task-color', chore.color);
    const person = chore.assignees_label
      ? `<span class="task__person" style="--person:${chore.color}">${chore.na_zmiane ? icon('repeat') : ''}${esc(chore.assignees_label)}</span>` : '';
    li.innerHTML = `
      <span class="chore-row__icon">${esc(chore.icon)}</span>
      <span class="chore-row__body">
        <span class="chore-row__title">${esc(chore.title)}</span>
        <span class="chore-row__meta">
          ${person}
          <span>${esc(chore.category_label)}</span>
          <span>${icon('repeat')} ${esc(chore.repeat_label)}</span>
          <span>${icon('calendar')} następny raz: ${esc(nextLabel(chore.next_date))}</span>
          <span>${icon('check')} ${chore.done_count}×</span>
          ${chore.archived ? `<span>${icon('pause')} wstrzymany</span>` : ''}
        </span>
      </span>
      <span class="chore-row__actions">
        <button type="button" class="btn btn--ghost btn--icon" data-edit title="Edytuj" aria-label="Edytuj">${icon('edit')}</button>
      </span>`;
    li.querySelector('[data-edit]').addEventListener('click', () => openChore(chore.id));
    return li;
  }

  function render() {
    const text = filters.text.trim().toLowerCase();
    const visible = chores.filter((c) =>
      (!filters.category || c.category === filters.category) &&
      (!filters.person || (c.assignees || []).includes(filters.person)) &&
      (!text || c.title.toLowerCase().includes(text) || (c.notes || '').toLowerCase().includes(text)));

    el.list.replaceChildren(...visible.map(row));
    el.empty.hidden = visible.length > 0;
    el.counter.textContent = visible.length === chores.length
      ? `${chores.length} szt.`
      : `${visible.length} z ${chores.length}`;
  }

  async function load() {
    try {
      const data = await api('/api/obowiazki');
      chores = data.chores;
      render();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  el.search.addEventListener('input', () => { filters.text = el.search.value; render(); });

  el.filter.addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-cat]');
    if (!btn) return;
    filters.category = btn.dataset.cat;
    el.filter.querySelectorAll('.chip--btn').forEach((b) => b.classList.toggle('is-active', b === btn));
    render();
  });

  el.personFilter.addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-person]');
    if (!btn) return;
    filters.person = btn.dataset.person;
    el.personFilter.querySelectorAll('.chip--btn').forEach((b) => b.classList.toggle('is-active', b === btn));
    render();
  });

  el.importBtn.addEventListener('click', () => el.importInput.click());

  el.importInput.addEventListener('change', async () => {
    const file = el.importInput.files?.[0];
    if (!file) return;
    if (!confirm(`Wczytać „${file.name}”? Obecne dane zostaną podmienione (kopia zapasowa zostanie zapisana obok pliku danych).`)) {
      el.importInput.value = '';
      return;
    }
    const form = new FormData();
    form.append('plik', file);
    try {
      const res = await api('/api/import', { method: 'POST', form });
      toast(`Wczytano ${res.chores} obowiązków.`);
      load();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      el.importInput.value = '';
    }
  });

  document.addEventListener('domownik:changed', load);
  load();
})();
