// Kontrolki formularza ustawień. Każda zwraca { el, get(), set(value) } i opcjonalnie validate().
// Zmiany zgłaszają zdarzeniami 'input'/'change', które nasłuchuje settings.js.

import { h, icon, clear, uid, setIconHref } from './dom.js';
import { formatNumber } from './i18n.js';

function shell({ id, label, hint, control, input = control, aside, extra }) {
  const hintId = hint ? `${id}-hint` : null;
  if (hintId) input.setAttribute('aria-describedby', hintId);
  return h(
    'div',
    { class: 'field' },
    h('div', { class: 'field-head' }, h('label', { class: 'field-label', for: id }, label), aside || null),
    control,
    extra || null,
    hint ? h('p', { class: 'field-hint', id: hintId }, hint) : null,
  );
}

export function textField({ label, hint, placeholder, maxlength = 200 }) {
  const id = uid('f');
  const input = h('input', { class: 'input', id, type: 'text', placeholder, maxlength, autocomplete: 'off', spellcheck: 'false' });
  return {
    el: shell({ id, label, hint, control: input }),
    get: () => input.value.trim(),
    set: (value) => {
      input.value = value == null ? '' : String(value);
    },
  };
}

/** Pole liczbowe jako tekst z klawiaturą numeryczną – akceptuje przecinek dziesiętny. */
export function numberField({ label, hint, min, max, integer = false, unit }) {
  const id = uid('f');
  const input = h('input', {
    class: 'input input-number', id, type: 'text', inputmode: integer ? 'numeric' : 'decimal',
    autocomplete: 'off', spellcheck: 'false', maxlength: 12,
  });
  const control = unit ? h('div', { class: 'input-unit' }, input, h('span', { class: 'unit', 'aria-hidden': 'true' }, unit)) : input;
  if (unit) input.setAttribute('aria-label', `${label} (${unit})`);
  const range = min != null && max != null ? `${formatNumber(min)}–${formatNumber(max)}` : '';
  const get = () => {
    const raw = input.value.trim().replace(',', '.');
    if (!raw || !/^-?\d+(\.\d+)?$/.test(raw)) return NaN;
    const value = Number(raw);
    return integer ? Math.round(value) : value;
  };
  const wrapper = shell({ id, label, hint: hint || (range ? `Zakres: ${range}${unit ? ` ${unit}` : ''}.` : ''), control, input });
  return {
    el: wrapper,
    get,
    set: (value) => {
      input.value = typeof value === 'number' && Number.isFinite(value) ? formatNumber(value) : '';
    },
    validate: () => {
      const value = get();
      if (!Number.isFinite(value)) return `Pole „${label}” musi zawierać liczbę.`;
      if ((min != null && value < min) || (max != null && value > max)) return `Pole „${label}” musi mieć wartość z zakresu ${range}.`;
      return null;
    },
  };
}

export function toggleField({ label, hint }) {
  const id = uid('f');
  const hintId = hint ? `${id}-hint` : null;
  const input = h('input', { class: 'switch-input', id, type: 'checkbox', role: 'switch', 'aria-describedby': hintId });
  const el = h(
    'div',
    { class: 'field field-switch' },
    h('label', { class: 'switch', for: id }, input, h('span', { class: 'switch-track', 'aria-hidden': 'true' }), h('span', { class: 'switch-label' }, label)),
    hint ? h('p', { class: 'field-hint', id: hintId }, hint) : null,
  );
  return {
    el,
    input,
    get: () => input.checked,
    set: (value) => {
      input.checked = Boolean(value);
    },
  };
}

export function rangeField({ label, hint, min, max, step, format, extra }) {
  const id = uid('f');
  const input = h('input', { class: 'range', id, type: 'range', min, max, step });
  const output = h('output', { class: 'field-value', for: id });
  const update = () => {
    const value = Number(input.value);
    output.textContent = format(value);
    input.setAttribute('aria-valuetext', output.textContent);
    input.style.setProperty('--fill', `${((value - min) / (max - min)) * 100}%`);
  };
  input.addEventListener('input', update);
  return {
    el: shell({ id, label, hint, control: input, aside: output, extra }),
    input,
    get: () => Number(input.value),
    set: (value) => {
      const n = Number(value);
      input.value = String(Number.isFinite(n) ? n : min);
      update();
    },
  };
}

export function selectField({ label, hint, options }) {
  const id = uid('f');
  const select = h('select', { class: 'input', id }, options.map((o) => h('option', { value: o.value }, o.label)));
  return {
    el: shell({ id, label, hint, control: select }),
    get: () => select.value,
    set: (value) => {
      const v = value == null ? '' : String(value);
      if (!Array.from(select.options).some((o) => o.value === v)) select.append(h('option', { value: v }, v || '—'));
      select.value = v;
    },
  };
}

/**
 * Lista rozwijana wypełniana z API. Gdy lista nie dotrze, zamienia się w pole tekstowe.
 * @param {string} [emptyLabel] etykieta opcji z pustą wartością (np. „Domyślne”)
 */
export function remoteSelectField({ label, hint, emptyLabel, placeholder }) {
  const id = uid('f');
  const select = h('select', { class: 'input', id });
  const text = h('input', { class: 'input', id: `${id}-text`, type: 'text', placeholder, autocomplete: 'off', spellcheck: 'false', hidden: true });
  const note = h('p', { class: 'field-note', hidden: true });
  const labelEl = h('label', { class: 'field-label', for: id }, label);
  const hintId = hint ? `${id}-hint` : null;
  if (hintId) {
    select.setAttribute('aria-describedby', hintId);
    text.setAttribute('aria-describedby', hintId);
  }
  const el = h('div', { class: 'field' }, h('div', { class: 'field-head' }, labelEl), select, text, note, hint ? h('p', { class: 'field-hint', id: hintId }, hint) : null);

  let options = null; // null = lista jeszcze nie wczytana
  let textMode = false;

  function renderOptions(value) {
    clear(select);
    if (emptyLabel != null) select.append(h('option', { value: '' }, emptyLabel));
    for (const o of options || []) select.append(h('option', { value: o.value }, o.label));
    const known = (emptyLabel != null && value === '') || (options || []).some((o) => o.value === value);
    if (!known && value !== '') select.append(h('option', { value }, options ? `${value} (niedostępne)` : value));
    if (!known && value === '' && emptyLabel == null) select.append(h('option', { value: '' }, '—'));
    select.value = value;
  }

  function get() {
    return textMode ? text.value.trim() : select.value;
  }

  renderOptions('');

  return {
    el,
    get,
    set(value) {
      const v = value == null ? '' : String(value);
      text.value = v;
      renderOptions(v);
    },
    /** @param {{value: string, label: string}[]} list */
    setOptions(list) {
      const value = get();
      options = list;
      textMode = false;
      select.hidden = false;
      text.hidden = true;
      note.hidden = true;
      labelEl.htmlFor = select.id;
      renderOptions(value);
    },
    setUnavailable(message) {
      const value = get();
      textMode = true;
      text.value = value;
      select.hidden = true;
      text.hidden = false;
      labelEl.htmlFor = text.id;
      note.textContent = message;
      note.hidden = false;
    },
  };
}

/** Pole wielowierszowe – jedna pozycja w linii → tablica tekstów. */
export function linesField({ label, hint, rows = 4, placeholder }) {
  const id = uid('f');
  const textarea = h('textarea', { class: 'input textarea', id, rows, placeholder, spellcheck: 'false' });
  return {
    el: shell({ id, label, hint, control: textarea }),
    get: () => textarea.value.split('\n').map((s) => s.trim()).filter(Boolean),
    set: (value) => {
      textarea.value = (Array.isArray(value) ? value : []).join('\n');
    },
  };
}

/** Pole sekretu (klucza API): puste = bez zmian; placeholder pokazuje, czy klucz jest ustawiony. */
export function secretField({ key, label, hint }) {
  const id = uid('s');
  const input = h('input', {
    class: 'input mono', id, type: 'password', autocomplete: 'new-password', spellcheck: 'false',
    autocapitalize: 'off', placeholder: 'brak', 'aria-describedby': `${id}-hint`,
  });
  const revealIcon = icon('eye');
  const reveal = h('button', { type: 'button', class: 'icon-btn', 'aria-label': 'Pokaż wpisany klucz', 'aria-pressed': 'false', title: 'Pokaż' }, revealIcon);
  reveal.addEventListener('click', () => setRevealed(input.type === 'password'));
  const badge = h('span', { class: 'secret-badge' });
  const el = h(
    'div',
    { class: 'field' },
    h('div', { class: 'field-head' }, h('label', { class: 'field-label', for: id }, label), badge),
    h('div', { class: 'input-group' }, input, reveal),
    h('p', { class: 'field-hint', id: `${id}-hint` }, h('code', null, key), ` — ${hint}`),
  );

  function setRevealed(show) {
    input.type = show ? 'text' : 'password';
    reveal.setAttribute('aria-pressed', String(show));
    setIconHref(revealIcon.querySelector('use'), show ? 'eye-off' : 'eye');
  }

  return {
    key,
    el,
    get: () => input.value.trim(),
    focus: () => input.focus(),
    clear() {
      input.value = '';
      setRevealed(false);
    },
    setState(state) {
      const isSet = Boolean(state && state.set);
      input.placeholder = isSet ? `ustawiony ${(state && state.hint) || ''}`.trim() : 'brak';
      badge.textContent = isSet ? 'ustawiony' : 'brak';
      badge.className = `secret-badge ${isSet ? 'is-set' : 'is-missing'}`;
    },
  };
}

const MESSENGER_REF = /^(?:(?:https?:\/\/)?(?:www\.)?messenger\.com\/)?\/?(?:e2ee\/)?(?:t\/)?\d{5,25}\/?$/;

/** Edytowalna tabela kontaktów (Discord i/lub Messenger). */
export function contactsEditor() {
  const list = h('ul', { class: 'contacts-list' });
  const empty = h('p', { class: 'contacts-empty' }, 'Brak kontaktów. Dodaj osobę, do której Jarvis ma pisać na Discordzie albo Messengerze.');
  // podpowiedzi ostatnich rozmów z Messengera (gdy jest włączony i zalogowany)
  const threadsList = h('datalist', { id: uid('mthreads') });
  const addBtn = h('button', { type: 'button', class: 'btn' }, icon('plus'), 'Dodaj kontakt');
  const head = h(
    'div',
    { class: 'contacts-row contacts-head', 'aria-hidden': 'true' },
    h('span', null, 'Nazwa'),
    h('span', null, 'ID kanału Discord'),
    h('span', null, 'Czat Messengera (link)'),
    h('span', null, 'Aliasy (po przecinku)'),
    h('span'),
  );
  const el = h('div', { class: 'contacts' }, head, list, empty, h('div', { class: 'contacts-actions' }, addBtn), threadsList);
  const rows = new Map(); // <li> → pola

  addBtn.addEventListener('click', () => {
    addRow({}, true);
    notify();
  });

  function notify() {
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function syncEmpty() {
    empty.hidden = rows.size > 0;
    head.hidden = rows.size === 0;
  }

  function addRow(contact, focus) {
    const n = rows.size + 1;
    const name = h('input', {
      class: 'input input-upper', type: 'text', value: contact.name || '', placeholder: 'np. PIOTREK',
      'aria-label': `Nazwa kontaktu ${n}`, autocomplete: 'off', spellcheck: 'false', autocapitalize: 'characters', maxlength: 40,
    });
    const channel = h('input', {
      class: 'input mono', type: 'text', inputmode: 'numeric', value: contact.channel_id || '', placeholder: 'np. 123456789012345678',
      'aria-label': `ID kanału Discord kontaktu ${n}`, autocomplete: 'off', spellcheck: 'false', maxlength: 25,
    });
    const messenger = h('input', {
      class: 'input mono', type: 'text', value: contact.messenger || '', placeholder: 'messenger.com/t/…',
      list: threadsList.id, 'aria-label': `Czat Messengera kontaktu ${n}`, autocomplete: 'off', spellcheck: 'false', maxlength: 120,
    });
    const aliases = h('input', {
      class: 'input', type: 'text', value: (contact.aliases || []).join(', '), placeholder: 'np. Piotr, Piotrka',
      'aria-label': `Aliasy kontaktu ${n}`, autocomplete: 'off', spellcheck: 'false', maxlength: 300,
    });
    const row = h('li', { class: 'contacts-row' });
    const remove = h('button', { type: 'button', class: 'icon-btn icon-btn-danger', 'aria-label': `Usuń kontakt ${n}`, title: 'Usuń kontakt' }, icon('trash'));
    remove.addEventListener('click', () => {
      const next = row.nextElementSibling || row.previousElementSibling;
      rows.delete(row);
      row.remove();
      syncEmpty();
      notify();
      (next ? next.querySelector('input') : addBtn).focus();
    });
    row.append(name, channel, messenger, aliases, remove);
    rows.set(row, { name, channel, messenger, aliases });
    list.append(row);
    syncEmpty();
    if (focus) name.focus();
  }

  function setIfIdle(input, value) {
    if (input.value !== value && document.activeElement !== input) input.value = value;
  }

  function get() {
    const result = [];
    for (const f of rows.values()) {
      const contact = {
        name: f.name.value.trim().toLocaleUpperCase('pl'),
        channel_id: f.channel.value.trim(),
        messenger: f.messenger.value.trim(),
        aliases: f.aliases.value.split(',').map((s) => s.trim()).filter(Boolean),
      };
      if (contact.name || contact.channel_id || contact.messenger || contact.aliases.length) result.push(contact);
    }
    return result;
  }

  syncEmpty();

  return {
    el,
    get,
    set(value) {
      const next = Array.isArray(value) ? value : [];
      if (rows.size === next.length) {
        // ta sama liczba wierszy: aktualizujemy wartości w miejscu, żeby nie gubić fokusu
        Array.from(rows.values()).forEach((f, i) => {
          const c = next[i] || {};
          setIfIdle(f.name, c.name || '');
          setIfIdle(f.channel, c.channel_id || '');
          setIfIdle(f.messenger, c.messenger || '');
          setIfIdle(f.aliases, (c.aliases || []).join(', '));
        });
        return;
      }
      clear(list);
      rows.clear();
      for (const contact of next) addRow(contact || {}, false);
      syncEmpty();
    },
    validate() {
      const errors = new Set();
      const seen = new Set();
      for (const c of get()) {
        if (!c.name) errors.add('Każdy kontakt musi mieć nazwę.');
        else if (seen.has(c.name)) errors.add('Nazwy kontaktów muszą być unikalne.');
        seen.add(c.name);
        const who = c.name || '?';
        if (c.channel_id && !/^\d{5,25}$/.test(c.channel_id)) errors.add(`Nieprawidłowe ID kanału Discorda dla kontaktu ${who}.`);
        if (c.messenger && !MESSENGER_REF.test(c.messenger)) errors.add(`Nieprawidłowy link do czatu Messengera dla kontaktu ${who}.`);
        if (!c.channel_id && !c.messenger) errors.add(`Kontakt ${who} potrzebuje ID kanału Discorda albo linku do czatu Messengera.`);
      }
      return errors.size ? Array.from(errors) : null;
    },
    /** Podpowiedzi w polu Messengera: [{ thread: 'e2ee/t/123', name: 'Natalia' }]. */
    setMessengerThreads(threads) {
      clear(threadsList).append(...threads.map((t) => h('option', { value: t.thread }, t.name)));
    },
  };
}
