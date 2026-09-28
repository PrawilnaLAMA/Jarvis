/* Ekran główny: co dziś, co zaległe, co w kolejnych dniach. */

(() => {
  'use strict';
  const { api, esc, toast, taskElement, miniTask, newChore } = Domownik;

  const el = {
    date: document.getElementById('heroDate'),
    greeting: document.getElementById('heroGreeting'),
    summary: document.getElementById('heroSummary'),
    progress: document.getElementById('progress'),
    fill: document.getElementById('progressFill'),
    streak: document.getElementById('statStreak'),
    week: document.getElementById('statWeek'),
    active: document.getElementById('statActive'),
    bubble: document.getElementById('dogBubble'),
    dog: document.querySelector('.hero__dog .dog'),
    shifts: document.getElementById('heroShifts'),
    todayList: document.getElementById('todayList'),
    todayEmpty: document.getElementById('todayEmpty'),
    todayCounter: document.getElementById('todayCounter'),
    overdueCard: document.getElementById('overdueCard'),
    overdueList: document.getElementById('overdueList'),
    overdueCounter: document.getElementById('overdueCounter'),
    toggleOverdue: document.getElementById('toggleOverdue'),
    grid: document.getElementById('upcomingGrid'),
  };

  const MAX_MINI = 4;

  function greeting() {
    const h = new Date().getHours();
    if (h < 5) return 'Nocna zmiana?';
    if (h < 11) return 'Dzień dobry!';
    if (h < 17) return 'Cześć!';
    if (h < 22) return 'Dobry wieczór!';
    return 'Późno już…';
  }

  function bubbleText(stats, overdue) {
    if (stats.today_total === 0) return 'Dziś nic nie ma. Idziemy na spacer? 🦴';
    if (stats.today_done === 0 && overdue) return 'Trochę się nazbierało… ogarniemy to! 💪';
    if (stats.today_done === 0) return 'Hau! Zaczynamy od czegoś małego?';
    if (stats.today_done < stats.today_total) {
      const left = stats.today_total - stats.today_done;
      return `Zostało ${left} ${left === 1 ? 'zadanie' : 'zadania'}. Dasz radę!`;
    }
    return 'Wszystko zrobione! Jesteś najlepszy/a 🎉';
  }

  function summaryText(stats) {
    if (stats.today_total === 0) return 'Dzisiaj nie masz nic zaplanowanego. Wolne!';
    if (stats.today_done === stats.today_total) return `Komplet! ${stats.today_total} z ${stats.today_total} obowiązków odhaczone.`;
    return `Zrobione ${stats.today_done} z ${stats.today_total} rzeczy na dziś.`;
  }

  function renderStats(stats, hasOverdue) {
    el.greeting.textContent = greeting();
    el.summary.textContent = summaryText(stats);
    el.fill.style.width = `${stats.percent}%`;
    el.fill.classList.toggle('is-full', stats.percent === 100);
    el.progress.setAttribute('aria-valuenow', String(stats.percent));
    el.streak.textContent = stats.streak;
    el.week.textContent = stats.week_done;
    el.active.textContent = stats.active_chores;
    el.todayCounter.textContent = stats.today_total
      ? `${stats.today_done} / ${stats.today_total}` : 'wolne';
    el.bubble.textContent = bubbleText(stats, hasOverdue);
  }

  /** Kto dziś pracuje - żeby było widać, zanim ktoś zacznie się dziwić planowi. */
  function renderShifts(zmiany) {
    const pracujacy = zmiany.filter((z) => z.pracuje);
    if (!pracujacy.length) {
      el.shifts.hidden = true;
      el.shifts.replaceChildren();
      return;
    }
    el.shifts.replaceChildren(...pracujacy.map((z) => {
      const li = document.createElement('li');
      li.className = 'shift shift--praca';
      li.style.setProperty('--person', z.color);
      const tekst = document.createElement('span');
      tekst.className = 'shift__text';
      tekst.textContent = z.opis;
      li.appendChild(tekst);
      return li;
    }));
    el.shifts.hidden = false;
  }

  function renderToday(day) {
    el.todayList.replaceChildren();
    el.todayEmpty.hidden = day.items.length > 0;
    day.items.forEach((item) => el.todayList.appendChild(taskElement(item)));
  }

  function renderOverdue(items) {
    el.overdueCard.hidden = items.length === 0;
    el.overdueCounter.textContent = `${items.length} ${items.length === 1 ? 'zaległość' : 'zaległości'}`;
    el.overdueList.replaceChildren();
    items.slice(0, 25).forEach((item) =>
      el.overdueList.appendChild(taskElement(item, { lateBadge: true })));
  }

  function dayCard(day) {
    const card = document.createElement('article');
    card.className = `day-card${day.is_weekend ? ' day-card--weekend' : ''}`;

    const head = document.createElement('header');
    head.className = 'day-card__head';
    head.innerHTML = `
      <span class="day-card__day">${esc(day.label)}</span>
      <span class="day-card__date">${day.day} ${esc(day.month_name)}</span>`;
    card.appendChild(head);

    if (!day.items.length) {
      const empty = document.createElement('p');
      empty.className = 'day-card__empty';
      empty.textContent = '— wolne —';
      card.appendChild(empty);
      return card;
    }

    const list = document.createElement('div');
    list.className = 'day-card__list';
    day.items.slice(0, MAX_MINI).forEach((item) => list.appendChild(miniTask(item)));
    card.appendChild(list);

    if (day.items.length > MAX_MINI) {
      const more = document.createElement('p');
      more.className = 'day-card__more';
      more.textContent = `+ ${day.items.length - MAX_MINI} więcej`;
      card.appendChild(more);
    }
    return card;
  }

  function celebrate() {
    if (!el.dog) return;
    el.dog.classList.remove('is-happy');
    void el.dog.offsetWidth;            // restart animacji
    el.dog.classList.add('is-happy');
    setTimeout(() => el.dog.classList.remove('is-happy'), 1400);
  }

  async function load() {
    try {
      const data = await api('/api/agenda?dni=7');
      el.date.textContent = data.today_long;
      renderStats(data.stats, data.overdue.length > 0);
      renderShifts(data.grafik?.[data.today] || []);
      renderToday(data.days[0]);
      renderOverdue(data.overdue);
      el.grid.replaceChildren(...data.days.slice(1).map(dayCard));
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  el.toggleOverdue?.addEventListener('click', () => {
    const hidden = el.overdueList.hasAttribute('hidden');
    el.overdueList.toggleAttribute('hidden', !hidden);
    el.toggleOverdue.textContent = hidden ? 'Zwiń' : 'Rozwiń';
  });

  document.addEventListener('domownik:changed', (ev) => {
    if (ev.detail?.reason === 'toggle' && ev.detail.done) celebrate();
    load();
  });

  // pierwszy start bez obowiązków — od razu zapraszamy do dodania
  load().then(() => {
    if (new URLSearchParams(location.search).has('nowy')) newChore();
  });
})();
