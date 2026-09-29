/* Ekran główny: plan dnia w kolumnach osób, zaległości zgrupowane po obowiązku, kolejne dni. */

(() => {
  'use strict';
  const { api, esc, icon, toast, taskElement, miniTask, newChore, dayShort, plural, setDone, laneOf } = Domownik;

  const el = {
    date: document.getElementById('heroDate'),
    greeting: document.getElementById('heroGreeting'),
    summary: document.getElementById('heroSummary'),
    progress: document.getElementById('progress'),
    ring: document.getElementById('reactorRing'),
    ringValue: document.getElementById('reactorValue'),
    ringLabel: document.getElementById('reactorLabel'),
    overdueCard: document.getElementById('overdueCard'),
    overdueList: document.getElementById('overdueList'),
    overdueCounter: document.getElementById('overdueCounter'),
    toggleOverdue: document.getElementById('toggleOverdue'),
    lanes: [...document.querySelectorAll('.lane')],
    grid: document.getElementById('upcomingGrid'),
  };

  const MAX_MINI = 4;
  const SVG = 'http://www.w3.org/2000/svg';
  const OVERDUE_KEY = 'domownik.zalegle-zwiniete';

  function greeting() {
    const h = new Date().getHours();
    if (h < 5) return 'Nocna zmiana?';
    if (h < 11) return 'Dzień dobry';
    if (h < 17) return 'Cześć';
    if (h < 22) return 'Dobry wieczór';
    return 'Późno już';
  }

  function summaryText(stats) {
    const streak = stats.streak > 1 ? ` Seria: ${stats.streak} ${plural(stats.streak, 'dzień', 'dni', 'dni')}.` : '';
    if (stats.today_total === 0) return `Na dziś nic nie ma – wolne.${streak}`;
    if (stats.today_done === stats.today_total) return `Komplet, wszystko na dziś odhaczone.${streak}`;
    const left = stats.today_total - stats.today_done;
    return `${left === 1 ? 'Została' : 'Zostały'} ${left} ${plural(left, 'rzecz', 'rzeczy', 'rzeczy')} z ${stats.today_total}.${streak}`;
  }

  /** Pierścień z segmentów – po jednym na zadanie; odhaczone świecą. */
  function renderRing(stats) {
    const total = stats.today_total;
    const done = stats.today_done;
    const r = 50;
    const segments = Math.max(total, 1);
    const gap = total > 1 ? Math.min(0.18, 1.2 / total) : 0; // rad
    const nodes = [];
    for (let i = 0; i < segments; i++) {
      const a0 = -Math.PI / 2 + (i / segments) * Math.PI * 2 + gap / 2;
      const a1 = -Math.PI / 2 + ((i + 1) / segments) * Math.PI * 2 - gap / 2;
      const large = a1 - a0 > Math.PI ? 1 : 0;
      const path = document.createElementNS(SVG, 'path');
      const p = (a) => `${(60 + r * Math.cos(a)).toFixed(2)} ${(60 + r * Math.sin(a)).toFixed(2)}`;
      path.setAttribute('d', total === 0
        ? `M ${p(-Math.PI / 2)} A ${r} ${r} 0 1 1 ${p(-Math.PI / 2 - 0.0001)}`
        : `M ${p(a0)} A ${r} ${r} 0 ${large} 1 ${p(a1)}`);
      path.setAttribute('class', `reactor__seg${i < done ? ' is-lit' : ''}`);
      path.style.setProperty('--i', i);
      nodes.push(path);
    }
    el.ring.replaceChildren(...nodes);
    el.ringValue.textContent = total ? `${done}/${total}` : '—';
    el.ringLabel.textContent = total ? 'na dziś' : 'wolne';
    el.progress.classList.toggle('is-full', total > 0 && done === total);
    el.progress.setAttribute('aria-valuenow', String(stats.percent));
  }

  function renderStats(stats) {
    el.greeting.textContent = greeting();
    el.summary.textContent = summaryText(stats);
    renderRing(stats);
  }

  // --- kolumny osób ---

  function renderLanes(day, zmiany) {
    for (const lane of el.lanes) {
      const key = lane.dataset.lane;
      const items = day.items.filter((item) => laneOf(item) === key);
      const done = items.filter((i) => i.done).length;
      lane.querySelector('[data-lane-list]').replaceChildren(...items.map((i) => taskElement(i, { person: false })));
      lane.querySelector('[data-lane-empty]').hidden = items.length > 0;
      lane.querySelector('[data-lane-count]').textContent = items.length ? `${done}/${items.length}` : '';
      lane.classList.toggle('is-done', items.length > 0 && done === items.length);
      // kto dziś pracuje – żeby było widać, zanim ktoś zacznie się dziwić planowi
      const shift = lane.querySelector('[data-lane-shift]');
      const praca = zmiany.find((z) => z.osoba === key && z.pracuje);
      shift.hidden = !praca;
      shift.textContent = praca ? `W pracy ${praca.godziny || 'cały dzień'}` : '';
    }
  }

  // --- zaległości: jeden wiersz na obowiązek, daty do odhaczenia ---

  function groupOverdue(items) {
    const groups = new Map();
    for (const item of items) {
      if (!groups.has(item.id)) groups.set(item.id, { item, dates: [] });
      groups.get(item.id).dates.push(item.date);
    }
    return [...groups.values()].map((g) => ({ ...g, dates: g.dates.sort() }));
  }

  function overdueRow({ item, dates }) {
    const li = document.createElement('li');
    li.className = 'overdue__row';
    li.style.setProperty('--task-color', item.color);
    const who = item.kto_label || 'wspólne';
    const count = dates.length;
    li.innerHTML = `
      <span class="overdue__title"><span aria-hidden="true">${esc(item.icon)}</span> ${esc(item.title)}</span>
      <span class="overdue__meta">${esc(who)} · ${count} ${plural(count, 'raz', 'razy', 'razy')}, od ${esc(dayShort(dates[0]))}</span>
      <span class="overdue__dates" role="group" aria-label="Odhacz zaległe dni"></span>`;
    const box = li.querySelector('.overdue__dates');
    const shown = dates.slice(-6); // najnowsze – starsze i tak rzadko kto nadrabia
    if (dates.length > shown.length) {
      const more = document.createElement('span');
      more.className = 'overdue__more';
      more.textContent = `+${dates.length - shown.length}`;
      box.append(more);
    }
    for (const date of shown) {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'date-chip';
      chip.innerHTML = `${icon('check')}<span>${esc(dayShort(date))}</span>`;
      chip.title = `Odhacz – zrobione ${dayShort(date)}`;
      chip.addEventListener('click', async () => {
        chip.classList.add('is-done');
        chip.disabled = true;
        try {
          await setDone(item.id, date, true);
        } catch (err) {
          chip.classList.remove('is-done');
          chip.disabled = false;
          toast(err.message, 'error');
        }
      });
      box.append(chip);
    }
    return li;
  }

  function renderOverdue(items) {
    const groups = groupOverdue(items).sort((a, b) => b.dates.length - a.dates.length);
    el.overdueCard.hidden = groups.length === 0;
    // zwinięte widać w jednej linii, czego się nazbierało – rozwinięcie daje daty do odhaczenia
    const names = groups.map((g) => (g.dates.length > 1 ? `${g.item.title} ×${g.dates.length}` : g.item.title));
    el.overdueCounter.textContent = `${items.length}: ${names.join(', ')}`;
    el.overdueCounter.title = names.join('\n');
    el.overdueList.replaceChildren(...groups.map(overdueRow));
  }

  function setOverdueCollapsed(collapsed, remember = false) {
    el.overdueList.hidden = collapsed;
    el.overdueCard.classList.toggle('is-collapsed', collapsed);
    el.toggleOverdue.textContent = collapsed ? 'Pokaż' : 'Zwiń';
    el.toggleOverdue.setAttribute('aria-expanded', String(!collapsed));
    if (remember) {
      try {
        localStorage.setItem(OVERDUE_KEY, collapsed ? '1' : '0');
      } catch { /* bez pamięci też działa */ }
    }
  }

  /** Domyślnie zwinięte – plan dnia jest ważniejszy; raz rozwinięte zostaje rozwinięte. */
  function overdueStartsCollapsed() {
    try {
      const saved = localStorage.getItem(OVERDUE_KEY);
      if (saved !== null) return saved === '1';
    } catch { /* prywatne okno */ }
    return true;
  }

  // --- kolejne dni ---

  function dayColumn(day, zmiany) {
    const col = document.createElement('article');
    col.className = `week-day${day.is_weekend ? ' week-day--weekend' : ''}`;
    const head = document.createElement('header');
    head.className = 'week-day__head';
    head.innerHTML = `
      <span class="week-day__name">${esc(day.label)}</span>
      <span class="week-day__date">${day.day} ${esc(day.month_name)}</span>`;
    col.appendChild(head);

    for (const z of zmiany.filter((s) => s.pracuje)) {
      const shift = document.createElement('p');
      shift.className = 'week-day__shift';
      shift.style.setProperty('--person', z.color);
      shift.textContent = `${z.initial} · ${z.godziny || 'praca'}`;
      shift.title = z.opis;
      col.appendChild(shift);
    }

    if (!day.items.length) {
      const empty = document.createElement('p');
      empty.className = 'week-day__empty';
      empty.textContent = 'wolne';
      col.appendChild(empty);
      return col;
    }
    const list = document.createElement('div');
    list.className = 'week-day__list';
    day.items.slice(0, MAX_MINI).forEach((item) => list.appendChild(miniTask(item)));
    col.appendChild(list);
    if (day.items.length > MAX_MINI) {
      const more = document.createElement('p');
      more.className = 'week-day__more';
      more.textContent = `i ${day.items.length - MAX_MINI} więcej`;
      col.appendChild(more);
    }
    return col;
  }

  function celebrate() {
    el.progress.classList.remove('is-pulse');
    void el.progress.offsetWidth; // restart animacji
    el.progress.classList.add('is-pulse');
  }

  async function load() {
    try {
      const data = await api('/api/agenda?dni=7');
      const grafik = data.grafik || {};
      el.date.textContent = data.today_long;
      renderStats(data.stats);
      renderOverdue(data.overdue);
      renderLanes(data.days[0], grafik[data.today] || []);
      el.grid.replaceChildren(...data.days.slice(1).map((day) => dayColumn(day, grafik[day.date] || [])));
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  el.toggleOverdue?.addEventListener('click', () => setOverdueCollapsed(!el.overdueList.hidden, true));
  setOverdueCollapsed(overdueStartsCollapsed());

  document.addEventListener('domownik:changed', (ev) => {
    if (ev.detail?.reason === 'toggle' && ev.detail.done) celebrate();
    load();
  });

  // pierwszy start bez obowiązków — od razu zapraszamy do dodania
  load().then(() => {
    if (new URLSearchParams(location.search).has('nowy')) newChore();
  });
})();
