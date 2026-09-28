// Widok ustawień: karty sekcji i jeden pasek „Zapisz”, który wysyła tylko zmienione sekcje
// (PUT /api/settings) oraz wpisane klucze API (PUT /api/secrets).

import { $, h, icon, clear } from './dom.js';
import { formatNumber } from './i18n.js';
import { voiceInfo } from './store.js';
import {
  contactsEditor, linesField, numberField, rangeField, remoteSelectField,
  secretField, selectField, textField, toggleField,
} from './settings-fields.js';
import { createWakeMeter } from './wake-meter.js';

const SECRETS = [
  { key: 'GROQ_API_KEY', label: 'Groq', hint: 'wymagany: model językowy i rozpoznawanie mowy (Whisper).' },
  { key: 'CEREBRAS_API_KEY', label: 'Cerebras (opcjonalny zapas)', hint: 'używany, gdy Groq nie odpowiada.' },
  { key: 'DISCORD_USER_TOKEN', label: 'Token Discorda', hint: 'do czytania i wysyłania wiadomości.' },
];
const GENDERS = { Male: 'głos męski', Female: 'głos żeński' };
const MESSENGER_STATES = {
  off: 'Wyłączony.',
  starting: 'Uruchamiam przeglądarkę…',
  login: 'Czeka na zalogowanie – zaloguj się w oknie przeglądarki.',
  ready: 'Połączony.',
  error: 'Błąd',
};
const OK_VISIBLE_MS = 3500;

export function initSettings({ socket, store, api, onDirtyChange }) {
  const root = $('#settings-root');
  const controls = []; // { card, section, key, control, baseline } – key null = cała sekcja (lista)
  const cards = new Map(); // id → { el, badge, title, section }

  let original = null;
  let loaded = false;
  let loading = false;
  let saving = false;
  let visible = false;
  let modelsOk = false;
  let voicesOk = false;
  let ignoreChangesUntil = 0;
  let resultTimer = 0;
  let previewTimer = 0;
  let lastDirty = false;
  let pillsKey = '';
  let pendingFocus = null; // klucz API do zaznaczenia po wczytaniu

  // --- kontrolki ---

  const meter = createWakeMeter();
  const secretControls = SECRETS.map(secretField);
  const contacts = contactsEditor();
  const model = remoteSelectField({ label: 'Model', hint: 'Model Groq używany do rozmowy i wykonywania poleceń.', placeholder: 'np. openai/gpt-oss-120b' });
  const ttsVoice = remoteSelectField({ label: 'Głos syntezatora', placeholder: 'np. pl-PL-MarekNeural' });
  const inputDevice = remoteSelectField({ label: 'Mikrofon', emptyLabel: 'Domyślne', placeholder: 'puste = urządzenie domyślne' });
  const outputDevice = remoteSelectField({ label: 'Głośnik', emptyLabel: 'Domyślne', placeholder: 'puste = urządzenie domyślne' });
  const rate = rangeField({ label: 'Tempo mowy', min: -50, max: 100, step: 1, format: (v) => `${v > 0 ? '+' : ''}${v}%` });
  const pitch = rangeField({ label: 'Wysokość głosu', min: -30, max: 30, step: 1, format: (v) => `${v > 0 ? '+' : ''}${v} Hz` });
  const volume = rangeField({ label: 'Głośność', min: 0, max: 1.5, step: 0.01, format: (v) => `${Math.round(v * 100)}%` });
  const threshold = rangeField({
    label: 'Próg słowa wywołania',
    hint: 'Niższy próg — łatwiej wywołać Jarvisa, ale częściej zareaguje przypadkiem.',
    min: 0.05, max: 0.99, step: 0.01, format: (v) => formatNumber(v, 2), extra: meter.el,
  });
  threshold.input.addEventListener('input', () => meter.setThreshold(threshold.get()));

  const previewMsg = h('span', { class: 'inline-msg', role: 'status' });
  const previewBtn = h('button', { type: 'button', class: 'btn' }, icon('play'), 'Odsłuchaj');
  previewBtn.addEventListener('click', preview);

  const domownikUrl = textField({
    label: 'Adres innego serwera Domownika',
    hint: 'Tylko przy wyłączonym serwerze w Jarvisie – np. Jarvis na Raspberry Pi: http://raspberrypi.local:8080.',
    placeholder: 'http://raspberrypi.local:8080',
  });
  const domownikMsg = h('span', { class: 'inline-msg', role: 'status' });
  let domownikKey = '';

  const messengerMsg = h('span', { class: 'inline-msg', role: 'status' });
  const messengerShow = h('button', { type: 'button', class: 'btn' }, icon('eye'), 'Pokaż okno');
  const messengerHide = h('button', { type: 'button', class: 'btn btn-ghost' }, icon('eye-off'), 'Schowaj okno');
  messengerShow.addEventListener('click', () => messengerWindow(true));
  messengerHide.addEventListener('click', () => messengerWindow(false));
  let messengerKey = '';
  let threadsLoaded = false;
  const domownikBtn = h('button', { type: 'button', class: 'btn' }, icon('refresh'), 'Sprawdź połączenie');
  // autostart żyje w rejestrze Windows, nie w settings.json – przełącznik działa od razu, bez „Zapisz”
  const autostart = toggleField({ label: 'Uruchamiaj razem z Windowsem', hint: 'Jarvis startuje po zalogowaniu, bez okna konsoli. Działa od razu, bez zapisywania.' });
  const autostartMsg = h('span', { class: 'inline-msg', role: 'status' });
  const autostartBox = h('div', { hidden: true }, autostart.el, autostartMsg);
  autostart.input.addEventListener('change', saveAutostart);
  domownikBtn.addEventListener('click', checkDomownik);

  function fields(cardId, section, live = false) {
    return (key, control) => {
      controls.push({ card: cardId, section, key, control, baseline: null, live });
      return control.el;
    };
  }
  const llmF = fields('llm', 'llm');
  const outF = fields('voice-out', 'voice');
  // głos, tempo, wysokość i głośność działają na żywo: zapis od razu po zmianie + próbka
  const liveF = fields('voice-out', 'voice', true);
  const liveControls = [ttsVoice, rate, pitch, volume];
  let liveTimer = 0;
  for (const control of liveControls) {
    control.el.addEventListener('change', () => {
      clearTimeout(liveTimer);
      liveTimer = setTimeout(saveLive, 250);
    });
  }
  const inF = fields('voice-in', 'voice');
  const domF = fields('domownik', 'domownik');
  const discF = fields('discord', 'discord');
  const msgF = fields('messenger', 'messenger');
  const uiF = fields('ui', 'ui');

  const layout = [
    card(
      'voice-out', 'Głos', { section: 'voice', wide: true, desc: 'Zmiany działają od razu – po każdej usłyszysz próbkę. Głosy „wielojęzyczne” też mówią po polsku.' },
      liveF('tts_voice', ttsVoice),
      liveF('tts_rate', rate),
      liveF('tts_pitch', pitch),
      liveF('volume', volume),
      h('div', { class: 'field field-inline' }, previewBtn, previewMsg),
      outF('speak_text_replies', toggleField({ label: 'Czytaj na głos odpowiedzi na komendy wpisane' })),
    ),
    card(
      'contacts', 'Kontakty',
      { section: 'contacts', wide: true, desc: 'Osoby, do których Jarvis może pisać na Discordzie i Messengerze (wystarczy jedno z nich). Link do czatu Messengera skopiuj z paska adresu na messenger.com. Nazwy zapisywane są wielkimi literami, aliasy to inne formy imienia.' },
      fields('contacts', 'contacts')(null, contacts),
    ),
    card('secrets', 'Klucze API', { desc: 'Zapisywane w pliku .env. Zostaw pole puste, aby nie zmieniać klucza.' }, secretControls.map((s) => s.el)),
    card(
      'llm', 'Model językowy', { section: 'llm' },
      llmF('model', model),
      llmF('fallback_model', textField({ label: 'Model zapasowy (Cerebras)', hint: 'Używany, gdy Groq nie odpowiada.', placeholder: 'np. gpt-oss-120b' })),
      llmF('history_messages', numberField({ label: 'Pamięć rozmowy', hint: 'Ile ostatnich wiadomości rozmowy wysyłać do modelu (0–100).', min: 0, max: 100, integer: true, unit: 'wiad.' })),
    ),
    card(
      'voice-in', 'Rozpoznawanie mowy', { section: 'voice' },
      inF('listen', toggleField({ label: 'Nasłuchuj mikrofonu', hint: 'Wykrywanie słowa „Hej Jarvis”.' })),
      inF('wake_threshold', threshold),
      inF('barge_in', selectField({
        label: 'Przerywanie wypowiedzi Jarvisa',
        options: [
          { value: 'any', label: 'Dowolna mowa (z filtrem echa)' },
          { value: 'wakeword', label: 'Tylko „Hej Jarvis”' },
          { value: 'off', label: 'Wyłączone' },
        ],
      })),
      inF('follow_up_seconds', numberField({ label: 'Nasłuch po odpowiedzi', hint: 'Ile sekund po odpowiedzi można mówić dalej bez „Hej Jarvis” (0 = wyłączone, maks. 30).', min: 0, max: 30, unit: 's' })),
      inF('stt_model', selectField({
        label: 'Model rozpoznawania mowy',
        options: [
          { value: 'whisper-large-v3', label: 'whisper-large-v3 — dokładniejszy' },
          { value: 'whisper-large-v3-turbo', label: 'whisper-large-v3-turbo — szybszy' },
        ],
      })),
      inF('vocabulary', linesField({ label: 'Słownik', hint: 'Jedno słowo lub fraza w linii: imiona, nazwy własne, które Whisper ma rozpoznawać.', placeholder: 'np. Wałbrzych\nPiotrek', rows: 4 })),
      h('h3', { class: 'card-subtitle' }, 'Urządzenia audio'),
      inF('input_device', inputDevice),
      inF('output_device', outputDevice),
    ),
    card(
      'domownik', 'Domownik', { section: 'domownik', desc: 'Zakładka Dom: obowiązki domowe, kalendarz, lista zakupów i grafik Natalii. Domownik działa razem z Jarvisem, a telefony wchodzą na niego przez przeglądarkę (można go dodać do ekranu głównego).' },
      domF('serve', toggleField({ label: 'Uruchamiaj Domownika w Jarvisie', hint: 'Wyłącz tylko wtedy, gdy Domownik działa na innym komputerze – podaj wtedy jego adres niżej. Dwa serwery to dwa osobne zestawy danych.' })),
      domF('lan', toggleField({ label: 'Dostęp z telefonów w sieci domowej', hint: 'Za pierwszym razem Windows zapyta o zgodę zapory – zezwól w sieci prywatnej.' })),
      domF('port', numberField({ label: 'Port', hint: 'Od 1024 do 65535, domyślnie 8080.', min: 1024, max: 65535, integer: true })),
      domF('url', domownikUrl),
      h('div', { class: 'field field-inline' }, domownikBtn, domownikMsg),
    ),
    card(
      'discord', 'Discord', { section: 'discord' },
      discF('read_aloud', toggleField({ label: 'Czytaj wiadomości na głos' })),
      discF('poll_seconds', numberField({ label: 'Sprawdzanie nowych wiadomości co', hint: 'Od 1 do 300 sekund.', min: 1, max: 300, unit: 's' })),
    ),
    card(
      'messenger', 'Messenger', { section: 'messenger', desc: 'Messenger nie ma API dla prywatnych kont, więc Jarvis korzysta z messenger.com w osobnym oknie przeglądarki Chrome (bez Chrome – Edge albo Chromium). Za pierwszym razem zaloguj się w tym oknie, potem możesz je schować.' },
      msgF('enabled', toggleField({ label: 'Włącz Messengera' })),
      h('div', { class: 'field field-inline' }, messengerShow, messengerHide, messengerMsg),
      msgF('read_aloud', toggleField({ label: 'Czytaj wiadomości na głos' })),
      msgF('poll_seconds', numberField({ label: 'Sprawdzanie nowych wiadomości co', hint: 'Od 1 do 300 sekund.', min: 1, max: 300, unit: 's' })),
      msgF('browser', textField({ label: 'Przeglądarka (opcjonalnie)', hint: 'Ścieżka do pliku przeglądarki; puste = Chrome, a gdy go nie ma – Edge albo Chromium.', placeholder: 'automatycznie' })),
    ),
    card(
      'ui', 'Interfejs', { section: 'ui' },
      autostartBox,
      uiF('fullscreen', toggleField({ label: 'Pełny ekran', hint: 'Wymaga ponownego uruchomienia aplikacji.' })),
    ),
  ];

  // --- szkielet widoku ---

  const pills = h('ul', { class: 'sys-pills', 'aria-label': 'Stan systemu' });
  const loadingEl = h('div', { class: 'settings-loading', role: 'status' }, 'Wczytywanie ustawień…');
  const cardsEl = h('div', { class: 'cards', hidden: true }, layout);

  const saveMsg = h('p', { class: 'savebar-msg' });
  const resultEl = h('div', { class: 'savebar-result', hidden: true });
  const reloadBtn = h('button', { type: 'button', class: 'btn btn-small' }, icon('refresh'), 'Wczytaj ponownie');
  const discardBtn = h('button', { type: 'button', class: 'btn btn-ghost' }, 'Odrzuć');
  const saveLabel = h('span', null, 'Zapisz');
  const saveBtn = h('button', { type: 'button', class: 'btn btn-primary' }, icon('check'), saveLabel);
  const actions = h('div', { class: 'savebar-actions' }, discardBtn, saveBtn);
  const savebar = h('div', { class: 'savebar', hidden: true }, h('div', { class: 'savebar-text' }, saveMsg, resultEl), actions);

  root.append(
    h('header', { class: 'settings-head' }, h('h1', { class: 'view-title' }, 'Ustawienia'), pills),
    loadingEl,
    cardsEl,
    savebar,
  );

  cardsEl.addEventListener('input', onEdit);
  cardsEl.addEventListener('change', onEdit);
  saveBtn.addEventListener('click', save);
  discardBtn.addEventListener('click', discard);
  reloadBtn.addEventListener('click', () => reload(true));
  document.addEventListener('keydown', (e) => {
    if (visible && (e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
      e.preventDefault();
      save();
    }
  });

  socket.on('audio.level', (data) => {
    if (visible && data.source === 'mic' && data.wake != null) meter.push(data.wake);
  });

  socket.on('settings.changed', () => {
    if (!loaded || saving || Date.now() < ignoreChangesUntil) return;
    if (computeDirty().size) showResult('external', 'Ustawienia zmieniono w innym miejscu. Wczytanie ich odrzuci Twoje niezapisane zmiany.');
    else reload(false);
  });

  store.subscribe(renderPills);
  renderPills(store.get());
  store.subscribe(renderMessenger);
  renderMessenger(store.get());
  store.subscribe(renderDomownik);
  renderDomownik(store.get());

  return {
    onShow() {
      visible = true;
      if (!loaded) load();
      loadOptions();
      loadMessengerThreads();
      loadAutostart();
      meter.start();
      applyPendingFocus();
    },
    onHide() {
      visible = false;
      meter.stop();
    },
    focusSecret,
  };

  /** Przewija do pola klucza API i ustawia na nim fokus (np. z banera „brak klucza”). */
  function focusSecret(key) {
    pendingFocus = key;
    applyPendingFocus();
  }

  function applyPendingFocus() {
    if (!pendingFocus || !loaded || !visible) return;
    const field = secretControls.find((s) => s.key === pendingFocus);
    pendingFocus = null;
    if (!field) return;
    field.el.scrollIntoView({ block: 'center' });
    field.focus();
  }

  // --- budowanie ---

  function card(id, title, { section = null, wide = false, desc = '' }, ...content) {
    const badge = h('span', { class: 'card-badge', hidden: true }, 'zmienione');
    const titleId = `card-${id}`;
    const el = h(
      'section',
      { class: `card${wide ? ' card-wide' : ''}`, 'aria-labelledby': titleId },
      h('header', { class: 'card-head' }, h('h2', { class: 'card-title', id: titleId }, title), badge),
      desc ? h('p', { class: 'card-desc' }, desc) : null,
      content,
    );
    cards.set(id, { el, badge, title, section });
    return el;
  }

  // --- wczytywanie ---

  async function load() {
    if (loading) return;
    loading = true;
    clear(loadingEl).append('Wczytywanie ustawień…');
    loadingEl.classList.remove('is-error');
    loadingEl.hidden = false;
    try {
      const res = await api.settings();
      applyResponse(res);
      loaded = true;
      loadingEl.hidden = true;
      cardsEl.hidden = false;
      applyPendingFocus();
    } catch (err) {
      loadingEl.classList.add('is-error');
      clear(loadingEl).append(
        h('p', null, icon('error'), ` Nie udało się wczytać ustawień: ${err.message}`),
        h('button', { type: 'button', class: 'btn', onClick: load }, icon('refresh'), 'Spróbuj ponownie'),
      );
    } finally {
      loading = false;
    }
  }

  async function reload(discardLocal) {
    try {
      const res = await api.settings();
      if (discardLocal) for (const s of secretControls) s.clear();
      applyResponse(res);
      if (resultEl.classList.contains('is-external')) clearResult();
    } catch (err) {
      if (discardLocal) showResult('error', `Nie udało się wczytać ustawień: ${err.message}`);
    }
  }

  function applyResponse(res) {
    if (res && res.secrets) applySecrets(res.secrets);
    fill((res && res.settings) || {});
  }

  function applySecrets(secrets) {
    for (const s of secretControls) s.setState(secrets[s.key]);
  }

  function fill(settings) {
    original = settings;
    for (const c of controls) {
      const section = settings[c.section];
      const value = c.key == null ? section : section && typeof section === 'object' ? section[c.key] : undefined;
      c.control.set(value);
      c.baseline = JSON.stringify(c.control.get());
    }
    meter.setThreshold(threshold.get());
    refreshDirty();
  }

  function loadOptions() {
    if (!modelsOk) {
      api.llmModels()
        .then((res) => {
          const list = (res && Array.isArray(res.models) && res.models) || [];
          if (!list.length) throw new Error('pusta lista');
          model.setOptions(list.map((m) => ({ value: String(m), label: String(m) })));
          modelsOk = true;
        })
        .catch(() => model.setUnavailable('Nie udało się pobrać listy modeli — wpisz nazwę ręcznie.'))
        .then(refreshDirty);
    }
    if (!voicesOk) {
      api.ttsVoices()
        .then((res) => {
          const list = (res && Array.isArray(res.voices) && res.voices) || [];
          if (!list.length) throw new Error('pusta lista');
          ttsVoice.setOptions(list.filter((v) => v && v.name).map(voiceOption));
          voicesOk = true;
        })
        .catch(() => ttsVoice.setUnavailable('Nie udało się pobrać listy głosów — wpisz nazwę, np. pl-PL-MarekNeural.'))
        .then(refreshDirty);
    }
    // urządzenia odświeżamy przy każdym wejściu (mogły zostać podłączone)
    api.audioDevices()
      .then((res) => {
        inputDevice.setOptions(deviceOptions(res && res.inputs));
        outputDevice.setOptions(deviceOptions(res && res.outputs));
      })
      .catch(() => {
        const message = 'Nie udało się pobrać listy urządzeń — wpisz nazwę albo zostaw puste (domyślne).';
        inputDevice.setUnavailable(message);
        outputDevice.setUnavailable(message);
      })
      .then(refreshDirty);
  }

  // --- zmiany i zapis ---

  function onEdit() {
    if (!loaded) return;
    const ids = refreshDirty();
    // komunikat o sukcesie znika przy edycji; błędy – gdy wszystkie zmiany cofnięto
    if (resultEl.classList.contains('is-ok') || (!ids.size && resultEl.classList.contains('is-error'))) clearResult();
  }

  function computeDirty() {
    const ids = new Set();
    if (!loaded) return ids;
    for (const c of controls) {
      if (!c.live && JSON.stringify(c.control.get()) !== c.baseline) ids.add(c.card);
    }
    if (secretControls.some((s) => s.get())) ids.add('secrets');
    return ids;
  }

  function refreshDirty() {
    const ids = computeDirty();
    for (const [id, c] of cards) c.badge.hidden = !ids.has(id);
    const dirty = ids.size > 0;
    const titles = Array.from(ids, (id) => cards.get(id).title);
    saveMsg.textContent = dirty ? `Niezapisane zmiany: ${titles.join(', ')}` : '';
    saveMsg.hidden = !dirty;
    actions.hidden = !dirty;
    savebar.hidden = !dirty && resultEl.hidden;
    if (dirty !== lastDirty) {
      lastDirty = dirty;
      if (onDirtyChange) onDirtyChange(dirty);
    }
    return ids;
  }

  function validate(ids) {
    const errors = [];
    for (const c of controls) {
      if (!ids.has(c.card) || !c.control.validate) continue;
      const result = c.control.validate();
      if (Array.isArray(result)) errors.push(...result);
      else if (result) errors.push(result);
    }
    return errors;
  }

  function collectSection(section) {
    const whole = controls.find((c) => c.section === section && c.key == null);
    if (whole) return whole.control.get();
    const out = { ...((original && original[section]) || {}) };
    for (const c of controls) if (c.section === section) out[c.key] = c.control.get();
    return out;
  }

  async function save() {
    if (saving || !loaded) return;
    const ids = refreshDirty();
    if (!ids.size) return;
    const errors = validate(ids);
    if (errors.length) {
      showResult('error', 'Popraw błędy przed zapisem:', errors);
      return;
    }

    const patch = {};
    for (const id of ids) {
      const section = cards.get(id).section;
      if (section && !(section in patch)) patch[section] = collectSection(section);
    }
    const secretPatch = {};
    for (const s of secretControls) if (s.get()) secretPatch[s.key] = s.get();

    setSaving(true);
    const failures = [];
    if (Object.keys(patch).length) {
      try {
        const res = await api.saveSettings(patch);
        fill(res && res.settings ? res.settings : { ...original, ...patch });
      } catch (err) {
        failures.push(failure('Nie zapisano ustawień', err));
      }
    }
    if (Object.keys(secretPatch).length) {
      try {
        const res = await api.saveSecrets(secretPatch);
        for (const s of secretControls) s.clear();
        if (res && res.secrets) applySecrets(res.secrets);
      } catch (err) {
        failures.push(failure('Nie zapisano kluczy API', err));
      }
    }
    ignoreChangesUntil = Date.now() + 2000;
    setSaving(false);

    if (failures.length) {
      const list = [];
      for (const f of failures) list.push(...f.errors);
      showResult('error', failures.map((f) => f.message).join(' '), list);
    } else {
      showResult('ok', 'Zapisano ustawienia.');
    }
  }

  function discard() {
    for (const s of secretControls) s.clear();
    if (original) fill(original);
    clearResult();
  }

  function setSaving(value) {
    saving = value;
    saveBtn.disabled = value;
    discardBtn.disabled = value;
    saveLabel.textContent = value ? 'Zapisywanie…' : 'Zapisz';
    savebar.setAttribute('aria-busy', String(value));
  }

  function showResult(kind, message, list = []) {
    clearTimeout(resultTimer);
    clear(resultEl);
    resultEl.className = `savebar-result is-${kind}`;
    resultEl.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    const iconName = kind === 'ok' ? 'check' : kind === 'error' ? 'error' : 'info';
    resultEl.append(h('p', { class: 'savebar-result-title' }, icon(iconName), h('span', null, message)));
    if (list.length) resultEl.append(h('ul', { class: 'savebar-errors' }, list.map((e) => h('li', null, e))));
    if (kind === 'external') resultEl.append(reloadBtn);
    resultEl.hidden = false;
    if (kind === 'ok') resultTimer = setTimeout(clearResult, OK_VISIBLE_MS);
    refreshDirty();
  }

  function clearResult() {
    clearTimeout(resultTimer);
    resultEl.hidden = true;
    resultEl.className = 'savebar-result';
    refreshDirty();
  }

  /** Zapis ustawień głosu od razu po zmianie (bez paska „Zapisz”) i odtworzenie próbki. */
  async function saveLive() {
    if (!loaded) return;
    const live = controls.filter((c) => c.live);
    const patch = {};
    for (const c of live) patch[c.key] = c.control.get();
    clearTimeout(previewTimer);
    setInline('Zapisuję…', '');
    ignoreChangesUntil = Date.now() + 2000;
    try {
      const res = await api.saveSettings({ voice: patch });
      const saved = (res && res.settings && res.settings.voice) || patch;
      original = { ...original, voice: { ...((original && original.voice) || {}), ...patch, ...pick(saved, Object.keys(patch)) } };
      for (const c of live) c.baseline = JSON.stringify(c.control.get());
    } catch (err) {
      setInline(`Nie zapisano: ${err.errors && err.errors.length ? err.errors.join(' ') : err.message}`, 'error');
      previewTimer = setTimeout(() => setInline('', ''), 6000);
      return;
    }
    await preview();
  }

  async function preview() {
    clearTimeout(previewTimer);
    previewBtn.disabled = true;
    setInline('Odtwarzam próbkę…', '');
    try {
      await api.ttsPreview(ttsVoice.get(), rate.get(), pitch.get());
      previewTimer = setTimeout(() => setInline('', ''), 3000);
    } catch (err) {
      setInline(`Nie udało się odtworzyć próbki: ${err.message}`, 'error');
      previewTimer = setTimeout(() => setInline('', ''), 6000);
    } finally {
      previewBtn.disabled = false;
    }
  }

  function setInline(text, kind, el = previewMsg) {
    el.textContent = text;
    el.className = `inline-msg${kind ? ` is-${kind}` : ''}`;
  }

  // --- Messenger ---

  function renderMessenger(s) {
    const m = (s.status && s.status.messenger) || { enabled: false, state: 'off', error: '' };
    const key = JSON.stringify(m);
    if (key === messengerKey) return;
    messengerKey = key;
    const active = m.state === 'login' || m.state === 'ready';
    messengerShow.disabled = !active;
    messengerHide.disabled = !active;
    const text = m.state === 'error' ? `Błąd: ${m.error}` : m.enabled && m.state === 'off' ? MESSENGER_STATES.starting : MESSENGER_STATES[m.state] || m.state;
    setInline(text, m.state === 'error' ? 'error' : m.state === 'ready' ? 'ok' : '', messengerMsg);
    if (m.state === 'ready') loadMessengerThreads();
  }

  /** Podpowiedzi ostatnich rozmów w polu „Czat Messengera” kontaktów. */
  function loadMessengerThreads() {
    const st = store.get().status;
    if (threadsLoaded || !visible || !st || !st.messenger || st.messenger.state !== 'ready') return;
    threadsLoaded = true;
    api.messengerThreads()
      .then((res) => contacts.setMessengerThreads((res && res.threads) || []))
      .catch(() => {
        threadsLoaded = false;
      });
  }

  async function messengerWindow(show) {
    try {
      await api.messengerWindow(show);
    } catch (err) {
      setInline(err.message, 'error', messengerMsg);
    }
  }

  async function loadAutostart() {
    try {
      const res = await api.autostart();
      autostartBox.hidden = !res.supported;
      autostart.set(res.enabled);
    } catch {
      autostartBox.hidden = true;
    }
  }

  async function saveAutostart() {
    const enabled = autostart.get();
    autostart.input.disabled = true;
    try {
      const res = await api.setAutostart(enabled);
      autostart.set(res.enabled);
      setInline(res.enabled ? 'Jarvis wystartuje po następnym zalogowaniu.' : 'Autostart wyłączony.', 'ok', autostartMsg);
    } catch (err) {
      autostart.set(!enabled);
      setInline(err.message, 'error', autostartMsg);
    } finally {
      autostart.input.disabled = false;
    }
  }

  function renderDomownik(s) {
    const d = s.status && s.status.domownik;
    const key = JSON.stringify(d || null);
    if (!d || key === domownikKey) return;
    domownikKey = key;
    showDomownik(d, d.state === 'running' || !d.serve);
  }

  function showDomownik(d, ok) {
    if (!d.serve) {
      setInline(ok ? `Korzystam z Domownika pod adresem ${d.url}.` : d.error || 'Domownik nie odpowiada.', ok ? 'ok' : 'error', domownikMsg);
    } else if (d.state === 'running') {
      setInline(d.lan_url ? `Działa. Na telefonie otwórz ${d.lan_url}` : 'Działa – tylko na tym komputerze.', 'ok', domownikMsg);
    } else if (d.state === 'error') {
      setInline(d.error, 'error', domownikMsg);
    } else {
      setInline('Domownik się uruchamia…', '', domownikMsg);
    }
  }

  /** Sprawdza zapisane ustawienia – przy niezapisanej zmianie najpierw prosi o zapis. */
  async function checkDomownik() {
    if (computeDirty().has('domownik')) {
      setInline('Najpierw zapisz zmiany.', 'error', domownikMsg);
      return;
    }
    domownikBtn.disabled = true;
    setInline('Sprawdzam…', '', domownikMsg);
    try {
      const res = await api.domownikStatus();
      if (res && res.ok) showDomownik(res, true);
      else setInline((res && res.error) || 'Domownik nie odpowiada.', 'error', domownikMsg);
    } catch (err) {
      setInline(`Nie udało się sprawdzić: ${err.message}`, 'error', domownikMsg);
    } finally {
      domownikBtn.disabled = false;
    }
  }

  // --- stan systemu ---

  function renderPills(s) {
    const st = s.status;
    const voice = voiceInfo(s);
    const messenger = (st && st.messenger) || {};
    const dom = (st && st.domownik) || {};
    const key = JSON.stringify([s.connected, st && st.version, voice.available, voice.muted, voice.error, st && st.llm_configured, st && st.discord_configured, messenger.enabled, messenger.state, dom.serve, dom.state, dom.error]);
    if (key === pillsKey) return;
    pillsKey = key;
    const items = [];
    if (!s.connected) items.push(pill('bad', 'Brak połączenia z Jarvisem'));
    else if (st) {
      if (voice.available === false) items.push(pill('bad', 'Głos niedostępny', voice.error));
      else if (voice.muted) items.push(pill('warn', 'Mikrofon wyciszony'));
      else items.push(pill('ok', 'Głos działa'));
      items.push(st.llm_configured ? pill('ok', 'Model językowy gotowy') : pill('bad', 'Brak klucza Groq'));
      items.push(st.discord_configured ? pill('ok', 'Discord skonfigurowany') : pill('warn', 'Discord nieskonfigurowany'));
      if (dom.serve) {
        if (dom.state === 'running') items.push(pill('ok', 'Domownik działa'));
        else if (dom.state === 'error') items.push(pill('bad', 'Domownik: błąd', dom.error));
        else items.push(pill('neutral', 'Domownik się uruchamia'));
      }
      if (messenger.enabled) {
        if (messenger.state === 'ready') items.push(pill('ok', 'Messenger połączony'));
        else if (messenger.state === 'login') items.push(pill('warn', 'Messenger: zaloguj się'));
        else if (messenger.state === 'error') items.push(pill('bad', 'Messenger: błąd', messenger.error));
        else items.push(pill('neutral', 'Messenger się uruchamia'));
      }
      if (st.version) items.push(pill('neutral', `Wersja ${st.version}`));
    }
    clear(pills).append(...items);
  }
}

/** Opis błędu zapisu; gdy backend podał listę błędów, nie powtarzamy jej w nagłówku. */
function failure(title, err) {
  const errors = (err && Array.isArray(err.errors) && err.errors) || [];
  return { message: errors.length ? `${title}:` : `${title}: ${err.message}`, errors };
}

function pill(kind, text, detail) {
  return h('li', { class: `pill is-${kind}`, title: detail ? String(detail) : null }, h('span', { class: 'pill-dot', 'aria-hidden': 'true' }), text, detail ? h('span', { class: 'sr-only' }, `: ${detail}`) : null);
}

function pick(obj, keys) {
  const out = {};
  for (const k of keys) if (obj && k in obj) out[k] = obj[k];
  return out;
}

function voiceOption(v) {
  const gender = GENDERS[v.gender];
  const label = v.label || v.name;
  return { value: String(v.name), label: gender ? `${label} · ${gender}` : String(label) };
}

function deviceOptions(list) {
  const names = [];
  for (const d of Array.isArray(list) ? list : []) {
    const name = d && typeof d === 'object' ? d.name : d;
    if (name && !names.includes(String(name))) names.push(String(name));
  }
  return names.map((name) => ({ value: name, label: name }));
}
