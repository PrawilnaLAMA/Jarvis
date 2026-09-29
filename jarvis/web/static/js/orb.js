// Animowana kula Jarvisa – „reaktor łukowy”.
//
// Warstwy (od tyłu): rdzeń z plazmą i poświatą (WebGL, js/orb-core.js – bez WebGL rysujemy go w 2D),
// pierścień reaktora z dziesięciu segmentów, łuki przetwarzania, skala z kreskami reagująca na dźwięk,
// pierścienie zewnętrzne i cząsteczki. Segmenty świecą w rytm głosu, a przy myśleniu obiega je światło.
// Poziom dźwięku (audio.level) wygładzamy: szybki atak, wolne opadanie – kula „oddycha” w rytm mowy
// przy 60 fps, choć pomiary przychodzą rzadziej. playIntro() rozkłada HUD wokół kuli (rozwinięcie okna).
// Przy minutniku (setTimer, js/timer.js) środek kuli ciemnieje pod cyframi, cewki stają i pokazują, ile
// zostało, cienka obręcz to dokładny postęp z jasnym czołem, a po skali biegnie sekundnik.

import { clamp, onMediaChange } from './dom.js';
import { OrbCore } from './orb-core.js';

const TAU = Math.PI * 2;
const POINTS = 128;
const ATTACK = 0.5; // współczynnik na klatkę przy 60 fps
const RELEASE = 0.08;
const LEVEL_TIMEOUT_MS = 300; // starszy pomiar traktujemy jak ciszę
const SYNTHETIC_AFTER_MS = 1200; // mówienie bez pomiarów TTS → łagodna animacja zastępcza
const WHITE = [255, 255, 255];
const DARK = [2, 9, 16];
// W spokojnych stanach wystarczy ~30 fps – oszczędza procesor (np. na Raspberry Pi).
const CALM_STATES = new Set(['idle', 'muted', 'offline']);
const CALM_FRAME_MS = 1000 / 30;
const SEGMENTS = 10; // cewki reaktora
const SEGMENT_GAP = 0.07; // rad
const SPHERE = 0.9; // promień kuli względem „bazy”

function look(core, glow, params) {
  return { core, glow, ...params };
}

// Wygląd i ruch dla każdego stanu; pomiędzy stanami wszystko jest płynnie interpolowane.
const LOOKS = {
  idle: look([56, 232, 255], [16, 104, 150], { brightness: 0.62, speed: 0.32, breath: 0.035, deform: 0.03, swirl: 0, react: 0 }),
  listening: look([70, 236, 255], [22, 150, 210], { brightness: 0.95, speed: 0.85, breath: 0.02, deform: 0.045, swirl: 0, react: 0.9 }),
  transcribing: look([98, 150, 255], [48, 72, 205], { brightness: 0.85, speed: 1.05, breath: 0.02, deform: 0.04, swirl: 0.75, react: 0 }),
  thinking: look([150, 116, 255], [80, 52, 196], { brightness: 0.9, speed: 1.35, breath: 0.03, deform: 0.05, swirl: 1, react: 0 }),
  speaking: look([196, 248, 255], [34, 186, 255], { brightness: 1, speed: 1, breath: 0.015, deform: 0.04, swirl: 0, react: 1 }),
  follow_up: look([56, 230, 200], [14, 136, 126], { brightness: 0.78, speed: 0.55, breath: 0.03, deform: 0.035, swirl: 0, react: 0.7 }),
  muted: look([136, 146, 158], [58, 66, 78], { brightness: 0.42, speed: 0.22, breath: 0.02, deform: 0.02, swirl: 0, react: 0 }),
  offline: look([84, 92, 106], [34, 40, 50], { brightness: 0.24, speed: 0.14, breath: 0.015, deform: 0.015, swirl: 0, react: 0 }),
};
const NUMERIC_KEYS = ['brightness', 'speed', 'breath', 'deform', 'swirl', 'react'];

// Z którego źródła dźwięku kula czerpie poziom w danym stanie.
const LEVEL_SOURCE = { listening: 'mic', follow_up: 'mic', speaking: 'tts' };

// Łuki widoczne podczas rozpoznawania mowy i myślenia (tuż za pierścieniem reaktora).
const ARCS = [
  { radius: 1.36, length: 1.1, speed: 1, width: 2, offset: 0, alpha: 0.85 },
  { radius: 1.36, length: 0.5, speed: 1, width: 2, offset: Math.PI, alpha: 0.7 },
  { radius: 1.45, length: 1.6, speed: -0.65, width: 1.1, offset: 1, alpha: 0.45 },
];

export class Orb {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.core = OrbCore.create(canvas);
    this.state = 'offline';
    this.target = LOOKS.offline;
    this.look = cloneLook(LOOKS.offline);
    this.levels = { mic: { value: 0, at: -Infinity }, tts: { value: 0, at: -Infinity } };
    this.level = 0;
    this.phase = Math.random() * 10;
    this.breathPhase = 0;
    this.spin = 0;
    this.width = 0;
    this.height = 0;
    this.dpr = 1;
    this.active = true;
    this.running = false;
    this.raf = 0;
    this.lastTime = 0;
    this.motion = 1;
    this.intro = 1; // 0 → 1 podczas rozkładania HUD
    this.introStart = 0;
    this.introMs = 0;
    this.timerSource = null; // (now) → {progress, elapsed, paused, ringing, editing} | null
    this.timerInfo = null;
    this.timerMix = 0; // 0 → 1 przy pojawieniu się minutnika

    this.cos = new Float32Array(POINTS);
    this.sin = new Float32Array(POINTS);
    for (let i = 0; i < POINTS; i++) {
      this.cos[i] = Math.cos((i / POINTS) * TAU);
      this.sin[i] = Math.sin((i / POINTS) * TAU);
    }
    this.px = new Float32Array(POINTS);
    this.py = new Float32Array(POINTS);
    this.particles = createParticles(34);

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    const applyMotion = () => {
      this.motion = reduced.matches ? 0.35 : 1;
    };
    applyMotion();
    onMediaChange(reduced, applyMotion);

    this._frame = this._frame.bind(this);
    document.addEventListener('visibilitychange', () => this._updateRunning());
    this._observeSize();
  }

  setState(state) {
    this.state = LOOKS[state] ? state : 'idle';
    this.target = LOOKS[this.state];
  }

  /** Pomiar poziomu dźwięku: source „mic” albo „tts”, level 0..1. */
  setLevel(source, level) {
    const slot = this.levels[source];
    if (!slot) return;
    const value = Number(level);
    slot.value = Number.isFinite(value) ? clamp(value, 0, 1) : 0;
    slot.at = performance.now();
  }

  /** Wstrzymuje animację, gdy kula nie jest widoczna (inny widok). */
  setActive(active) {
    this.active = Boolean(active);
    this._updateRunning();
  }

  /** Źródło stanu minutnika – wywoływane co klatkę; null = bez minutnika. */
  setTimer(source) {
    this.timerSource = typeof source === 'function' ? source : null;
  }

  /** Rozkłada HUD wokół kuli: segmenty zapalają się po kolei, skala rysuje się dookoła. */
  playIntro(ms = 1100) {
    if (this.motion < 1) return; // ograniczony ruch – bez pokazu
    this.intro = 0;
    this.introStart = performance.now();
    this.introMs = ms;
    this._draw(this.introStart);
  }

  _updateRunning() {
    const shouldRun = this.active && !document.hidden && this.width > 0 && this.height > 0 && Boolean(this.ctx);
    if (shouldRun && !this.running) {
      this.running = true;
      this.lastTime = performance.now();
      this.raf = requestAnimationFrame(this._frame);
    } else if (!shouldRun && this.running) {
      this.running = false;
      cancelAnimationFrame(this.raf);
    }
  }

  _observeSize() {
    const wrap = this.canvas.parentElement;
    const apply = () => {
      // rozmiar z układu strony, nie getBoundingClientRect – ten zmienia się przy animacji transform
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = wrap.clientWidth;
      const height = wrap.clientHeight;
      if (width === this.width && height === this.height && dpr === this.dpr) return;
      this.width = width;
      this.height = height;
      this.dpr = dpr;
      this.canvas.width = Math.max(1, Math.round(width * dpr));
      this.canvas.height = Math.max(1, Math.round(height * dpr));
      this.core?.resize(width, height, dpr);
      this._draw(performance.now());
      this._updateRunning();
    };
    if (typeof ResizeObserver === 'function') new ResizeObserver(apply).observe(wrap);
    window.addEventListener('resize', apply);
    apply();
  }

  _frame(now) {
    if (!this.running) return;
    this.raf = requestAnimationFrame(this._frame);
    const settled = this.timerInfo ? this.timerMix > 0.99 && !this.timerInfo.ringing : this.timerMix === 0;
    const calm =
      CALM_STATES.has(this.state) && this.level < 0.01 && this.look.swirl < 0.02 && this.intro >= 1 && settled;
    if (calm && now - this.lastTime < CALM_FRAME_MS - 2) return;
    const dt = Math.min(0.1, Math.max(0.001, (now - this.lastTime) / 1000));
    this.lastTime = now;
    this._step(dt, now);
    this._draw(now);
  }

  _step(dt, now) {
    const { look, target } = this;
    const k = 1 - Math.exp(-dt * 3.2);
    for (const key of NUMERIC_KEYS) look[key] += (target[key] - look[key]) * k;
    for (let i = 0; i < 3; i++) {
      look.core[i] += (target.core[i] - look.core[i]) * k;
      look.glow[i] += (target.glow[i] - look.glow[i]) * k;
    }

    const goal = this._levelTarget(now);
    const rate = goal > this.level ? ATTACK : RELEASE;
    this.level += (goal - this.level) * (1 - Math.pow(1 - rate, dt * 60));

    const m = this.motion;
    this.phase += dt * look.speed * (1 + this.level * 1.6) * m;
    this.breathPhase += dt * (1.1 + look.speed * 0.5) * m;
    this.spin += dt * (0.35 + look.swirl * 1.9) * m;
    const drift = dt * (1 + this.level * 3 + look.swirl * 2.5) * m;
    for (const p of this.particles) p.angle += p.speed * drift;
    if (this.intro < 1) this.intro = clamp((now - this.introStart) / this.introMs, 0, 1);

    const timer = this.timerSource ? this.timerSource(now) : null;
    if (timer) this.timerInfo = timer;
    this.timerMix += ((timer ? 1 : 0) - this.timerMix) * (1 - Math.exp(-dt * 4.5));
    if (!timer && this.timerMix < 0.003) {
      this.timerMix = 0;
      this.timerInfo = null;
    }
  }

  _levelTarget(now) {
    const source = LEVEL_SOURCE[this.state];
    if (!source) return 0;
    const slot = this.levels[source];
    const age = now - slot.at;
    if (age < LEVEL_TIMEOUT_MS) return Math.pow(slot.value, 0.75);
    if (source === 'tts' && age > SYNTHETIC_AFTER_MS) {
      const t = now / 1000;
      return 0.18 + 0.14 * Math.max(0, Math.sin(t * 7.3) * Math.sin(t * 3.1 + 1.2)) + 0.05 * Math.sin(t * 11.7);
    }
    return 0;
  }

  _draw(now) {
    const { ctx, width: w, height: h, look } = this;
    if (!ctx || !w || !h) return;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const cx = w / 2;
    const cy = h / 2;
    const base = Math.min(w, h) * 0.25;
    const m = this.motion;
    const lvl = this.level * look.react;
    const intro = easeOut(this.intro);
    const tm = this.timerMix;
    // koniec minutnika: kula pulsuje dwa razy na sekundę
    const pulse = this.timerInfo && this.timerInfo.ringing ? 0.5 + 0.5 * Math.sin(now * 0.0126) : 0;
    // przy rozkładaniu kula na moment rozbłyska
    const b = look.brightness * (1 + 0.55 * (1 - intro) * (1 - intro)) * (1 + pulse * 0.4 * tm);
    const radius = base * SPHERE * (1 + Math.sin(this.breathPhase) * look.breath + lvl * 0.2 * m);
    const amp = base * (look.deform + lvl * 0.12) * m;
    const haloR = base * (2.3 + lvl * 0.6);
    const compact = base < 40; // kulka na pulpicie – mniej drobiazgów

    if (this.core && !this.core.lost) {
      this.core.draw({
        cx, cy, radius, amp,
        time: this.phase,
        level: lvl,
        brightness: b,
        swirl: look.swirl,
        halo: haloR / radius,
        core: look.core,
        glow: look.glow,
        hollow: tm * (0.9 - pulse * 0.45),
      });
    }

    ctx.globalCompositeOperation = 'lighter';
    if (!this.core || this.core.lost) this._drawHalo(cx, cy, radius, haloR, b);
    this._drawReactor(cx, cy, base, lvl, b, intro, now, pulse);
    if (look.swirl > 0.02) this._drawArcs(cx, cy, base, look.swirl * b * intro);
    this._drawScale(cx, cy, base, lvl, b, intro, compact, pulse);
    this._drawRings(cx, cy, base, lvl, b, intro);
    this._drawParticles(cx, cy, base, lvl, b * intro, now, compact);
    if (!this.core || this.core.lost) this._drawBlob(cx, cy, radius, amp, lvl, b);
    ctx.globalCompositeOperation = 'source-over';
    if ((!this.core || this.core.lost) && tm > 0.01) this._drawLens(cx, cy, radius, tm);
  }

  _drawHalo(cx, cy, radius, haloR, b) {
    const { ctx, look } = this;
    const halo = ctx.createRadialGradient(cx, cy, radius * 0.5, cx, cy, haloR);
    halo.addColorStop(0, rgba(look.glow, 0.34 * b));
    halo.addColorStop(0.45, rgba(look.glow, 0.1 * b));
    halo.addColorStop(1, rgba(look.glow, 0));
    ctx.fillStyle = halo;
    ctx.beginPath();
    ctx.arc(cx, cy, haloR, 0, TAU);
    ctx.fill();
  }

  /**
   * Pierścień z dziesięciu cewek jak w reaktorze łukowym – świecą od głosu i od „myślenia”. Przy minutniku
   * cewki stają (w najbliższym ustawieniu od góry) i od góry, zgodnie z ruchem wskazówek zegara, świeci ich
   * tyle, ile zostało czasu; ostatnia zapalona – tylko w części.
   */
  _drawReactor(cx, cy, base, lvl, b, intro, now, pulse) {
    const { ctx, look, timerMix: tm, timerInfo: timer } = this;
    const inner = base * (1.08 + lvl * 0.16);
    const outer = inner + base * 0.14;
    const slot = TAU / SEGMENTS;
    const free = this.spin * 0.08 - Math.PI / 2;
    const k = Math.round((free + Math.PI / 2) / slot);
    const turn = free - (free + Math.PI / 2 - k * slot) * tm;
    const hot = mix(look.core, WHITE, 0.45);
    const progress = timer ? timer.progress : 0;
    let gauge = 0.85;
    if (!timer) gauge = 0;
    else if (timer.ringing) gauge = 0.25 + 0.75 * pulse;
    else if (timer.paused) gauge = 0.5 + 0.18 * Math.sin(now * 0.004);
    ctx.lineWidth = 1;
    for (let i = 0; i < SEGMENTS; i++) {
      // przy rozkładaniu cewki zapalają się po kolei, zgodnie z ruchem wskazówek zegara
      const appear = clamp((intro - (i / SEGMENTS) * 0.55) / 0.3, 0, 1);
      if (appear <= 0) continue;
      const a0 = turn + i * slot + SEGMENT_GAP / 2;
      const a1 = a0 + slot - SEGMENT_GAP;
      const mid = (a0 + a1) / 2;
      const shimmer = 0.1 * Math.pow(Math.max(0, Math.cos(mid - this.phase * 0.45)), 4);
      const voice = lvl * (0.55 + 0.45 * (0.5 + 0.5 * Math.sin(i * 2.1 + this.phase * 3.2)));
      const chase = look.swirl * 0.9 * Math.pow(Math.max(0, Math.cos(mid - this.spin * 2.4)), 8);
      const own = clamp(0.1 + shimmer + voice * 0.75 + chase, 0, 1);
      this._coil(cx, cy, inner, outer, a0, a1, (own * (1 - tm) + 0.05 * tm) * appear, hot, b, appear);
      if (tm < 0.001 || !timer) continue;
      const j = (((i + k) % SEGMENTS) + SEGMENTS) % SEGMENTS; // która to cewka, licząc od góry
      const fill = timer.ringing ? 1 : clamp(progress * SEGMENTS - j, 0, 1);
      if (fill > 0) this._coil(cx, cy, inner, outer, a0, a0 + (a1 - a0) * fill, gauge * tm * appear, hot, b, tm * appear);
    }
    // cienka obręcz wewnątrz cewek; przy minutniku – dokładny postęp z jasnym czołem
    const hoop = inner - base * 0.05;
    ctx.beginPath();
    ctx.arc(cx, cy, hoop, 0, TAU * intro);
    ctx.strokeStyle = rgba(look.core, 0.22 * b * (1 - 0.5 * tm));
    ctx.stroke();
    if (tm < 0.01 || !timer || timer.ringing || progress <= 0) return;
    const top = -Math.PI / 2;
    const end = top + progress * TAU;
    ctx.lineWidth = base < 40 ? 1.2 : 2;
    ctx.beginPath();
    ctx.arc(cx, cy, hoop, top, end);
    ctx.strokeStyle = rgba(hot, 0.85 * tm * b * (timer.paused ? 0.6 : 1));
    ctx.stroke();
    ctx.lineWidth = 1;
    const hx = cx + Math.cos(end) * hoop;
    const hy = cy + Math.sin(end) * hoop;
    const r = Math.max(4, base * 0.1);
    const head = ctx.createRadialGradient(hx, hy, 0, hx, hy, r);
    head.addColorStop(0, rgba(WHITE, 0.95 * tm * b));
    head.addColorStop(0.3, rgba(look.core, 0.55 * tm * b));
    head.addColorStop(1, rgba(look.core, 0));
    ctx.fillStyle = head;
    ctx.beginPath();
    ctx.arc(hx, hy, r, 0, TAU);
    ctx.fill();
  }

  _coil(cx, cy, inner, outer, a0, a1, lit, hot, b, edge) {
    const { ctx, look } = this;
    ctx.beginPath();
    ctx.arc(cx, cy, outer, a0, a1);
    ctx.arc(cx, cy, inner, a1, a0, true);
    ctx.closePath();
    ctx.fillStyle = rgba(mix(look.core, hot, lit), lit * 0.55 * b);
    ctx.fill();
    ctx.strokeStyle = rgba(look.core, clamp(0.18 + lit * 0.9, 0, 1) * b * edge);
    ctx.stroke();
  }

  _drawArcs(cx, cy, base, strength) {
    const { ctx, look } = this;
    ctx.lineCap = 'round';
    for (const arc of ARCS) {
      const start = this.spin * arc.speed + arc.offset;
      ctx.beginPath();
      ctx.arc(cx, cy, base * arc.radius, start, start + arc.length);
      ctx.lineWidth = arc.width;
      ctx.strokeStyle = rgba(look.core, arc.alpha * strength);
      ctx.stroke();
    }
    ctx.lineCap = 'butt';
  }

  /**
   * Skala z kreskami – przy dźwięku wydłużają się jak wskaźnik wysterowania. Przy minutniku skala staje
   * (długa kreska u góry), a po kreskach co sekundę przeskakuje jasny sekundnik ze smugą.
   */
  _drawScale(cx, cy, base, lvl, b, intro, compact, pulse) {
    const { ctx, look, timerMix: tm, timerInfo: timer } = this;
    const ticks = compact ? 60 : 120;
    const shown = Math.floor(ticks * intro); // przy rozkładaniu skala rysuje się dookoła
    const r0 = base * 1.58;
    const tick = TAU / ticks;
    const free = this.spin * 0.12;
    const rot = free - (free - Math.round(free / (tick * 10)) * tick * 10) * tm;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i < shown; i++) {
      const angle = i * tick + rot - Math.PI / 2;
      const wave = 0.5 + 0.5 * Math.sin(i * 0.55 + this.phase * 2.2);
      const len = (i % 10 === 0 ? 6 : 2.5) + lvl * 14 * wave * wave;
      const c = Math.cos(angle);
      const s = Math.sin(angle);
      ctx.moveTo(cx + c * r0, cy + s * r0);
      ctx.lineTo(cx + c * (r0 + len), cy + s * (r0 + len));
    }
    ctx.strokeStyle = rgba(look.core, (0.28 + 0.4 * pulse * tm) * b);
    ctx.stroke();

    if (tm < 0.01 || !timer || timer.elapsed == null || timer.ringing) return;
    // sekundnik liczy czas, który minął – idzie zgodnie z ruchem wskazówek i przeskakuje co sekundę
    const whole = Math.floor(timer.elapsed + 1e-6);
    const pos = whole - 1 + easeOut(clamp((timer.elapsed - whole) * 6, 0, 1));
    const hand = ((((pos % 60) + 60) % 60) / 60) * TAU;
    const hot = mix(look.core, WHITE, 0.6);
    const dim = timer.paused ? 0.5 : 1;
    for (let i = 0; i < shown; i++) {
      const behind = (((hand - i * tick) % TAU) + TAU) % TAU; // smuga za sekundnikiem
      const glow = behind < tick * 0.5 ? 1 : Math.exp(-behind * 7);
      if (glow < 0.04) continue;
      const angle = i * tick + rot - Math.PI / 2;
      const c = Math.cos(angle);
      const s = Math.sin(angle);
      const len = (i % 10 === 0 ? 6 : 2.5) + 5 * glow;
      ctx.beginPath();
      ctx.moveTo(cx + c * (r0 - 1), cy + s * (r0 - 1));
      ctx.lineTo(cx + c * (r0 + len), cy + s * (r0 + len));
      ctx.strokeStyle = rgba(hot, 0.95 * glow * tm * b * dim);
      ctx.stroke();
    }
  }

  _drawRings(cx, cy, base, lvl, b, intro) {
    const { ctx, look } = this;
    ctx.lineWidth = 1;
    const grow = 0.84 + 0.16 * intro;
    for (const [factor, alpha] of [[1.8, 0.1], [2.04, 0.055]]) {
      ctx.beginPath();
      ctx.arc(cx, cy, base * factor * grow * (1 + lvl * 0.04), 0, TAU);
      ctx.strokeStyle = rgba(look.core, alpha * b * intro);
      ctx.stroke();
    }
  }

  _drawParticles(cx, cy, base, lvl, b, now, compact) {
    const { ctx, look } = this;
    if (b <= 0.01) return;
    ctx.fillStyle = rgba(look.core, 1);
    const spread = 1 + lvl * 0.12;
    const list = compact ? this.particles.slice(0, 14) : this.particles;
    for (const p of list) {
      const r = base * p.radius * spread;
      const x = cx + Math.cos(p.angle) * r;
      const y = cy + Math.sin(p.angle) * r;
      ctx.globalAlpha = clamp((0.16 + 0.22 * (0.5 + 0.5 * Math.sin(now * 0.0017 + p.twinkle))) * b, 0, 1);
      ctx.fillRect(x - p.size / 2, y - p.size / 2, p.size, p.size);
    }
    ctx.globalAlpha = 1;
  }

  /** Ciemny środek pod cyframi minutnika – w 2D (z WebGL robi to shader). */
  _drawLens(cx, cy, radius, tm) {
    const { ctx } = this;
    const lens = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
    lens.addColorStop(0, rgba(DARK, 0.86 * tm));
    lens.addColorStop(0.55, rgba(DARK, 0.7 * tm));
    lens.addColorStop(1, rgba(DARK, 0));
    ctx.fillStyle = lens;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, TAU);
    ctx.fill();
  }

  /** Kula w 2D – tylko gdy nie ma WebGL. */
  _drawBlob(cx, cy, radius, amp, lvl, b) {
    const { ctx, look } = this;

    // zewnętrzna mgiełka
    this._blobPath(cx, cy, radius * 1.1, amp * 1.5, this.phase * 0.8 + 2.1, 1.7, lvl);
    ctx.fillStyle = rgba(look.glow, 0.2 * b);
    ctx.fill();

    // główna bryła
    this._blobPath(cx, cy, radius, amp, this.phase, 0, lvl);
    const body = ctx.createRadialGradient(cx - radius * 0.22, cy - radius * 0.28, radius * 0.05, cx, cy, radius * 1.08);
    body.addColorStop(0, rgba(mix(look.core, WHITE, 0.65), 0.9 * b));
    body.addColorStop(0.5, rgba(look.core, 0.5 * b));
    body.addColorStop(1, rgba(look.glow, 0.14 * b));
    ctx.fillStyle = body;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = rgba(look.core, 0.6 * b);
    ctx.stroke();

    // druga, przesunięta w fazie linia konturu – efekt „plazmy”
    this._blobPath(cx, cy, radius * 0.94, amp * 1.25, this.phase * 1.3 + 4.2, 3.1, lvl);
    ctx.lineWidth = 1;
    ctx.strokeStyle = rgba(mix(look.core, WHITE, 0.3), 0.3 * b);
    ctx.stroke();

    // jasne jądro
    const coreR = radius * (0.5 + lvl * 0.2);
    const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR);
    glow.addColorStop(0, rgba(WHITE, 0.55 * b));
    glow.addColorStop(1, rgba(WHITE, 0));
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(cx, cy, coreR, 0, TAU);
    ctx.fill();
  }

  /** Zamknięta, gładka ścieżka kuli: promień + suma sinusoid (całkowite harmoniczne → ciągłość). */
  _blobPath(cx, cy, radius, amp, phase, seed, lvl) {
    const { ctx, cos, sin, px, py } = this;
    const ripple = lvl * 0.3;
    for (let i = 0; i < POINTS; i++) {
      const t = (i / POINTS) * TAU;
      const d =
        0.5 * Math.sin(3 * t + phase * 1.3 + seed) +
        0.32 * Math.sin(5 * t - phase * 1.7 + seed * 2.1) +
        0.22 * Math.sin(7 * t + phase * 2.3 + seed * 0.7) +
        0.18 * Math.sin(2 * t - phase * 0.9 + seed * 1.3) +
        ripple * Math.sin(11 * t + phase * 4.1 + seed);
      const r = radius + amp * d;
      px[i] = cx + cos[i] * r;
      py[i] = cy + sin[i] * r;
    }
    ctx.beginPath();
    ctx.moveTo((px[POINTS - 1] + px[0]) / 2, (py[POINTS - 1] + py[0]) / 2);
    for (let i = 0; i < POINTS; i++) {
      const j = (i + 1) % POINTS;
      ctx.quadraticCurveTo(px[i], py[i], (px[i] + px[j]) / 2, (py[i] + py[j]) / 2);
    }
    ctx.closePath();
  }
}

function easeOut(t) {
  return 1 - Math.pow(1 - t, 3);
}

function cloneLook(src) {
  return { ...src, core: src.core.slice(), glow: src.glow.slice() };
}

function createParticles(count) {
  const list = [];
  for (let i = 0; i < count; i++) {
    list.push({
      angle: Math.random() * TAU,
      radius: 1.3 + Math.random() * 1,
      speed: (0.04 + Math.random() * 0.14) * (Math.random() < 0.5 ? -1 : 1),
      size: 0.7 + Math.random() * 1.3,
      twinkle: Math.random() * TAU,
    });
  }
  return list;
}

function mix(a, b, t) {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

function rgba(color, alpha) {
  const a = alpha <= 0 ? 0 : alpha >= 1 ? 1 : Math.round(alpha * 1000) / 1000;
  return `rgba(${color[0] | 0},${color[1] | 0},${color[2] | 0},${a})`;
}
