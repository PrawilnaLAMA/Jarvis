// Formularz dodawania/edycji wydarzenia kalendarza.

import { h, uid } from './dom.js';
import { EVENT_TYPES, WEEKDAYS_LONG, WEEKDAYS_SHORT } from './i18n.js';
import { WEEKDAYS_EN, normalizeDate, normalizeTime, parseISODate, weekdayIndex } from './dates.js';

/**
 * @param {object} options
 * @param {object|null} options.event  edytowane wydarzenie albo null (nowe)
 * @param {string} options.date        wybrany dzień (RRRR-MM-DD) – domyślna data
 * @param {(data: object) => Promise<void>} options.onSubmit  rzuca błąd z komunikatem po polsku
 * @param {() => void} options.onCancel
 */
export function createEventForm({ event, date, onSubmit, onCancel }) {
  const id = uid('event');
  const isEdit = Boolean(event);
  const recurring = Boolean(event && Array.isArray(event.days) && event.days.length);

  const desc = h('input', {
    class: 'input', id: `${id}-desc`, type: 'text', required: true, maxlength: 200, autocomplete: 'off',
    value: (event && event.desc) || '',
  });
  const type = h('input', {
    class: 'input', id: `${id}-type`, type: 'text', list: `${id}-types`, maxlength: 40, autocomplete: 'off',
    placeholder: 'np. spotkanie', value: (event && event.type) || '',
  });
  const typeList = h('datalist', { id: `${id}-types` }, EVENT_TYPES.map((t) => h('option', { value: t })));

  const modeName = `${id}-mode`;
  const modeOnce = h('input', { type: 'radio', name: modeName, value: 'once', checked: !recurring });
  const modeWeekly = h('input', { type: 'radio', name: modeName, value: 'weekly', checked: recurring });
  const modeGroup = h(
    'fieldset',
    { class: 'field segmented-field' },
    h('legend', { class: 'field-label' }, 'Powtarzanie'),
    h(
      'div',
      { class: 'segmented' },
      h('label', null, modeOnce, h('span', null, 'Jednorazowe')),
      h('label', null, modeWeekly, h('span', null, 'Cykliczne')),
    ),
  );

  const dateInput = h('input', {
    class: 'input', id: `${id}-date`, type: 'date', placeholder: 'RRRR-MM-DD',
    value: (event && event.date) || date || '',
  });
  const onceBox = field('Data', dateInput);

  const dayBoxes = WEEKDAYS_EN.map((name) =>
    h('input', { type: 'checkbox', value: name, checked: recurring && event.days.includes(name) }),
  );
  const weeklyBox = h(
    'fieldset',
    { class: 'field' },
    h('legend', { class: 'field-label' }, 'Dni tygodnia'),
    h(
      'div',
      { class: 'day-picks' },
      dayBoxes.map((box, i) =>
        h(
          'label',
          { class: 'day-pick', title: WEEKDAYS_LONG[i] },
          box,
          h('span', { 'aria-hidden': 'true' }, WEEKDAYS_SHORT[i]),
          h('span', { class: 'sr-only' }, WEEKDAYS_LONG[i]),
        ),
      ),
    ),
  );

  const start = h('input', { class: 'input', id: `${id}-start`, type: 'time', placeholder: 'GG:MM', value: (event && event.start) || '' });
  const end = h('input', { class: 'input', id: `${id}-end`, type: 'time', placeholder: 'GG:MM', value: (event && event.end) || '' });

  const errorEl = h('p', { class: 'form-error', role: 'alert', hidden: true });
  const submitBtn = h('button', { type: 'submit', class: 'btn btn-primary' }, isEdit ? 'Zapisz zmiany' : 'Dodaj');
  const cancelBtn = h('button', { type: 'button', class: 'btn btn-ghost', onClick: () => onCancel() }, 'Anuluj');

  const form = h(
    'form',
    { class: 'event-form', novalidate: true, 'aria-labelledby': `${id}-title` },
    h('h3', { class: 'form-title', id: `${id}-title` }, isEdit ? 'Edycja wydarzenia' : 'Nowe wydarzenie'),
    isEdit && recurring ? h('p', { class: 'form-note' }, 'Zmiany dotyczą wszystkich powtórzeń tego wydarzenia.') : null,
    field('Opis', desc, true),
    field('Kategoria', type),
    typeList,
    modeGroup,
    onceBox,
    weeklyBox,
    h('div', { class: 'field-row' }, field('Początek', start), field('Koniec', end)),
    h('p', { class: 'field-hint' }, 'Bez godziny wydarzenie trwa cały dzień.'),
    errorEl,
    h('div', { class: 'form-actions' }, cancelBtn, submitBtn),
  );

  function syncMode() {
    const weekly = modeWeekly.checked;
    onceBox.hidden = weekly;
    weeklyBox.hidden = !weekly;
    // przy przejściu na „cykliczne” zaznaczamy dzień tygodnia wybranej daty
    if (weekly && !dayBoxes.some((b) => b.checked)) {
      const d = parseISODate(normalizeDate(dateInput.value) || date);
      if (d) dayBoxes[weekdayIndex(d)].checked = true;
    }
  }
  modeOnce.addEventListener('change', syncMode);
  modeWeekly.addEventListener('change', syncMode);
  syncMode();

  form.addEventListener('input', () => {
    errorEl.hidden = true;
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const result = collect();
    if (result.error) {
      showError(result.error);
      if (result.focus) result.focus.focus();
      return;
    }
    setBusy(true);
    try {
      await onSubmit(result.data);
    } catch (err) {
      showError((err && err.message) || 'Nie udało się zapisać wydarzenia.');
    } finally {
      setBusy(false);
    }
  });

  function collect() {
    const descValue = desc.value.trim();
    if (!descValue) return { error: 'Podaj opis wydarzenia.', focus: desc };

    let dateValue = null;
    let days = [];
    if (modeWeekly.checked) {
      days = dayBoxes.filter((b) => b.checked).map((b) => b.value);
      if (!days.length) return { error: 'Wybierz co najmniej jeden dzień tygodnia.', focus: dayBoxes[0] };
    } else {
      dateValue = normalizeDate(dateInput.value);
      if (!dateValue) return { error: 'Podaj poprawną datę (RRRR-MM-DD).', focus: dateInput };
    }

    const startValue = normalizeTime(start.value);
    if (startValue === null) return { error: 'Nieprawidłowa godzina rozpoczęcia. Użyj formatu GG:MM.', focus: start };
    const endValue = normalizeTime(end.value);
    if (endValue === null) return { error: 'Nieprawidłowa godzina zakończenia. Użyj formatu GG:MM.', focus: end };

    return {
      data: {
        type: type.value.trim(),
        desc: descValue,
        date: dateValue,
        days,
        start: startValue || null,
        end: endValue || null,
      },
    };
  }

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = false;
  }

  function setBusy(busy) {
    submitBtn.disabled = busy;
    cancelBtn.disabled = busy;
    form.setAttribute('aria-busy', String(busy));
  }

  return {
    el: form,
    focus: () => desc.focus(),
  };
}

function field(label, control, required = false) {
  return h(
    'div',
    { class: 'field' },
    h('label', { class: 'field-label', for: control.id }, label, required ? h('span', { class: 'req', 'aria-hidden': 'true' }, ' *') : null),
    control,
  );
}
