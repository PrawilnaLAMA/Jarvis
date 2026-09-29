// Rdzeń kuli rysowany na GPU (WebGL): plazma wewnątrz kuli, świecąca krawędź i poświata.
//
// Kula to dysk o promieniu odkształcanym tymi samymi sinusoidami co w wersji 2D, cieniowany jak
// sfera (z = √(1 − d²)). Wnętrze to szum fbm „przepływający” po powierzchni sfery, z jaśniejszymi
// żyłkami tam, gdzie szum przechodzi przez zero. Plazmę liczymy tylko wewnątrz kuli, a scissor
// ogranicza rysowanie do kwadratu poświaty – to wystarcza nawet na Raspberry Pi.
// Brak WebGL (albo błąd shadera) → create() zwraca null i kula rysuje się po staremu, w 2D.

const VERTEX = `
attribute vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }
`;

const FRAGMENT = `
precision PRECISION float;
uniform vec2 u_center;
uniform float u_radius;
uniform float u_amp;
uniform float u_time;
uniform float u_level;
uniform float u_bright;
uniform float u_swirl;
uniform float u_halo;
uniform float u_hollow;
uniform vec3 u_core;
uniform vec3 u_glow;

vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

// szum simplex 3D (Ashima Arts, licencja MIT)
float snoise(vec3 v) {
  const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod289(i);
  vec4 p = permute(permute(permute(i.z + vec4(0.0, i1.z, i2.z, 1.0)) + i.y + vec4(0.0, i1.y, i2.y, 1.0))
    + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
}

float fbm(vec3 p) {
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 3; i++) {
    v += a * snoise(p);
    p = p * 2.03 + vec3(17.1, 9.2, 4.7);
    a *= 0.5;
  }
  return v;
}

void main() {
  vec2 p = (gl_FragCoord.xy - u_center) / u_radius;
  float r = length(p);
  float ang = atan(p.y, p.x);
  float t = u_time;
  float wob = 0.5 * sin(3.0 * ang + t * 1.3) + 0.32 * sin(5.0 * ang - t * 1.7) + 0.22 * sin(7.0 * ang + t * 2.3)
    + 0.18 * sin(2.0 * ang - t * 0.9) + u_level * 0.3 * sin(11.0 * ang + t * 4.1);
  float edge = 1.0 + u_amp * wob;
  float d = r / edge;
  float aa = 1.6 / u_radius;
  vec3 white = vec3(1.0);
  vec3 col = vec3(0.0);

  // poświata na zewnątrz – wygasa do promienia u_halo
  float out_ = max(d - 1.0, 0.0) / max(u_halo - 1.0, 0.01);
  col += u_glow * (0.55 + u_level * 0.5) * exp(-out_ * 4.2) * (1.0 - smoothstep(0.7, 1.0, out_));
  // cienka świecąca krawędź kuli
  col += mix(u_core, white, 0.35) * exp(-abs(d - 1.0) * u_radius * 0.22) * 0.75;

  if (d < 1.0 + aa) {
    float z = sqrt(max(0.0, 1.0 - d * d));
    vec3 n = vec3(p / edge, z);
    // sfera powoli się obraca – wnętrze płynie w głąb, a nie tylko po płaskim dysku
    float rot = t * 0.07;
    n.xz = mat2(cos(rot), -sin(rot), sin(rot), cos(rot)) * n.xz;
    float flow = t * (0.1 + u_swirl * 0.2);
    vec3 q = n * 1.2;
    float warp = fbm(q * 0.9 + vec3(0.0, flow, flow * 0.5));
    float f = fbm(q + warp * (0.8 + u_swirl * 0.8) + vec3(flow * 0.3));
    // włókna z innego pola niż jasność – inaczej obrysowują plamy i kula wygląda jak mapa
    float vein = exp(-abs(warp + 0.15 * f) * (13.0 - u_level * 5.0));
    vec3 body = mix(u_glow, u_core, 0.6) * (0.5 + 0.32 * (0.5 + 0.5 * f));
    body += mix(u_core, white, 0.55) * vein * (0.26 + u_level * 0.5 + u_swirl * 0.15);
    body *= 0.5 + 0.5 * z;
    float rim = pow(1.0 - z, 2.2);
    body += u_core * rim * 1.1;
    body += mix(u_core, white, 0.7) * exp(-d * d * 4.2) * (0.5 + u_level * 0.7) * (1.0 - u_hollow);
    // minutnik: ciemna soczewka pod cyframi, plazma zostaje przy brzegu
    float lens = 1.0 - u_hollow * 0.94 * (1.0 - smoothstep(0.35, 1.0, d));
    body *= lens;
    float mask = 1.0 - smoothstep(1.0 - aa, 1.0 + aa, d);
    col = mix(col, body + col * 0.35 * lens, mask);
  }

  col *= u_bright;
  float alpha = clamp(max(col.r, max(col.g, col.b)), 0.0, 1.0);
  gl_FragColor = vec4(min(col, vec3(1.0)), alpha);
}
`;

const UNIFORMS = [
  'u_center', 'u_radius', 'u_amp', 'u_time', 'u_level', 'u_bright', 'u_swirl', 'u_halo', 'u_hollow', 'u_core', 'u_glow',
];

// Raspberry Pi (i inne słabe ARM-y): rdzeń w mniejszej rozdzielczości – plazma jest miękka, nie widać różnicy
const LOW_POWER = /aarch64|armv7|arm64/i.test(navigator.userAgent) && !/Windows|Mac/i.test(navigator.userAgent);

export class OrbCore {
  /** Kanwa WebGL pod `canvas` (2D) albo null, gdy się nie da. */
  static create(canvas) {
    try {
      const layer = document.createElement('canvas');
      layer.className = 'orb-core';
      layer.setAttribute('aria-hidden', 'true');
      // kolor z alfą = jasność: kula świeci na tło jak światło (rgb ≤ a, więc poprawne premultiplied)
      const gl = layer.getContext('webgl', { alpha: true, premultipliedAlpha: true, antialias: false, depth: false });
      if (!gl) return null;
      const core = new OrbCore(layer, gl);
      canvas.before(layer);
      return core;
    } catch (err) {
      console.warn('Kula bez WebGL:', err.message);
      return null;
    }
  }

  constructor(layer, gl) {
    this.layer = layer;
    this.gl = gl;
    this.scale = LOW_POWER ? 0.7 : 1;
    const high = gl.getShaderPrecisionFormat(gl.FRAGMENT_SHADER, gl.HIGH_FLOAT);
    const precision = high && high.precision > 0 ? 'highp' : 'mediump';
    const program = link(gl, VERTEX, FRAGMENT.replace('PRECISION', precision));
    gl.useProgram(program);
    this.loc = {};
    for (const name of UNIFORMS) this.loc[name] = gl.getUniformLocation(program, name);
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const pos = gl.getAttribLocation(program, 'a_pos');
    gl.enableVertexAttribArray(pos);
    gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);
    gl.enable(gl.SCISSOR_TEST);
    gl.clearColor(0, 0, 0, 0);
    layer.addEventListener('webglcontextlost', (event) => {
      event.preventDefault();
      this.lost = true;
    });
  }

  resize(width, height, dpr) {
    const k = dpr * this.scale;
    this.k = k;
    this.layer.width = Math.max(1, Math.round(width * k));
    this.layer.height = Math.max(1, Math.round(height * k));
    this.gl.viewport(0, 0, this.layer.width, this.layer.height);
  }

  /** Jedna klatka; wymiary w pikselach CSS (jak w 2D), kolory 0..255. */
  draw({ cx, cy, radius, amp, time, level, brightness, swirl, halo, hollow = 0, core, glow }) {
    const { gl, loc, k } = this;
    if (this.lost || !k) return;
    const h = this.layer.height;
    gl.scissor(0, 0, this.layer.width, h);
    gl.clear(gl.COLOR_BUFFER_BIT);
    const reach = radius * halo * 1.05;
    const x0 = Math.floor((cx - reach) * k);
    const y0 = Math.floor(h - (cy + reach) * k);
    const size = Math.ceil(reach * 2 * k);
    gl.scissor(Math.max(0, x0), Math.max(0, y0), size, size);
    gl.uniform2f(loc.u_center, cx * k, h - cy * k);
    gl.uniform1f(loc.u_radius, radius * k);
    gl.uniform1f(loc.u_amp, amp / radius);
    gl.uniform1f(loc.u_time, time);
    gl.uniform1f(loc.u_level, level);
    gl.uniform1f(loc.u_bright, brightness);
    gl.uniform1f(loc.u_swirl, swirl);
    gl.uniform1f(loc.u_halo, halo);
    gl.uniform1f(loc.u_hollow, hollow);
    gl.uniform3f(loc.u_core, core[0] / 255, core[1] / 255, core[2] / 255);
    gl.uniform3f(loc.u_glow, glow[0] / 255, glow[1] / 255, glow[2] / 255);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }
}

function link(gl, vertexSource, fragmentSource) {
  const program = gl.createProgram();
  for (const [type, source] of [[gl.VERTEX_SHADER, vertexSource], [gl.FRAGMENT_SHADER, fragmentSource]]) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) || 'shader');
    gl.attachShader(program, shader);
  }
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || 'link');
  return program;
}
