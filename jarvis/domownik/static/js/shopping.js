/* Zakładka "Zakupy": jedna wspólna lista, pogrupowana działami sklepu. */

(() => {
  'use strict';
  const { api, esc, toast } = Domownik;

  // działy przychodzą z serwera w kolejności "jak się idzie przez sklep"
  const CATEGORIES = JSON.parse(document.getElementById('shopCategories').textContent);

  const el = {
    form: document.getElementById('shopForm'),
    title: document.getElementById('shopTitle'),
    qty: document.getElementById('shopQty'),
    groups: document.getElementById('shopGroups'),
    empty: document.getElementById('shopEmpty'),
    counter: document.getElementById('shopCounter'),
    clear: document.getElementById('clearDone'),
  };

  let items = [];

  const FROM = 'ąćęłńóśźż';
  const TO = 'acelnoszz';
  /** Nazwa bez polskich znaków i wielkości liter — do wyłapywania duplikatów. */
  const fold = (text) =>
    String(text).toLowerCase().replace(/[ąćęłńóśźż]/g, (c) => TO[FROM.indexOf(c)]);

  // ------------------------------------------------------------- rysowanie --

  const options = (selected) =>
    Object.entries(CATEGORIES)
      .map(([key, cat]) =>
        `<option value="${key}"${key === selected ? ' selected' : ''}>${cat.icon} ${esc(cat.label)}</option>`)
      .join('');

  function row(item) {
    const li = document.createElement('li');
    li.className = `shop-item${item.done ? ' is-done' : ''}`;
    li.style.setProperty('--task-color', item.color);
    li.innerHTML = `
      <button type="button" class="shop-item__check" aria-pressed="${item.done}"
              aria-label="${item.done ? 'Cofnij' : 'Kupione'}">${Domownik.icon('check')}</button>
      <button type="button" class="shop-item__body">
        <span class="shop-item__title">${esc(item.title)}</span>
        ${item.qty ? `<span class="shop-item__qty">${esc(item.qty)}</span>` : ''}
      </button>
      <span class="shop-cat" title="Dział: ${esc(item.category_label)}">
        <span class="shop-cat__icon" aria-hidden="true">${esc(item.icon)}</span>
        <select class="shop-cat__select" aria-label="Dział">${options(item.category)}</select>
      </span>
      <button type="button" class="shop-item__del" aria-label="Usuń z listy">✕</button>`;

    li.querySelector('.shop-item__check').addEventListener('click', () => toggle(item));
    li.querySelector('.shop-item__body').addEventListener('click', () => toggle(item));
    li.querySelector('.shop-cat__select').addEventListener('change', (ev) =>
      change(item, { category: ev.target.value }));
    li.querySelector('.shop-item__del').addEventListener('click', () => remove(item));
    return li;
  }

  function group(head, color, list, extra = '') {
    const box = document.createElement('section');
    box.className = `shop-group ${extra}`.trim();
    box.style.setProperty('--task-color', color);
    const title = document.createElement('h3');
    title.className = 'shop-group__head';
    title.innerHTML = `${head} <span class="shop-group__n">${list.length}</span>`;
    const ul = document.createElement('ul');
    ul.className = 'shop-list';
    ul.replaceChildren(...list.map(row));
    box.append(title, ul);
    return box;
  }

  function render() {
    const left = items.filter((i) => !i.done);
    const bought = items.filter((i) => i.done);

    const blocks = [];
    for (const [key, cat] of Object.entries(CATEGORIES)) {
      const inGroup = left.filter((i) => i.category === key);
      if (inGroup.length) blocks.push(group(`${cat.icon} ${esc(cat.label)}`, cat.color, inGroup));
    }
    if (bought.length) blocks.push(group('Kupione', 'var(--ok)', bought, 'shop-group--bought'));

    el.groups.replaceChildren(...blocks);
    el.empty.hidden = items.length > 0;
    el.counter.textContent = items.length ? `${bought.length} / ${items.length}` : '';
    el.clear.hidden = bought.length === 0;
  }

  // ------------------------------------------------------------- działania --

  async function load() {
    try {
      const data = await api('/api/zakupy');
      items = data.items;
      render();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function change(item, patch) {
    Object.assign(item, patch);   // od razu na ekranie, bez czekania na serwer
    const cat = patch.category && CATEGORIES[patch.category];
    if (cat) {
      item.color = cat.color;
      item.icon = cat.icon;
      item.category_label = cat.label;
    }
    render();
    try {
      await api(`/api/zakupy/${item.id}`, { method: 'PUT', body: patch });
    } catch (err) {
      toast(err.message, 'error');
      load();
    }
  }

  const toggle = (item) => change(item, { done: !item.done });

  async function remove(item) {
    items = items.filter((i) => i.id !== item.id);
    render();
    try {
      await api(`/api/zakupy/${item.id}`, { method: 'DELETE' });
    } catch (err) {
      toast(err.message, 'error');
      load();
    }
  }

  el.form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const title = el.title.value.trim();
    if (!title) return;

    const already = items.find((i) => !i.done && fold(i.title) === fold(title));
    if (already) {
      toast(`„${already.title}” już jest na liście.`);
      el.title.select();
      return;
    }

    try {
      await api('/api/zakupy', { method: 'POST', body: { title, qty: el.qty.value.trim() } });
      el.form.reset();
      el.title.focus();   // kolejna rzecz leci od razu, bez sięgania po mysz
      await load();
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  el.clear.addEventListener('click', async () => {
    const bought = items.filter((i) => i.done).length;
    if (!bought || !confirm(`Usunąć z listy ${bought} kupionych rzeczy?`)) return;
    try {
      const res = await api('/api/zakupy/wyczysc', { method: 'POST' });
      toast(`Sprzątnięte: ${res.usuniete}.`);
      load();
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  document.addEventListener('domownik:changed', load);

  // na telefonie nie wywalamy klawiatury od razu po wejściu na zakładkę
  if (window.matchMedia('(min-width: 760px)').matches) el.title.focus();

  load();
})();
