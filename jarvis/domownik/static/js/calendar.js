/* Zakładka kalendarza: siatka miesiąca + panel wybranego dnia. */

(() => {
  'use strict';
  const { api, esc, icon, toast, taskElement, newChore } = Domownik;

  const el = {
    title: document.getElementById('monthTitle'),
    counter: document.getElementById('monthCounter'),
    weekdays: document.getElementById('calWeekdays'),
    grid: document.getElementById('calGrid'),
    prev: document.getElementById('prevMonth'),
    next: document.getElementById('nextMonth'),
    todayBtn: document.getElementById('todayBtn'),
    panelWeekday: document.getElementById('panelWeekday'),
    panelDate: document.getElementById('panelDate'),
    panelCounter: document.getElementById('panelCounter'),
    panelList: document.getElementById('panelList'),
    panelEmpty: document.getElementById('panelEmpty'),
    panelAdd: document.getElementById('panelAdd'),
    panelShifts: document.getElementById('panelShifts'),
    debts: document.getElementById('monthDebts'),
    grafikBtn: document.getElementById('grafikBtn'),
  };

  const MAX_CHIPS = 3;
  // rozbijamy ISO ręcznie — new Date('2026-08-11') to północ UTC, co w innej
  // strefie potrafi cofnąć się o dzień (i o cały miesiąc na przełomie)
  const currentYM = () => Domownik.todayISO().split('-').map(Number);
  const [thisYear, thisMonth] = currentYM();
  const state = {
    year: thisYear,
    month: thisMonth,
    selected: null,
    month_data: null,
  };

  function dayButton(cell) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'cal-day';
    btn.dataset.date = cell.date;
    if (!cell.in_month) btn.classList.add('cal-day--out');
    if (cell.is_weekend) btn.classList.add('cal-day--weekend');
    if (cell.is_today) btn.classList.add('cal-day--today');
    if (cell.date === state.selected) btn.classList.add('is-selected');
    if (cell.total > 0 && cell.done === cell.total) btn.classList.add('cal-day--done');
    btn.setAttribute('aria-label', `${cell.long}, ${cell.total} obowiązków`);

    const num = document.createElement('span');
    num.className = 'cal-day__num';
    num.textContent = cell.day;
    btn.appendChild(num);

    // kto tego dnia pracuje — same godziny, bez rozpychania kratki
    const pracujacy = (state.month_data?.grafik?.[cell.date] || []).filter((z) => z.pracuje);
    if (pracujacy.length) {
      const shift = document.createElement('span');
      shift.className = 'cal-day__shift';
      shift.title = pracujacy.map((z) => z.opis).join('\n');
      shift.style.setProperty('--person', pracujacy[0].color);
      pracujacy.forEach((z) => {
        const kto = document.createElement('b');
        kto.textContent = z.initial;
        const czas = document.createElement('i');   // na wąskim ekranie chowamy godziny
        czas.textContent = z.godziny || 'praca';
        shift.append(kto, czas);
      });
      btn.appendChild(shift);
    }

    if (cell.total > 0 && cell.done === cell.total) {
      const dot = document.createElement('span');
      dot.className = 'cal-day__dot';
      dot.title = 'Wszystko zrobione';
      btn.appendChild(dot);
    }

    const items = document.createElement('span');
    items.className = 'cal-day__items';
    cell.items.slice(0, MAX_CHIPS).forEach((item) => {
      const chip = document.createElement('span');
      chip.className = `cal-chip${item.done ? ' is-done' : ''}`;
      chip.style.setProperty('--chip-color', Domownik.laneColor(item)); // czyje: Leon, Natalia, wspólne
      chip.textContent = item.title;
      items.appendChild(chip);
    });
    if (cell.items.length > MAX_CHIPS) {
      const more = document.createElement('span');
      more.className = 'cal-day__more';
      more.textContent = `+${cell.items.length - MAX_CHIPS}`;
      items.appendChild(more);
    }
    btn.appendChild(items);

    // wersja mobilna: same kropki zamiast nazw
    const dots = document.createElement('span');
    dots.className = 'cal-day__count';
    cell.items.slice(0, 6).forEach((item) => {
      const dot = document.createElement('i');
      dot.style.setProperty('--chip-color', Domownik.laneColor(item));
      if (item.done) dot.style.opacity = '.35';
      dots.appendChild(dot);
    });
    btn.appendChild(dots);

    btn.addEventListener('click', () => select(cell.date));
    btn.addEventListener('dblclick', () => newChore(cell.date));
    return btn;
  }

  function renderPanel(cell) {
    if (!cell) {
      el.panelDate.textContent = 'Wybierz dzień';
      el.panelWeekday.innerHTML = '&nbsp;';
      el.panelCounter.textContent = '';
      el.panelList.replaceChildren();
      el.panelEmpty.hidden = true;
      el.panelShifts.hidden = true;
      return;
    }
    el.panelWeekday.textContent = cell.label === cell.weekday ? cell.weekday : `${cell.label} · ${cell.weekday}`;
    el.panelDate.textContent = cell.long;
    el.panelCounter.textContent = cell.total ? `${cell.done} / ${cell.total}` : 'wolne';
    el.panelList.replaceChildren(...panelGroups(cell.items));
    el.panelEmpty.hidden = cell.items.length > 0;
    renderShifts(cell.date);
  }

  /** Zadania dnia pogrupowane po osobach, jak kolumny na ekranie „Dziś”. */
  function panelGroups(items) {
    const out = [];
    for (const lane of Domownik.lanes) {
      const mine = items.filter((item) => Domownik.laneOf(item) === lane.key);
      if (!mine.length) continue;
      const head = document.createElement('li');
      head.className = 'panel-lane';
      head.style.setProperty('--person', lane.color);
      head.textContent = lane.label;
      out.push(head, ...mine.map((item) => {
        const li = taskElement(item, { person: false });
        li.style.setProperty('--task-color', lane.color);
        return li;
      }));
    }
    return out;
  }

  /** Grafik pracy w panelu dnia + ręczna poprawka „ma wolne / pracuje". */
  function renderShifts(date) {
    const wczytani = Object.entries(state.month_data?.grafik_wczytany || {})
      .filter(([, jest]) => jest)
      .map(([osoba]) => osoba);
    if (!wczytani.length) {
      el.panelShifts.hidden = true;
      el.panelShifts.replaceChildren();
      return;
    }
    const wpisy = state.month_data?.grafik?.[date] || [];
    el.panelShifts.replaceChildren(...wczytani.map((osoba) => {
      const wpis = wpisy.find((z) => z.osoba === osoba) || null;
      const li = document.createElement('li');
      li.className = `shift${wpis?.pracuje ? ' shift--praca' : ''}`;
      if (wpis) li.style.setProperty('--person', wpis.color);
      const opis = wpis ? wpis.opis : 'wolne';
      li.innerHTML = `
        <span class="shift__text">${esc(opis)}${wpis?.reczne ? ' <em>(ręcznie)</em>' : ''}</span>
        <button type="button" class="btn btn--ghost btn--sm" data-toggle>
          ${wpis?.pracuje ? 'ma wolne' : 'pracuje'}
        </button>`;
      li.querySelector('[data-toggle]').addEventListener('click', () => {
        przestawDzien(osoba, date, !wpis?.pracuje, wpis);
      });
      return li;
    }));
    el.panelShifts.hidden = false;
  }

  async function przestawDzien(osoba, date, pracuje, wpis) {
    try {
      await api(`/api/grafik/${osoba}/dzien/${date}`, {
        method: 'PUT',
        body: { pracuje, od: (pracuje && wpis?.od) || '', do: (pracuje && wpis?.do) || '' },
      });
      Domownik.notifyChanged({ reason: 'grafik' });
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  /** „Do wyrównania" — pokazujemy tylko liczniki, które do końca miesiąca nie zeszły do zera. */
  function renderDebts(data) {
    const dlugi = data.dlugi || [];
    if (!dlugi.length) {
      el.debts.hidden = true;
      el.debts.replaceChildren();
      return;
    }
    el.debts.replaceChildren(...dlugi.map((d) => {
      const li = document.createElement('li');
      li.className = 'debt';
      li.style.setProperty('--person', d.color);
      li.innerHTML = `${icon('repeat')} <strong>${esc(d.obowiazek)}</strong> — ${esc(d.label)} ma ${d.ile}× z górki`;
      li.title = `${d.label} wziął(ęła) ten obowiązek ${d.ile}× za kogoś. `
        + 'Wyrówna się przy kolejnych turach — także w następnym miesiącu.';
      return li;
    }));
    el.debts.hidden = false;
  }

  function findCell(date) {
    return state.month_data?.cells.find((c) => c.date === date) || null;
  }

  function select(date) {
    state.selected = date;
    el.grid.querySelectorAll('.cal-day').forEach((btn) =>
      btn.classList.toggle('is-selected', btn.dataset.date === date));
    renderPanel(findCell(date));
  }

  async function load(keepSelection = true) {
    try {
      const data = await api(`/api/miesiac?rok=${state.year}&miesiac=${state.month}`);
      state.month_data = data;

      el.title.textContent = `${data.month_name} ${data.year}`;
      el.counter.textContent = data.total
        ? `${data.done} / ${data.total} w tym miesiącu` : 'pusty miesiąc';

      if (!el.weekdays.children.length) {
        el.weekdays.replaceChildren(...data.weekday_names.map((name) => {
          const span = document.createElement('span');
          span.textContent = name;
          return span;
        }));
      }

      if (!keepSelection || !findCell(state.selected)) {
        const inMonth = data.cells.filter((c) => c.in_month);
        state.selected = (inMonth.find((c) => c.is_today) || inMonth[0])?.date || null;
      }

      renderDebts(data);
      el.grid.replaceChildren(...data.cells.map(dayButton));
      renderPanel(findCell(state.selected));
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  function step(delta) {
    const target = state.month_data ? (delta < 0 ? state.month_data.prev : state.month_data.next) : null;
    if (target) {
      state.year = target.year;
      state.month = target.month;
    }
    load(false);
  }

  el.prev.addEventListener('click', () => step(-1));
  el.next.addEventListener('click', () => step(1));
  el.todayBtn.addEventListener('click', () => {
    [state.year, state.month] = currentYM();
    load(false);
  });
  el.panelAdd.addEventListener('click', () => newChore(state.selected || Domownik.todayISO()));
  el.grafikBtn?.addEventListener('click', () =>
    Grafik.open({ rok: state.year, miesiac: state.month }));

  document.addEventListener('keydown', (ev) => {
    if (document.getElementById('choreModal')?.hidden === false) return;
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || '')) return;
    if (ev.key === 'ArrowLeft') step(-1);
    if (ev.key === 'ArrowRight') step(1);
  });

  document.addEventListener('domownik:changed', () => load(true));

  load(false);
})();
