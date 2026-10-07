/* Blender AI Agent site: a small 3D engine, a simulated agent console, and the page wiring.
   Everything here is dependency-free. The 3D preview is drawn with the 2D canvas API. */
(() => {
'use strict';

/* ================================================================== utilities */
const TAU = Math.PI * 2;
const clamp = (v, a = 0, b = 1) => (v < a ? a : v > b ? b : v);
const lerp = (a, b, t) => a + (b - a) * t;
const smooth = (t) => t * t * (3 - 2 * t);
const mixc = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];

function rng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function hash3(x, y, z) {
  let h = (Math.imul(x | 0, 374761393) + Math.imul(y | 0, 668265263) + Math.imul(z | 0, 1274126177)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}
function vnoise(x, y, z = 0) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  const xf = smooth(x - xi), yf = smooth(y - yi), zf = smooth(z - zi);
  const h = (i, j, k) => hash3(xi + i, yi + j, zi + k);
  const x00 = lerp(h(0, 0, 0), h(1, 0, 0), xf), x10 = lerp(h(0, 1, 0), h(1, 1, 0), xf);
  const x01 = lerp(h(0, 0, 1), h(1, 0, 1), xf), x11 = lerp(h(0, 1, 1), h(1, 1, 1), xf);
  return lerp(lerp(x00, x10, yf), lerp(x01, x11, yf), zf);
}
function fbm(x, y, z = 0, oct = 4) {
  let a = 0.5, f = 1, s = 0, n = 0;
  for (let i = 0; i < oct; i++) { s += a * vnoise(x * f, y * f, z * f); n += a; a *= 0.5; f *= 2; }
  return s / n;
}
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const vlen = (a) => Math.hypot(a[0], a[1], a[2]);
const norm = (a) => { const l = vlen(a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };

/* Euler XYZ in degrees, applied as Z*Y*X like Blender */
function rotv(p, r) {
  if (!r || (!r[0] && !r[1] && !r[2])) return p;
  const rx = (r[0] * Math.PI) / 180, ry = (r[1] * Math.PI) / 180, rz = (r[2] * Math.PI) / 180;
  let [x, y, z] = p;
  let y1 = y * Math.cos(rx) - z * Math.sin(rx), z1 = y * Math.sin(rx) + z * Math.cos(rx); y = y1; z = z1;
  const x2 = x * Math.cos(ry) + z * Math.sin(ry), z2 = -x * Math.sin(ry) + z * Math.cos(ry); x = x2; z = z2;
  const x3 = x * Math.cos(rz) - y * Math.sin(rz), y3 = x * Math.sin(rz) + y * Math.cos(rz);
  return [x3, y3, z];
}

/* ================================================================== mesh */
class Mesh {
  constructor() {
    this.tris = [];
    this.objects = 0;
    this.shadows = [];
    this.lights = [];
    this.world = 'studio';
    this.fx = {};
    this.bounds = { zmin: 0, zmax: 1 };
  }
  add(a, b, c, mat, col, o = {}) {
    const t = {
      p: [a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]], mat, col,
      emit: o.emit || 0, tag: o.tag || 'base', sway: o.sway || 0, ph: o.ph || 0,
      alpha: o.alpha == null ? 1 : o.alpha, grp: o.grp || 0,
    };
    this.tris.push(t);
    return t;
  }
  finalize() {
    const keep = [];
    let zmin = Infinity, zmax = -Infinity;
    for (const t of this.tris) {
      const p = t.p;
      const e1 = [p[3] - p[0], p[4] - p[1], p[5] - p[2]], e2 = [p[6] - p[0], p[7] - p[1], p[8] - p[2]];
      const n = cross(e1, e2);
      const area = vlen(n) / 2;
      if (area < 1e-7) continue;
      t.n = [n[0] / (2 * area), n[1] / (2 * area), n[2] / (2 * area)];
      t.area = area;
      t.c = [(p[0] + p[3] + p[6]) / 3, (p[1] + p[4] + p[7]) / 3, (p[2] + p[5] + p[8]) / 3];
      t.nv = fbm(t.c[0] * 3.1 + 7, t.c[1] * 3.1 + 3, t.c[2] * 3.1, 3);
      zmin = Math.min(zmin, t.c[2]); zmax = Math.max(zmax, t.c[2]);
      keep.push(t);
    }
    const jr = rng(99);
    const span = Math.max(1e-3, zmax - zmin);
    for (const t of keep) t.ord = clamp(((t.c[2] - zmin) / span) * 0.8 + jr() * 0.2);
    this.tris = keep;
    this.bounds = { zmin, zmax };
    return this;
  }
}

function surface(m, f, nu, nv, o) {
  const g = [];
  for (let i = 0; i <= nu; i++) { const row = []; for (let j = 0; j <= nv; j++) row.push(f(i / nu, j / nv)); g.push(row); }
  const opt = { emit: o.emit, tag: o.tag, sway: o.sway, ph: o.ph, alpha: o.alpha, grp: o.grp };
  for (let i = 0; i < nu; i++) {
    for (let j = 0; j < nv; j++) {
      const col = o.colorFn ? o.colorFn((i + 0.5) / nu, (j + 0.5) / nv) : o.col;
      const mat = o.matFn ? o.matFn((i + 0.5) / nu, (j + 0.5) / nv) : o.mat;
      m.add(g[i][j], g[i + 1][j], g[i + 1][j + 1], mat, col, opt);
      m.add(g[i][j], g[i + 1][j + 1], g[i][j + 1], mat, col, opt);
    }
  }
}
function ellipsoid(m, c, r, o = {}) {
  const seg = o.seg || 12, rings = o.rings || 8, rot = o.rot, jit = o.jitter || 0, seed = o.seed || 1;
  const f = (u, v) => {
    const th = u * TAU, ph = v * Math.PI;
    let s = 1;
    if (jit) s = 1 + jit * (hash3(Math.round(u * seg) % seg, Math.round(v * rings), seed * 7) - 0.5) * 2;
    const q = rotv([Math.sin(ph) * Math.cos(th) * r[0] * s, Math.sin(ph) * Math.sin(th) * r[1] * s, -Math.cos(ph) * r[2] * s], rot);
    return [c[0] + q[0], c[1] + q[1], c[2] + q[2]];
  };
  surface(m, f, seg, rings, o);
  if (!o.part) m.objects++;
}
function cylinder(m, a, b, r0, r1, o = {}) {
  const seg = o.seg || 12, axis = sub(b, a), L = vlen(axis), w = norm(axis);
  const ref = Math.abs(w[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
  const u = norm(cross(w, ref)), v = cross(w, u);
  const pt = (th, t, rr) => [
    a[0] + w[0] * L * t + (u[0] * Math.cos(th) + v[0] * Math.sin(th)) * rr,
    a[1] + w[1] * L * t + (u[1] * Math.cos(th) + v[1] * Math.sin(th)) * rr,
    a[2] + w[2] * L * t + (u[2] * Math.cos(th) + v[2] * Math.sin(th)) * rr];
  const f = (uu, vv) => pt(uu * TAU, vv, lerp(r0, r1, vv) * (1 + (o.wobble || 0) * (hash3(Math.round(uu * seg) % seg, Math.round(vv * (o.rings || 1)), 5) - 0.5)));
  surface(m, f, seg, o.rings || 1, o);
  if (o.caps) {
    const opt = { emit: o.emit, tag: o.tag };
    for (let i = 0; i < seg; i++) {
      const t0 = (i / seg) * TAU, t1 = ((i + 1) / seg) * TAU;
      m.add(a, pt(t0, 0, r0), pt(t1, 0, r0), o.capMat || o.mat, o.capCol || o.col, opt);
      m.add(b, pt(t1, 1, r1), pt(t0, 1, r1), o.capMat || o.mat, o.capCol || o.col, opt);
    }
  }
  if (!o.part) m.objects++;
}
function lathe(m, prof, o = {}) {
  const seg = o.seg || 24, c = o.center || [0, 0, 0], rot = o.rot, sc = o.scale || [1, 1, 1], sub_ = o.sub || 1;
  const f = (u, v) => {
    const k = v * (prof.length - 1), i = Math.min(prof.length - 2, Math.floor(k)), t = k - i;
    const r = lerp(prof[i][0], prof[i + 1][0], t), z = lerp(prof[i][1], prof[i + 1][1], t), th = u * TAU;
    let p = [r * Math.cos(th) * sc[0], r * Math.sin(th) * sc[1], z * sc[2]];
    if (o.deform) p = o.deform(p);
    p = rotv(p, rot);
    return [c[0] + p[0], c[1] + p[1], c[2] + p[2]];
  };
  surface(m, f, seg, (prof.length - 1) * sub_, o);
  if (!o.part) m.objects++;
}
function box(m, c, s, o = {}) {
  const h = [s[0] / 2, s[1] / 2, s[2] / 2], rot = o.rot;
  const P = [];
  for (let i = 0; i < 8; i++) {
    const q = rotv([(i & 1 ? 1 : -1) * h[0], (i & 2 ? 1 : -1) * h[1], (i & 4 ? 1 : -1) * h[2]], rot);
    P.push([c[0] + q[0], c[1] + q[1], c[2] + q[2]]);
  }
  const faces = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]];
  const opt = { emit: o.emit, tag: o.tag, alpha: o.alpha };
  for (const f of faces) {
    m.add(P[f[0]], P[f[1]], P[f[2]], o.mat, o.col, opt);
    m.add(P[f[0]], P[f[2]], P[f[3]], o.mat, o.col, opt);
  }
  if (!o.part) m.objects++;
}
function torus(m, c, R, r, o = {}) {
  const rot = o.rot;
  const f = (u, v) => {
    const th = u * TAU, ph = v * TAU;
    const q = rotv([(R + r * Math.cos(ph)) * Math.cos(th), (R + r * Math.cos(ph)) * Math.sin(th), r * Math.sin(ph)], rot);
    return [c[0] + q[0], c[1] + q[1], c[2] + q[2]];
  };
  surface(m, f, o.seg || 20, o.tube || 6, o);
  if (!o.part) m.objects++;
}
function disc(m, r, o = {}) {
  const hf = o.height || (() => 0);
  surface(m, (u, v) => { const th = u * TAU, rr = v * r, x = rr * Math.cos(th), y = rr * Math.sin(th); return [x + (o.cx || 0), y + (o.cy || 0), hf(x, y, v) + (o.z || 0)]; },
    o.seg || 36, o.rings || 6, o);
  if (!o.part) m.objects++;
}

/* ================================================================== materials */
const MATS = {
  dirt: { shiny: 0, vary: 0.45 }, stone: { shiny: 0.1, vary: 0.5 }, wood: { shiny: 0.08, vary: 0.45 }, char: { shiny: 0.02, vary: 0.5 },
  ember: { shiny: 0, vary: 0.2 }, flame: { shiny: 0, vary: 0 }, ash: { shiny: 0, vary: 0.3 }, skin: { shiny: 0.18, vary: 0.05 },
  hair: { shiny: 0.45, vary: 0.12 }, cloth: { shiny: 0.05, vary: 0.2 }, paint: { shiny: 0.75, vary: 0.04 }, glass: { shiny: 0.95, vary: 0.02 },
  rubber: { shiny: 0.08, vary: 0.1 }, chrome: { shiny: 0.95, vary: 0.02 }, metal: { shiny: 0.8, vary: 0.12 }, snow: { shiny: 0.12, vary: 0.1 },
  water: { shiny: 0.9, vary: 0.05 }, grass: { shiny: 0, vary: 0.4 }, rock: { shiny: 0.05, vary: 0.5 }, floor: { shiny: 0.2, vary: 0.05 },
  plaster: { shiny: 0.05, vary: 0.1 }, fabric: { shiny: 0.06, vary: 0.2 }, lamp: { shiny: 0.3, vary: 0 }, leaf: { shiny: 0.15, vary: 0.4 },
  screen: { shiny: 0.9, vary: 0 }, cloth: { shiny: 0.05, vary: 0.15 },
};

/* ================================================================== scenes */
function flame(m, base, h, w, twist, col, o = {}) {
  const ph = o.ph || 0;
  surface(m, (u, v) => {
    const th = u * TAU + twist * v;
    const taper = Math.pow(1 - v, 0.65), bulge = 1 + 0.35 * Math.sin(v * Math.PI * 0.9), wob = 1 + 0.18 * Math.sin(u * TAU * 3 + v * 5) * v;
    const r = w * taper * bulge * wob + 0.012, lean = 0.12 * Math.sin(v * 2.2 + ph) * v * h * 0.35;
    return [base[0] + r * Math.cos(th) + lean, base[1] + r * Math.sin(th), base[2] + v * h];
  }, o.seg || 14, o.rings || 10, { mat: 'flame', col, emit: o.emit == null ? 1 : o.emit, sway: o.sway == null ? 0.1 : o.sway, ph, tag: o.tag || 'base', alpha: o.alpha });
  m.objects++;
}

function buildCampfire() {
  const m = new Mesh(), R = rng(14);
  m.world = 'night';
  disc(m, 4.4, { seg: 30, rings: 8, mat: 'dirt', col: [0.22, 0.15, 0.1], z: -0.02, height: (x, y, v) => (fbm(x * 0.7, y * 0.7, 0) - 0.5) * 0.2 * smooth(v) });
  m.fade = { from: 1.6, to: 4.3, mats: ['dirt'], color: [0.01, 0.012, 0.018] };
  for (let i = 0; i < 14; i++) {
    const a = (i / 14) * TAU + R() * 0.15, rad = 1.5 + R() * 0.22, x = Math.cos(a) * rad, y = Math.sin(a) * rad;
    const rx = 0.34 + R() * 0.16, ry = 0.28 + R() * 0.12;
    ellipsoid(m, [x, y, 0.12], [rx, ry, 0.18 + R() * 0.1], { seg: 6, rings: 4, mat: 'stone', col: [0.55, 0.52, 0.48], rot: [R() * 24 - 12, R() * 24 - 12, a * 57.3], jitter: 0.14, seed: i + 1 });
    m.shadows.push({ x, y, rx: rx * 1.5, ry: ry * 1.5, a: 0.55 });
  }
  const layout = [[32, 0.27], [-32, 0.3], [78, 0.58], [-75, 0.6]];
  layout.forEach(([deg, lift], k) => {
    const ang = (deg * Math.PI) / 180, d = [Math.cos(ang), Math.sin(ang), 0], len = k > 1 ? 0.95 : 1.15;
    const a = [-d[0] * len, -d[1] * len, lift], b = [d[0] * len, d[1] * len, lift + 0.06];
    cylinder(m, a, b, 0.2, 0.19, {
      seg: 9, rings: 5, mat: 'wood', caps: true, capMat: 'char', capCol: [0.07, 0.045, 0.03], wobble: 0.08,
      colorFn: (u, v) => (v < 0.1 || v > 0.9 ? [0.13, 0.08, 0.05] : mixc([0.46, 0.25, 0.13], [0.12, 0.07, 0.045], fbm(u * 6, v * 3, k) > 0.64 ? 0.85 : 0.08)),
    });
    m.shadows.push({ x: 0, y: 0, rx: len * 0.95, ry: 0.36, a: 0.5, rot: ang });
  });
  for (let i = 0; i < 28; i++) {
    const a = R() * TAU, rad = Math.sqrt(R()) * 0.85, hot = R() < 0.72;
    ellipsoid(m, [Math.cos(a) * rad, Math.sin(a) * rad, 0.06 + R() * 0.2], [0.07 + R() * 0.07, 0.07 + R() * 0.06, 0.05 + R() * 0.04],
      { seg: 5, rings: 3, mat: hot ? 'ember' : 'char', col: hot ? [1, 0.25 + R() * 0.2, 0.03] : [0.08, 0.05, 0.04], emit: hot ? 0.5 + R() * 0.5 : 0, tag: 'detail', seed: i + 30 });
  }
  for (let i = 0; i < 18; i++) {
    const a = R() * TAU, rad = 0.65 + R() * 0.7;
    ellipsoid(m, [Math.cos(a) * rad, Math.sin(a) * rad, 0.02], [0.08 + R() * 0.1, 0.06 + R() * 0.08, 0.025], { seg: 5, rings: 2, mat: 'ash', col: [0.5, 0.48, 0.45], tag: 'detail', seed: i + 70 });
  }
  flame(m, [0, 0, 0.38], 2.2, 0.5, 1.0, [1, 0.3, 0.05], { ph: 0.4, alpha: 0.85 });
  flame(m, [0.04, -0.02, 0.4], 1.7, 0.34, -0.8, [1, 0.55, 0.1], { ph: 1.3 });
  flame(m, [0, 0, 0.42], 1.1, 0.2, 0.5, [1, 0.88, 0.45], { ph: 2.1, emit: 1.3 });
  flame(m, [0, 0, 0.4], 0.55, 0.26, 0.2, [0.3, 0.5, 1], { ph: 3, emit: 0.7, sway: 0.04 });
  for (let i = 0; i < 9; i++) {
    const a = (i / 9) * TAU + R() * 0.5, rad = 0.22 + R() * 0.38;
    flame(m, [Math.cos(a) * rad, Math.sin(a) * rad, 0.4], 0.8 + R() * 0.95, 0.12 + R() * 0.09, R() * 3 - 1.5, R() < 0.65 ? [1, 0.3, 0.05] : [1, 0.58, 0.12], { ph: R() * 6, tag: 'detail', seg: 8, rings: 6 });
  }
  m.lights.push({ p: [0, 0, 1.0], c: [1, 0.42, 0.1], k: 2.3, pool: 3.6, flicker: true });
  m.fx = { smoke: true, sparks: true };
  return m.finalize();
}

function buildMountains() {
  const m = new Mesh();
  m.world = 'sky';
  const RAD = 4.6;
  const H = (x, y) => {
    const r = Math.hypot(x, y) / RAD;
    const ridge = 1 - Math.abs(2 * fbm(x * 0.5 + 3, y * 0.5 + 1, 0, 5) - 1);
    const h = Math.pow(ridge, 2.1) * 3.2 + fbm(x * 0.9, y * 0.9, 2, 3) * 0.7;
    return h * (1 - smooth(clamp((r - 0.3) / 0.7))) + 0.05;
  };
  surface(m, (u, v) => { const th = u * TAU, r = v * RAD, x = r * Math.cos(th), y = r * Math.sin(th); return [x, y, H(x, y)]; }, 44, 20, {
    mat: 'rock',
    colorFn: (u, v) => {
      const th = u * TAU, r = v * RAD, x = r * Math.cos(th), y = r * Math.sin(th), h = H(x, y), s = Math.abs(H(x + 0.2, y) - h) + Math.abs(H(x, y + 0.2) - h);
      if (h > 2.3 && s < 0.9) return [0.95, 0.96, 1];
      if (h > 1.3) return mixc([0.44, 0.4, 0.37], [0.34, 0.31, 0.3], clamp(s));
      return mixc([0.24, 0.42, 0.18], [0.42, 0.37, 0.3], clamp(s * 0.8));
    },
  });
  m.objects += 1;
  disc(m, 9, { seg: 40, rings: 8, mat: 'water', col: [0.1, 0.3, 0.5], z: 0.34 });
  m.fade = { from: 3.5, to: 9, mats: ['water'], color: [0.87, 0.91, 0.95] };
  m.lights.push({ p: [-4, -5, 6], c: [1, 0.96, 0.9], k: 1 });
  return m.finalize();
}

/* Flat grid surface: p0 + u * a + v * b. Used for floors and walls so painter's sorting stays correct (many small triangles). */
function plane(m, p0, a, b, nu, nv, mat, colorFn, o = {}) {
  surface(m, (u, v) => [p0[0] + a[0] * u + b[0] * v, p0[1] + a[1] * u + b[1] * v, p0[2] + a[2] * u + b[2] * v], nu, nv, Object.assign({ mat, colorFn }, o));
  if (!o.part) m.objects++;
}

/* Modern living room, cut away at the front. variant 1 = first try (sofa floats, no lights), 2 = grounded but dark, 3 = finished. */
function buildRoom(variant = 3) {
  const m = new Mesh(), R = rng(31);
  m.world = 'interior';
  const HX = 3.3, HY = 2.4, H = 3.0, lift = variant === 1 ? 0.26 : 0, lit = variant >= 3;
  const dark = [0.13, 0.14, 0.17], warm = [1.0, 0.7, 0.36];
  /* floor planks run front to back, each plank has its own tone */
  const plank = []; for (let i = 0; i < 16; i++) plank.push(mixc([0.4, 0.25, 0.14], [0.58, 0.39, 0.21], R()));
  plane(m, [-HX, -HY, 0], [2 * HX, 0, 0], [0, 2 * HY, 0], 16, 12, 'floor', (u) => plank[Math.min(15, Math.floor(u * 16))]);
  /* walls: dark back wall, light side walls */
  plane(m, [-HX, HY, 0], [2 * HX, 0, 0], [0, 0, H], 14, 6, 'plaster', () => dark);
  plane(m, [-HX, -HY, 0], [0, 2 * HY, 0], [0, 0, H], 10, 6, 'plaster', () => [0.84, 0.82, 0.78]);
  plane(m, [HX, -HY, 0], [0, 2 * HY, 0], [0, 0, H], 10, 6, 'plaster', () => [0.62, 0.62, 0.64]);
  /* cut edges so the room reads as a model */
  box(m, [0, -HY, 0.03], [2 * HX + 0.2, 0.1, 0.06], { mat: 'plaster', col: [0.08, 0.08, 0.09], part: true });
  for (const sx of [-1, 1]) box(m, [sx * HX, -HY, H / 2], [0.12, 0.1, H], { mat: 'plaster', col: [0.08, 0.08, 0.09], part: true });
  /* back wall: TV panel and wooden slats on both sides */
  box(m, [0, HY - 0.05, 1.5], [2.6, 0.05, 1.25], { mat: 'screen', col: [0.03, 0.04, 0.06], emit: lit ? 0.18 : 0 });
  for (const s of [-1, 1]) for (let i = 0; i < 7; i++)
    box(m, [s * (1.75 + i * 0.12), HY - 0.04, 1.4], [0.07, 0.05, 2.7], { mat: 'wood', col: mixc([0.4, 0.22, 0.1], [0.62, 0.38, 0.18], (i % 2) * 0.6 + R() * 0.3), part: true });
  m.objects += 2;
  /* floating ceiling panel with a warm LED strip, downlights and pendant lamps */
  box(m, [0, 0.1, 2.82], [5.0, 3.3, 0.14], { mat: 'plaster', col: [0.1, 0.1, 0.12] });
  const led = lit ? warm : [0.3, 0.26, 0.22];
  for (const [c, sz] of [[[0, -1.5, 2.72], [4.8, 0.04, 0.04]], [[0, 1.7, 2.72], [4.8, 0.04, 0.04]], [[-2.4, 0.1, 2.72], [0.04, 3.2, 0.04]], [[2.4, 0.1, 2.72], [0.04, 3.2, 0.04]]])
    box(m, c, sz, { mat: 'lamp', col: led, emit: lit ? 1.6 : 0, part: true });
  for (let i = 0; i < 6; i++) cylinder(m, [-1.6 + (i % 3) * 1.6, -0.5 + Math.floor(i / 3) * 1.7, 2.745], [-1.6 + (i % 3) * 1.6, -0.5 + Math.floor(i / 3) * 1.7, 2.7], 0.07, 0.07, { seg: 8, mat: 'lamp', col: warm, emit: lit ? 1.4 : 0, caps: true, part: true });
  m.objects += 2;
  if (variant >= 2) for (const px of [-0.95, 0, 0.95]) {
    cylinder(m, [px, 1.15, 1.95], [px, 1.15, 2.75], 0.008, 0.008, { seg: 5, mat: 'metal', col: [0.02, 0.02, 0.02], part: true });
    ellipsoid(m, [px, 1.15, 1.8], [0.17, 0.17, 0.17], { seg: 12, rings: 8, mat: 'lamp', col: warm, emit: lit ? 1.3 : 0 });
  }
  /* bookshelf on the left wall */
  const SX = -HX + 0.2, SY = 0.95, SW = 2.1;
  for (const s of [-1, 1]) box(m, [SX, SY + s * SW / 2, 1.25], [0.34, 0.04, 2.5], { mat: 'wood', col: [0.3, 0.19, 0.1], part: true });
  for (let i = 0; i < 6; i++) box(m, [SX, SY, 0.08 + i * 0.5], [0.34, SW, 0.04], { mat: 'wood', col: [0.34, 0.21, 0.11], part: true });
  m.objects += 2;
  for (let i = 0; i < 4; i++) {
    let y = SY - SW / 2 + 0.08;
    while (y < SY + SW / 2 - 0.14) {
      const th = 0.03 + R() * 0.045, hh = 0.2 + R() * 0.2;
      if (R() < 0.22) { y += 0.2; continue; }
      box(m, [SX, y + th / 2, 0.1 + i * 0.5 + hh / 2], [0.22, th, hh], { mat: 'cloth', col: mixc([0.7, 0.2, 0.16], [0.2, 0.5, 0.68], R()), tag: 'detail', part: true });
      y += th + 0.005;
    }
  }
  /* plants */
  const plant = (x, y, tall, col, n) => {
    cylinder(m, [x, y, 0], [x, y, 0.42], 0.23, 0.19, { seg: 12, mat: 'rock', col: [0.12, 0.12, 0.13], caps: true });
    cylinder(m, [x, y, 0.4], [x, y, 0.4 + tall * 0.6], 0.02, 0.012, { seg: 5, mat: 'wood', col: [0.2, 0.14, 0.08], part: true });
    for (let i = 0; i < n; i++) {
      const a = (i / n) * TAU + R(), h = 0.5 + (i / n) * tall * 0.9;
      ellipsoid(m, [x + Math.cos(a) * 0.17, y + Math.sin(a) * 0.17, h], [0.09, 0.27, 0.025], { seg: 6, rings: 4, mat: 'leaf', col, rot: [-35 - R() * 20, 0, (a * 180) / Math.PI - 90], part: true });
    }
  };
  if (variant >= 2) { plant(-2.75, -1.55, 1.6, [0.05, 0.22, 0.08], 14); plant(2.55, 1.5, 1.2, [0.2, 0.5, 0.18], 10); }
  /* rug, sofa (back to the viewer), coffee table */
  box(m, [0, 0.45, 0.012], [3.9, 2.7, 0.024], { mat: 'fabric', col: [0.36, 0.34, 0.31] });
  const L = lift;
  box(m, [-0.1, 0.3, 0.3 + L], [2.75, 0.96, 0.38], { mat: 'fabric', col: [0.1, 0.1, 0.12], part: true });
  box(m, [-0.1, -0.05, 0.74 + L], [2.75, 0.26, 0.62], { mat: 'fabric', col: [0.11, 0.11, 0.13], part: true });
  for (const s of [-1, 1]) box(m, [-0.1 + s * 1.25, 0.3, 0.6 + L], [0.26, 0.96, 0.56], { mat: 'fabric', col: [0.12, 0.12, 0.14], part: true });
  for (const x of [-0.9, 0, 0.9]) box(m, [-0.1 + x, 0.4, 0.55 + L], [0.86, 0.72, 0.14], { mat: 'fabric', col: [0.14, 0.14, 0.16], part: true });
  box(m, [-0.55, 0.28, 0.82 + L], [0.4, 0.12, 0.38], { mat: 'fabric', col: [0.55, 0.3, 0.12], rot: [-12, 0, 12], part: true });
  m.objects += 3;
  box(m, [-0.1, 1.25, 0.38], [1.3, 0.62, 0.05], { mat: 'wood', col: [0.5, 0.33, 0.18], part: true });
  for (const [x, y] of [[-0.6, 1.0], [0.4, 1.0], [-0.6, 1.5], [0.4, 1.5]]) box(m, [x, y, 0.18], [0.05, 0.05, 0.36], { mat: 'metal', col: [0.1, 0.1, 0.11], part: true });
  m.objects += 1;
  /* desk, monitor, chair, floor lamp on the right */
  if (variant >= 2) {
    box(m, [2.15, -0.35, 0.76], [1.9, 0.78, 0.05], { mat: 'wood', col: [0.82, 0.78, 0.7], part: true });
    for (const [x, y] of [[1.25, -0.7], [3.05, -0.7], [1.25, -0.0], [3.05, -0.0]]) box(m, [x, y, 0.37], [0.05, 0.05, 0.74], { mat: 'metal', col: [0.08, 0.08, 0.09], part: true });
    m.objects += 2;
  }
  if (variant >= 3) {
    box(m, [2.15, -0.18, 1.17], [0.74, 0.03, 0.44], { mat: 'screen', col: [0.04, 0.05, 0.08], emit: 0.22 });
    box(m, [2.15, -0.2, 0.9], [0.05, 0.05, 0.28], { mat: 'metal', col: [0.05, 0.05, 0.06], part: true });
    box(m, [2.15, -0.45, 0.8], [0.42, 0.14, 0.02], { mat: 'metal', col: [0.06, 0.06, 0.07], part: true });
    box(m, [2.0, -1.15, 0.5], [0.52, 0.52, 0.1], { mat: 'cloth', col: [0.06, 0.06, 0.07] });
    box(m, [2.0, -1.4, 0.88], [0.5, 0.08, 0.66], { mat: 'cloth', col: [0.06, 0.06, 0.07], part: true });
    cylinder(m, [2.0, -1.15, 0.05], [2.0, -1.15, 0.46], 0.03, 0.03, { seg: 6, mat: 'metal', col: [0.05, 0.05, 0.06], part: true });
    cylinder(m, [2.0, -1.15, 0.03], [2.0, -1.15, 0.06], 0.3, 0.3, { seg: 10, mat: 'metal', col: [0.05, 0.05, 0.06], caps: true, part: true });
    cylinder(m, [1.05, -0.8, 0], [1.05, -0.8, 1.5], 0.016, 0.016, { seg: 5, mat: 'metal', col: [0.75, 0.55, 0.22] });
    ellipsoid(m, [1.05, -0.8, 1.6], [0.19, 0.19, 0.15], { seg: 12, rings: 8, mat: 'lamp', col: warm, emit: 1.2 });
  }
  /* dark curtains along the right wall */
  if (variant >= 2) for (let i = 0; i < 5; i++) box(m, [HX - 0.14, -1.9 + i * 0.52 + 0.9, 1.45], [0.09, 0.5, 2.9], { mat: 'cloth', col: mixc([0.07, 0.07, 0.08], [0.14, 0.14, 0.16], R()), part: true });
  m.objects += 1;
  /* contact shadows */
  m.shadows.push({ x: -0.1, y: 0.3, rx: 1.7, ry: 0.85, a: 0.6 }, { x: -0.1, y: 1.25, rx: 0.8, ry: 0.45, a: 0.4 });
  if (variant >= 2) m.shadows.push({ x: 2.15, y: -0.35, rx: 1.1, ry: 0.6, a: 0.45 }, { x: -2.75, y: -1.55, rx: 0.4, ry: 0.4, a: 0.5 }, { x: 2.55, y: 1.5, rx: 0.35, ry: 0.35, a: 0.5 });
  /* lights: the finished room gets warm pendants, a LED strip and a cool glow from the TV */
  if (variant === 1) m.lights.push({ p: [0, -1, 2.4], c: [0.6, 0.7, 1.0], k: 0.55 });
  else if (variant === 2) m.lights.push({ p: [0, 0.2, 2.5], c: [1.0, 0.8, 0.5], k: 0.7 });
  else m.lights.push({ p: [0, 0.2, 2.55], c: [1.0, 0.76, 0.42], k: 2.4 }, { p: [0, 1.1, 1.8], c: [1.0, 0.7, 0.35], k: 1.2 }, { p: [1.05, -0.8, 1.55], c: [1.0, 0.72, 0.4], k: 1.0 }, { p: [-2.3, 0.95, 1.5], c: [1.0, 0.72, 0.4], k: 0.9 }, { p: [0, 2.0, 1.4], c: [0.45, 0.6, 1.0], k: 0.6 });
  m.scanR = 3.6;
  return m.finalize();
}

/* Spiral galaxy: thousands of star points on two arms, a warm bulge, a ringed planet and a moon. */
function buildGalaxy() {
  const m = new Mesh(), R = rng(21), pts = [];
  m.world = 'space'; m.scanMode = 'radial'; m.scanR = 4.9; m.spin = 0.05;
  const gauss = () => { let s = 0; for (let i = 0; i < 4; i++) s += R(); return (s - 2) / 0.58; };
  const star = (x, y, z, size, col, a, ord) => pts.push({ x, y, z, size, col, a, ord });
  for (let k = 0; k < 2; k++) for (let i = 0; i < 1700; i++) {
    const t = Math.pow(R(), 0.85), th = t * 3.1 * Math.PI + k * Math.PI, r = 0.5 + t * 4.1, sp = 0.05 + 0.15 * t, hot = R() < 0.035;
    const x = r * Math.cos(th) + gauss() * sp, y = r * Math.sin(th) + gauss() * sp, z = gauss() * (0.03 + 0.05 * (1 - t));
    star(x, y, z, hot ? 0.034 : 0.009 + R() * 0.012, hot ? [1, 1, 1] : mixc([1, 0.82, 0.5], [0.45, 0.62, 1], clamp(t * 1.15)), hot ? 1 : 0.5 + R() * 0.45, Math.hypot(x, y) / 4.9);
  }
  for (let i = 0; i < 700; i++) {
    const rr = Math.abs(gauss()) * 0.42, a = R() * TAU, b = Math.acos(2 * R() - 1);
    star(rr * Math.sin(b) * Math.cos(a), rr * Math.sin(b) * Math.sin(a), rr * Math.cos(b) * 0.55, 0.011 + R() * 0.012, mixc([1, 0.9, 0.62], [1, 0.7, 0.35], R()), 0.7 + 0.3 * R(), rr / 4.9);
  }
  for (let i = 0; i < 260; i++) {
    const rr = 1 + R() * 4.5, a = R() * TAU, b = Math.acos(2 * R() - 1);
    star(rr * Math.sin(b) * Math.cos(a), rr * Math.sin(b) * Math.sin(a), rr * Math.cos(b) * 0.5, 0.008, [0.7, 0.75, 1], 0.25, rr / 6);
  }
  for (let i = 0; i < 520; i++) {
    const rr = 11 + R() * 6, a = R() * TAU, b = Math.acos(2 * R() - 1);
    star(rr * Math.sin(b) * Math.cos(a), rr * Math.sin(b) * Math.sin(a), rr * Math.cos(b), 0.012 + R() * 0.022, R() < 0.2 ? [1, 0.8, 0.6] : R() < 0.5 ? [0.7, 0.8, 1] : [1, 1, 1], 0.35 + R() * 0.5, 0.4 + R() * 0.6);
  }
  const map = new Map(); m.buckets = [];
  for (const p of pts) {
    const q = p.col.map((v) => Math.round(clamp(v) * 6) / 6), key = q.join(',');
    let b = map.get(key);
    if (!b) { b = { col: q, pts: [] }; map.set(key, b); m.buckets.push(b); }
    b.pts.push(p);
  }
  m.points = pts;
  const PC = [3.5, -2.2, 0.9];
  ellipsoid(m, PC, [0.7, 0.7, 0.7], { seg: 20, rings: 14, mat: 'rock', colorFn: (u, v) => mixc([0.62, 0.36, 0.2], [0.98, 0.76, 0.5], 0.5 + 0.5 * Math.sin(v * 18 + Math.sin(u * 6) * 0.5)) });
  surface(m, (u, v) => { const th = u * TAU, r = 0.98 + v * 0.62, q = rotv([r * Math.cos(th), r * Math.sin(th), 0], [18, 0, 12]); return [PC[0] + q[0], PC[1] + q[1], PC[2] + q[2]]; }, 36, 3, { mat: 'ash', col: [0.95, 0.86, 0.7], alpha: 0.8 });
  m.objects++;
  ellipsoid(m, [2.3, -3.0, 1.2], [0.15, 0.15, 0.15], { seg: 10, rings: 7, mat: 'rock', col: [0.6, 0.6, 0.64] });
  m.objects++;
  m.lights.push({ p: [0, 0, 0.3], c: [1, 0.82, 0.58], k: 16 });
  m.fx = { core: true, nebula: true };
  return m.finalize();
}

const SCENES = {
  campfire: { label: 'Campfire', build: () => buildCampfire(), cam: { yaw: -0.55, pitch: 0.36, dist: 8.2, target: [0, 0, 1.15] }, aria: 'A campfire with stones, logs, glowing coals and flames' },
  room: { label: 'Room design', build: (v) => buildRoom(v || 3), cam: { yaw: 0.22, pitch: 0.12, dist: 6.6, target: [0, 0.3, 1.25] }, portraitZoom: 1.15,
    aria: 'A modern living room with a floating ceiling light, pendant lamps, wooden slat panels, a sofa, a bookshelf and a desk' },
  galaxy: { label: 'Galaxy space', build: () => buildGalaxy(), cam: { yaw: -0.3, pitch: 0.6, dist: 9.4, target: [0.5, -0.3, 0.1] }, portraitZoom: 1.25, aria: 'A spiral galaxy with a bright core, a ringed planet and a moon' },
  mountains: { label: 'Mountains', build: () => buildMountains(), cam: { yaw: -0.6, pitch: 0.42, dist: 11.5, target: [0, 0, 0.9] }, aria: 'A mountain range with snowy peaks and a lake' },
};

const scenesCache = new Map();
function getScene(key, variant) {
  const id = key + ':' + (variant || '');
  if (!scenesCache.has(id)) scenesCache.set(id, SCENES[key].build(variant));
  return scenesCache.get(id);
}

/* ================================================================== renderer */
const KEY_DIR = norm([-0.45, -0.55, 0.75]);
const WORLDS = {
  night: { top: '#04060b', mid: '#0a111d', bot: '#0b0e15', amb: [0.075, 0.095, 0.15], rim: { d: norm([0.5, 0.6, 0.45]), c: [0.14, 0.2, 0.34] } },
  studio: { top: '#5d616b', mid: '#43464d', bot: '#2b2d32', amb: [0.34, 0.35, 0.39], rim: { d: norm([0.6, 0.5, 0.35]), c: [0.2, 0.26, 0.38] } },
  sky: { top: '#6f98c6', mid: '#a9c4de', bot: '#dfe9f1', amb: [0.4, 0.44, 0.52], rim: { d: norm([0.6, 0.5, 0.35]), c: [0.2, 0.24, 0.3] } },
  interior: { top: '#06080d', mid: '#0b0e15', bot: '#07090e', amb: [0.095, 0.105, 0.135], rim: { d: norm([0.3, 0.7, 0.4]), c: [0.06, 0.08, 0.14] }, gain: 1.5 },
  space: { top: '#000004', mid: '#02030b', bot: '#000003', amb: [0.05, 0.05, 0.09], rim: { d: norm([0.5, 0.6, 0.4]), c: [0.05, 0.06, 0.12] }, gain: 1.0 },
};
const rgbs = (c, a) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;

function cameraPos(cam) {
  const cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
  return [cam.target[0] - cam.dist * cp * Math.sin(cam.yaw), cam.target[1] - cam.dist * cp * Math.cos(cam.yaw), cam.target[2] + cam.dist * sp];
}
function makeProjector(cam, W, H, cx, cy, focal) {
  const cyw = Math.cos(cam.yaw), syw = Math.sin(cam.yaw), cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch), t = cam.target, D = cam.dist;
  return (x, y, z) => {
    x -= t[0]; y -= t[1]; z -= t[2];
    const x1 = x * cyw - y * syw, y1 = x * syw + y * cyw, y2 = y1 * cp - z * sp, z2 = y1 * sp + z * cp, d = y2 + D;
    return [cx + (focal * x1) / d, cy - (focal * z2) / d, d];
  };
}

function drawBackground(ctx, W, H, mode, scene) {
  const g = ctx.createLinearGradient(0, 0, 0, H);
  if (mode === 'rendered') { const w = WORLDS[scene.world] || WORLDS.studio; g.addColorStop(0, w.top); g.addColorStop(0.55, w.mid); g.addColorStop(1, w.bot); }
  else { g.addColorStop(0, '#404144'); g.addColorStop(1, '#2f3033'); }
  ctx.globalCompositeOperation = 'source-over';
  ctx.globalAlpha = 1;
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  if (mode === 'rendered' && scene.fx && scene.fx.nebula) {            /* soft coloured gas clouds behind the stars */
    ctx.globalCompositeOperation = 'lighter';
    for (const [x, y, r, c, a] of [[0.2, 0.3, 0.55, [110, 40, 160], 0.2], [0.8, 0.68, 0.6, [30, 80, 170], 0.18], [0.5, 0.9, 0.5, [20, 130, 130], 0.14], [0.65, 0.18, 0.4, [150, 50, 90], 0.12]]) {
      const R = Math.max(W, H) * r, cx = W * x, cy = H * y, gg = ctx.createRadialGradient(cx, cy, 0, cx, cy, R);
      gg.addColorStop(0, rgbs(c, a)); gg.addColorStop(1, rgbs(c, 0));
      ctx.fillStyle = gg; ctx.fillRect(cx - R, cy - R, R * 2, R * 2);
    }
    ctx.globalCompositeOperation = 'source-over';
  }
}

function drawPoints(ctx, scene, project, mode, prog, focal, time) {
  const spin = (scene.spin || 0) * time, cs = Math.cos(spin), sn = Math.sin(spin), rendered = mode === 'rendered', bigs = [];
  if (rendered) ctx.globalCompositeOperation = 'lighter';
  for (const b of scene.buckets) {
    ctx.fillStyle = mode === 'wire' ? 'rgb(190,196,208)' : mode === 'solid' ? 'rgb(176,176,180)' : `rgb(${(b.col[0] * 255) | 0},${(b.col[1] * 255) | 0},${(b.col[2] * 255) | 0})`;
    for (const p of b.pts) {
      const gate = p.ord * 0.85;
      if (prog <= gate) continue;
      const k = clamp((prog - gate) / 0.15), x = p.x * cs - p.y * sn, y = p.x * sn + p.y * cs, q = project(x, y, p.z);
      if (q[2] < 0.3) continue;
      const r = Math.max(0.55, (p.size * focal) / q[2]) * (0.4 + 0.6 * k);
      ctx.globalAlpha = rendered ? p.a * k : 0.85;
      if (r < 1.15) ctx.fillRect(q[0] - r, q[1] - r, r * 2, r * 2);
      else { ctx.beginPath(); ctx.arc(q[0], q[1], r, 0, TAU); ctx.fill(); }
      if (rendered && p.size > 0.028 && bigs.length < 140) bigs.push([q[0], q[1], r, b.col, p.a * k]);
    }
  }
  ctx.globalAlpha = 1;
  for (const [x, y, r, c, a] of bigs) {
    const g = ctx.createRadialGradient(x, y, 0, x, y, r * 5);
    g.addColorStop(0, rgbs([c[0] * 255, c[1] * 255, c[2] * 255], 0.35 * a)); g.addColorStop(1, rgbs([c[0] * 255, c[1] * 255, c[2] * 255], 0));
    ctx.fillStyle = g; ctx.fillRect(x - r * 5, y - r * 5, r * 10, r * 10);
  }
  ctx.globalCompositeOperation = 'source-over';
}

function drawFloorGrid(ctx, project) {
  ctx.lineWidth = 1;
  ctx.strokeStyle = 'rgba(255,255,255,0.075)';
  ctx.beginPath();
  for (let i = -10; i <= 10; i++) {
    if (i === 0) continue;
    for (const [a, b] of [[[i, -10, 0], [i, 10, 0]], [[-10, i, 0], [10, i, 0]]]) {
      const p = project(...a), q = project(...b);
      if (p[2] < 0.3 || q[2] < 0.3) continue;
      ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]);
    }
  }
  ctx.stroke();
  for (const [a, b, col] of [[[-10, 0, 0], [10, 0, 0], 'rgba(229,88,77,0.7)'], [[0, -10, 0], [0, 10, 0], 'rgba(146,196,63,0.7)']]) {
    const p = project(...a), q = project(...b);
    if (p[2] < 0.3 || q[2] < 0.3) continue;
    ctx.strokeStyle = col; ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.stroke();
  }
}

function shadeTri(t, o) {
  /* returns [r,g,b] 0..255 */
  const { mode, flags, camPos, scene } = o;
  let n = t.n;
  const tc = [camPos[0] - t.c[0], camPos[1] - t.c[1], camPos[2] - t.c[2]];
  if (dot(n, tc) < 0) n = [-n[0], -n[1], -n[2]];
  if (mode === 'solid') {
    const l = 0.3 + 0.7 * Math.max(0, dot(n, KEY_DIR)) + 0.1 * (n[2] * 0.5 + 0.5);
    const v = 176 * Math.min(1, l);
    return [v, v, v * 1.02];
  }
  const mat = MATS[t.mat] || MATS.stone;
  let col = t.col;
  if (flags.materials) { const k = 1 + (t.nv - 0.5) * mat.vary * 1.7; col = [col[0] * k, col[1] * k, col[2] * k]; }
  else { const g = 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2]; col = [lerp(col[0], g, 0.6) * 0.92 + 0.04, lerp(col[1], g, 0.6) * 0.92 + 0.04, lerp(col[2], g, 0.6) * 0.92 + 0.04]; }
  if (mode === 'material') {
    const l = 0.38 + 0.62 * Math.max(0, dot(n, KEY_DIR)) + 0.08 * (n[2] * 0.5 + 0.5);
    const e = t.emit ? 0.55 + t.emit * 0.8 : 0;
    return [clamp(col[0] * (l + e)) * 255, clamp(col[1] * (l + e)) * 255, clamp(col[2] * (l + e)) * 255];
  }
  /* rendered */
  const w = WORLDS[scene.world] || WORLDS.studio;
  let r = w.amb[0], g2 = w.amb[1], b = w.amb[2];
  const rim = Math.max(0, dot(n, w.rim.d));
  r += w.rim.c[0] * rim; g2 += w.rim.c[1] * rim; b += w.rim.c[2] * rim;
  const view = norm(tc);
  let spec = 0;
  if (flags.light) {
    for (const L of scene.lights) {
      const lv = [L.p[0] - t.c[0], L.p[1] - t.c[1], L.p[2] - t.c[2]], d2 = lv[0] * lv[0] + lv[1] * lv[1] + lv[2] * lv[2], d = Math.sqrt(d2);
      const ld = [lv[0] / d, lv[1] / d, lv[2] / d], k = (L.k * (1 + (L.flicker ? 0.08 * Math.sin(o.time * 9 + 1.7) + 0.05 * Math.sin(o.time * 23) : 0))) / (1 + 0.32 * d2);
      const df = Math.max(0, dot(n, ld)) * k * ((WORLDS[scene.world] && WORLDS[scene.world].gain) || (scene.world === 'night' ? 1.9 : 1.1));
      r += L.c[0] * df; g2 += L.c[1] * df; b += L.c[2] * df;
      if (mat.shiny > 0.15) { const rf = [2 * dot(n, ld) * n[0] - ld[0], 2 * dot(n, ld) * n[1] - ld[1], 2 * dot(n, ld) * n[2] - ld[2]]; spec += Math.pow(Math.max(0, dot(rf, view)), 26) * mat.shiny * k * 0.9; }
    }
  } else if (scene.world !== 'night' && scene.world !== 'space') { r += 0.12; g2 += 0.12; b += 0.12; }
  let R = col[0] * r + spec, G = col[1] * g2 + spec, B = col[2] * b + spec;
  if (t.emit) { const e = 0.7 + t.emit * 1.1; R += col[0] * e; G += col[1] * e; B += col[2] * e; }
  if (scene.fade && scene.fade.mats.indexOf(t.mat) >= 0) {
    const f = 1 - smooth(clamp((Math.hypot(t.c[0], t.c[1]) - scene.fade.from) / (scene.fade.to - scene.fade.from))), fc = scene.fade.color;
    R = lerp(fc[0], R, f); G = lerp(fc[1], G, f); B = lerp(fc[2], B, f);
  }
  if (flags.finish) { R = 1 - Math.exp(-R * 1.45); G = 1 - Math.exp(-G * 1.45); B = 1 - Math.exp(-B * 1.45); }
  return [clamp(R) * 255, clamp(G) * 255, clamp(B) * 255];
}

function renderScene(ctx, W, H, scene, view) {
  const mode = view.mode, flags = view.flags, time = view.time || 0, prog = view.prog == null ? 1 : view.prog;
  const cx = (view.cx == null ? 0.5 : view.cx) * W, cy = (view.cy == null ? 0.5 : view.cy) * H, focal = (view.focal || 0.95) * H;
  const project = makeProjector(view.cam, W, H, cx, cy, focal);
  const camPos = cameraPos(view.cam);
  drawBackground(ctx, W, H, mode, scene);
  if (mode !== 'rendered') drawFloorGrid(ctx, project);

  /* light pool on the ground + contact shadows */
  if (mode === 'rendered') {
    if (flags.light) for (const L of scene.lights) if (L.pool) {
      const o = project(L.p[0], L.p[1], 0), ex = project(L.p[0] + L.pool, L.p[1], 0), ey = project(L.p[0], L.p[1] + L.pool, 0);
      const pulse = 1 + 0.06 * Math.sin(time * 9) + 0.04 * Math.sin(time * 23);
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      ctx.transform(ex[0] - o[0], ex[1] - o[1], ey[0] - o[0], ey[1] - o[1], o[0], o[1]);
      const g = ctx.createRadialGradient(0, 0, 0, 0, 0, 1);
      g.addColorStop(0, rgbs([255, 120, 40], 0.34 * pulse * prog)); g.addColorStop(0.5, rgbs([255, 90, 20], 0.12 * prog)); g.addColorStop(1, rgbs([255, 80, 10], 0));
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(0, 0, 1, 0, TAU); ctx.fill();
      ctx.restore();
    }
    if (flags.edges) for (const s of scene.shadows) {
      const rot = s.rot || 0, c = Math.cos(rot), sn = Math.sin(rot);
      const o = project(s.x, s.y, 0.005), ex = project(s.x + s.rx * c, s.y + s.rx * sn, 0.005), ey = project(s.x - s.ry * sn, s.y + s.ry * c, 0.005);
      ctx.save();
      ctx.globalCompositeOperation = 'source-over';
      ctx.transform(ex[0] - o[0], ex[1] - o[1], ey[0] - o[0], ey[1] - o[1], o[0], o[1]);
      const g = ctx.createRadialGradient(0, 0, 0, 0, 0, 1);
      g.addColorStop(0, rgbs([0, 0, 0], s.a * prog)); g.addColorStop(0.65, rgbs([0, 0, 0], s.a * 0.45 * prog)); g.addColorStop(1, rgbs([0, 0, 0], 0));
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(0, 0, 1, 0, TAU); ctx.fill();
      ctx.restore();
    }
  }

  if (scene.buckets) drawPoints(ctx, scene, project, mode, prog, focal, time);

  /* gather triangles */
  const items = [], flames = [], glows = [];
  const shadeOpts = { mode, flags, camPos, scene, time };
  const swayT = time;
  for (const t of scene.tris) {
    if (t.tag === 'detail' && !flags.layers) continue;
    const gate = t.ord * 0.85;
    if (prog <= gate) continue;
    const s = clamp((prog - gate) / 0.15);
    const p = t.p;
    let a, b, c;
    if (t.sway) {
      const sw = (z) => Math.sin(swayT * 3.1 + t.ph + z * 1.7) * t.sway * Math.max(0, z - 0.35);
      a = project(p[0] + sw(p[2]), p[1], p[2]); b = project(p[3] + sw(p[5]), p[4], p[5]); c = project(p[6] + sw(p[8]), p[7], p[8]);
    } else { a = project(p[0], p[1], p[2]); b = project(p[3], p[4], p[5]); c = project(p[6], p[7], p[8]); }
    if (a[2] < 0.3 || b[2] < 0.3 || c[2] < 0.3) continue;
    const mx = (a[0] + b[0] + c[0]) / 3, my = (a[1] + b[1] + c[1]) / 3, depth = (a[2] + b[2] + c[2]) / 3;
    const k = s * 1.0;
    const item = { a, b, c, mx, my, depth, s: k, t };
    if (mode === 'rendered' && t.mat === 'flame') { flames.push(item); continue; }
    items.push(item);
  }
  items.sort((x, y) => y.depth - x.depth);

  const wire = mode === 'wire';
  if (wire) {
    ctx.strokeStyle = 'rgba(214,220,232,0.55)'; ctx.lineWidth = 0.8; ctx.beginPath();
    for (const it of [...items, ...flames]) {
      const k = it.s;
      const ax = it.mx + (it.a[0] - it.mx) * k, ay = it.my + (it.a[1] - it.my) * k, bx = it.mx + (it.b[0] - it.mx) * k, by = it.my + (it.b[1] - it.my) * k, cx2 = it.mx + (it.c[0] - it.mx) * k, cy2 = it.my + (it.c[1] - it.my) * k;
      ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.lineTo(cx2, cy2); ctx.closePath();
    }
    ctx.stroke();
  } else {
    const glass = mode === 'rendered' || mode === 'material';
    for (const it of items) {
      const col = shadeTri(it.t, shadeOpts), k = it.s, grow = 0.45;
      const ax = it.mx + (it.a[0] - it.mx) * k, ay = it.my + (it.a[1] - it.my) * k, bx = it.mx + (it.b[0] - it.mx) * k, by = it.my + (it.b[1] - it.my) * k, cx2 = it.mx + (it.c[0] - it.mx) * k, cy2 = it.my + (it.c[1] - it.my) * k;
      const inf = (x, y) => { const dx = x - it.mx, dy = y - it.my, l = Math.hypot(dx, dy) || 1; return [x + (dx / l) * grow, y + (dy / l) * grow]; };
      const A = inf(ax, ay), B = inf(bx, by), C = inf(cx2, cy2);
      ctx.globalAlpha = glass && it.t.alpha < 1 ? it.t.alpha : 1;
      ctx.fillStyle = `rgb(${col[0] | 0},${col[1] | 0},${col[2] | 0})`;
      ctx.beginPath(); ctx.moveTo(A[0], A[1]); ctx.lineTo(B[0], B[1]); ctx.lineTo(C[0], C[1]); ctx.closePath(); ctx.fill();
      if (it.t.emit > 0.4 && mode === 'rendered' && k > 0.6) glows.push(it);
    }
    ctx.globalAlpha = 1;
    /* flames: additive, so overlapping layers get brighter like real fire */
    if (flames.length) {
      flames.sort((x, y) => y.depth - x.depth);
      ctx.globalCompositeOperation = 'lighter';
      for (const it of flames) {
        const t = it.t, k = it.s, e = 0.75 + t.emit * 0.35;
        ctx.globalAlpha = (flags.finish ? 0.5 : 0.62) * (t.alpha == null ? 1 : t.alpha);
        ctx.fillStyle = `rgb(${clamp(t.col[0] * e) * 255 | 0},${clamp(t.col[1] * e) * 255 | 0},${clamp(t.col[2] * e) * 255 | 0})`;
        const ax = it.mx + (it.a[0] - it.mx) * k, ay = it.my + (it.a[1] - it.my) * k, bx = it.mx + (it.b[0] - it.mx) * k, by = it.my + (it.b[1] - it.my) * k, cx2 = it.mx + (it.c[0] - it.mx) * k, cy2 = it.my + (it.c[1] - it.my) * k;
        ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.lineTo(cx2, cy2); ctx.closePath(); ctx.fill();
        if (t.emit > 0.4 && k > 0.6) glows.push(it);
      }
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
    }
    /* bloom */
    if (mode === 'rendered' && flags.finish && glows.length && !view.noBloom) {
      ctx.globalCompositeOperation = 'lighter';
      const seen = new Set();
      let drawn = 0;
      for (const it of glows) {
        const key = ((it.mx / 14) | 0) + ':' + ((it.my / 14) | 0);
        if (seen.has(key) || drawn > 150) continue;
        seen.add(key); drawn++;
        const rad = clamp(Math.sqrt(it.t.area) * focal / it.depth * (it.t.mat === 'flame' ? 5 : 7), 6, 70), col = it.t.col, a0 = it.t.mat === 'flame' ? 0.1 : 0.2;
        const g = ctx.createRadialGradient(it.mx, it.my, 0, it.mx, it.my, rad);
        g.addColorStop(0, rgbs([col[0] * 255, col[1] * 255 * 0.8, col[2] * 255 * 0.6], a0 * prog)); g.addColorStop(1, rgbs([col[0] * 255, col[1] * 255 * 0.5, 40], 0));
        ctx.fillStyle = g; ctx.fillRect(it.mx - rad, it.my - rad, rad * 2, rad * 2);
      }
      ctx.globalCompositeOperation = 'source-over';
    }
  }

  /* the bright heart of a galaxy */
  if (mode === 'rendered' && scene.fx && scene.fx.core && prog > 0.2) {
    const c = project(0, 0, 0), grow = clamp(prog);
    ctx.globalCompositeOperation = 'lighter';
    for (const [rw, col, a] of [[2.6, [255, 170, 90], 0.16], [1.3, [255, 205, 140], 0.28], [0.55, [255, 240, 215], 0.55]]) {
      const R = (rw * focal * grow) / c[2], g = ctx.createRadialGradient(c[0], c[1], 0, c[0], c[1], R);
      g.addColorStop(0, rgbs(col, a)); g.addColorStop(1, rgbs(col, 0));
      ctx.fillStyle = g; ctx.fillRect(c[0] - R, c[1] - R, R * 2, R * 2);
    }
    ctx.globalCompositeOperation = 'source-over';
  }

  /* particles: smoke and sparks */
  if (mode === 'rendered' && scene.fx && prog > 0.5) {
    if (scene.fx.smoke && flags.smoke) {
      for (let i = 0; i < 24; i++) {
        const a = (time * 0.075 + i / 24) % 1, wob = a * 2 + 0.3;
        const p = project(Math.sin(i * 3.1 + a * 3) * 0.28 * wob, Math.cos(i * 1.7 + a * 2.5) * 0.22 * wob, 1.7 + a * 4.2);
        const rad = ((0.36 + a * 1.3) * focal) / p[2], al = 0.2 * Math.pow(Math.sin(Math.PI * a), 1.1);
        const g = ctx.createRadialGradient(p[0], p[1], 0, p[0], p[1], rad);
        const warm = clamp(1 - a * 2.2);
        g.addColorStop(0, rgbs([78 + 80 * warm, 74 + 40 * warm, 80], al)); g.addColorStop(1, rgbs([60, 60, 66], 0));
        ctx.fillStyle = g; ctx.fillRect(p[0] - rad, p[1] - rad, rad * 2, rad * 2);
      }
    }
    if (scene.fx.sparks && flags.layers) {
      ctx.globalCompositeOperation = 'lighter';
      for (let i = 0; i < 34; i++) {
        const r1 = hash3(i, 1, 0), r2 = hash3(i, 2, 0), r3 = hash3(i, 3, 0), r4 = hash3(i, 4, 0);
        const a = (time * (0.11 + 0.17 * r1) + r2) % 1, ang = r3 * TAU, rad = (0.08 + 0.85 * a) * (0.35 + 0.65 * r4);
        const p = project(Math.cos(ang) * rad + Math.sin(time * 1.1 + i) * 0.12 * a, Math.sin(ang) * rad + Math.cos(time * 0.9 + i * 2) * 0.1 * a, 0.9 + a * (2.2 + 1.8 * r1));
        const al = Math.pow(1 - a, 0.8) * (0.65 + 0.35 * Math.sin(time * 14 + i)), rad2 = Math.max(1.1, ((0.026 + 0.02 * r4) * focal) / p[2]);
        ctx.fillStyle = rgbs([255, 150 + 90 * (1 - a), 50], al);
        ctx.beginPath(); ctx.arc(p[0], p[1], rad2, 0, TAU); ctx.fill();
        const g = ctx.createRadialGradient(p[0], p[1], 0, p[0], p[1], rad2 * 4.5);
        g.addColorStop(0, rgbs([255, 140, 40], al * 0.32)); g.addColorStop(1, rgbs([255, 90, 10], 0));
        ctx.fillStyle = g; ctx.fillRect(p[0] - rad2 * 4.5, p[1] - rad2 * 4.5, rad2 * 9, rad2 * 9);
      }
      ctx.globalCompositeOperation = 'source-over';
    }
  }

  /* finishing: vignette */
  if (mode === 'rendered' && flags.finish) {
    const g = ctx.createRadialGradient(W * 0.5, H * 0.52, Math.min(W, H) * 0.3, W * 0.5, H * 0.52, Math.max(W, H) * 0.72);
    g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,0,0.5)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  }
  return { project, camPos, items: items.length + flames.length };
}

const DEFAULT_FLAGS = () => ({ layers: true, materials: true, light: true, smoke: true, edges: true, finish: true });

/* ================================================================== viewport (interactive canvas) */
const NO_MOTION = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
const angDiff = (a, b) => { let d = (b - a) % TAU; if (d > Math.PI) d -= TAU; if (d < -Math.PI) d += TAU; return d; };
const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
const VIEWS = { right: { yaw: -Math.PI / 2, pitch: 0.02 }, left: { yaw: Math.PI / 2, pitch: 0.02 }, back: { yaw: Math.PI, pitch: 0.02 }, front: { yaw: 0, pitch: 0.02 }, top: { yaw: 0, pitch: 1.5 }, bottom: { yaw: 0, pitch: -1.5 } };

class Viewport {
  constructor(canvas, o = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.mode = o.mode || 'rendered';
    this.flags = Object.assign(DEFAULT_FLAGS(), o.flags || {});
    this.cam = { yaw: 0, pitch: 0.3, dist: 9, target: [0, 0, 1] };
    this.goal = null;
    this.scene = null; this.sceneKey = null;
    this.prog = 1; this.anim = null;
    this.time = 0; this.last = 0;
    this.auto = !NO_MOTION && o.auto !== false;
    this.idleUntil = 0;
    this.visible = true; this.dirty = true;
    this.cxRatio = o.cx == null ? 0.5 : o.cx;
    this.onStats = o.onStats || null;
    this.showGizmo = o.gizmo !== false;
    this.gizmoPos = o.gizmoPos || ((W) => [W - 52, 120]);
    this.dprCap = typeof innerWidth === 'number' && innerWidth < 700 ? 1.5 : 2; this.slowFrames = 0; this.noBloom = false;
    this.hover = null; this.drag = null;
    this.resize();
    this.bind();
    viewports.add(this);
  }
  resize() {
    const r = this.canvas.getBoundingClientRect();
    const dpr = Math.min((typeof devicePixelRatio === 'number' && devicePixelRatio) || 1, this.dprCap);
    this.W = Math.max(2, Math.round(r.width)); this.H = Math.max(2, Math.round(r.height)); this.dpr = dpr;
    this.canvas.width = Math.round(this.W * dpr); this.canvas.height = Math.round(this.H * dpr);
    this.dirty = true;
  }
  setMode(mode) { this.mode = mode; this.dirty = true; }
  setFlags(flags) { Object.assign(this.flags, flags); this.dirty = true; }
  snapTo(cam) { this.goal = { yaw: cam.yaw, pitch: cam.pitch, dist: cam.dist == null ? this.cam.dist : cam.dist, target: cam.target || this.cam.target }; if (NO_MOTION) this.jump(); }
  jump() { if (!this.goal) return; Object.assign(this.cam, { yaw: this.goal.yaw, pitch: this.goal.pitch, dist: this.goal.dist, target: this.goal.target.slice() }); this.goal = null; this.dirty = true; }
  setView(name) { const v = VIEWS[name]; if (!v) return; this.snapTo({ yaw: v.yaw, pitch: v.pitch }); this.idleUntil = performance.now() + 7000; this.dirty = true; }
  tween(from, to, ms) {
    return new Promise((resolve) => {
      if (this.anim) this.anim.resolve();
      this.anim = { from, to, ms, start: null, resolve };
      this.prog = from; this.dirty = true;
    });
  }
  setScene(key, o = {}) {
    const next = getScene(key, o.variant);
    const go = () => {
      this.scene = next; this.sceneKey = key;
      if (o.camera !== false) { const c = SCENES[key].cam; this.snapTo(c); if (!this.hasCam) { this.jump(); this.hasCam = true; } }
      this.canvas.setAttribute('aria-label', SCENES[key].aria + '. Drag to rotate, arrow keys also work.');
      if (this.onStats) this.onStats({ tris: next.tris.length, objects: next.objects, key, stars: next.points ? next.points.length : 0 });
      this.dirty = true;
    };
    if (NO_MOTION || o.animate === false || !this.scene) { go(); this.prog = 1; this.dirty = true; return Promise.resolve(); }
    const out = this.prog > 0.02 ? this.tween(this.prog, 0, 300 * this.prog) : Promise.resolve();
    return out.then(() => { go(); return this.tween(0, 1, o.duration || 1500); });
  }
  get animating() { return !!(this.anim || this.goal || (this.auto && performance.now() > this.idleUntil) || (!NO_MOTION && this.mode === 'rendered' && this.scene && (this.scene.fx || this.scene.lights.some((l) => l.flicker)))); }
  bind() {
    const c = this.canvas;
    c.addEventListener('pointerdown', (e) => { this.drag = { x: e.clientX, y: e.clientY, moved: false }; try { c.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ } });
    c.addEventListener('pointermove', (e) => {
      const r = c.getBoundingClientRect();
      if (this.showGizmo && !this.drag) { const h = this.hitGizmo(e.clientX - r.left, e.clientY - r.top); if (h !== this.hover) { this.hover = h; c.style.cursor = h ? 'pointer' : ''; this.dirty = true; } }
      if (!this.drag) return;
      const dx = e.clientX - this.drag.x, dy = e.clientY - this.drag.y;
      if (!this.drag.moved && Math.hypot(dx, dy) < 4) return;
      this.drag.moved = true; this.goal = null;
      this.cam.yaw += dx * 0.008; this.cam.pitch = clamp(this.cam.pitch + dy * 0.006, -0.1, 1.5);
      this.drag.x = e.clientX; this.drag.y = e.clientY; this.idleUntil = performance.now() + 7000; this.dirty = true;
    });
    const up = (e) => {
      if (this.drag && !this.drag.moved && this.showGizmo) { const r = c.getBoundingClientRect(), h = this.hitGizmo(e.clientX - r.left, e.clientY - r.top, e.pointerType === 'touch'); if (h) this.setView(h); }
      this.drag = null;
    };
    c.addEventListener('pointerup', up);
    c.addEventListener('pointercancel', () => { this.drag = null; });
    c.addEventListener('pointerleave', () => { if (this.hover) { this.hover = null; c.style.cursor = ''; this.dirty = true; } });
    c.addEventListener('keydown', (e) => {
      const k = e.key;
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(k)) return;
      e.preventDefault(); this.goal = null;
      if (k === 'ArrowLeft') this.cam.yaw -= 0.16; if (k === 'ArrowRight') this.cam.yaw += 0.16;
      if (k === 'ArrowUp') this.cam.pitch = clamp(this.cam.pitch - 0.1, -0.1, 1.5); if (k === 'ArrowDown') this.cam.pitch = clamp(this.cam.pitch + 0.1, -0.1, 1.5);
      this.idleUntil = performance.now() + 7000; this.dirty = true;
    });
  }
  gizmoAxes() {
    const [gx, gy] = this.gizmoPos(this.W), R = 30, cy = Math.cos(this.cam.yaw), sy = Math.sin(this.cam.yaw), cp = Math.cos(this.cam.pitch), sp = Math.sin(this.cam.pitch);
    const out = [];
    for (const [name, v, label, col] of [['right', [1, 0, 0], 'X', '#e5584d'], ['left', [-1, 0, 0], '', '#e5584d'], ['back', [0, 1, 0], 'Y', '#92c43f'], ['front', [0, -1, 0], '', '#92c43f'], ['top', [0, 0, 1], 'Z', '#4f95e8'], ['bottom', [0, 0, -1], '', '#4f95e8']]) {
      const x1 = v[0] * cy - v[1] * sy, y1 = v[0] * sy + v[1] * cy, y2 = y1 * cp - v[2] * sp, z2 = y1 * sp + v[2] * cp;
      out.push({ name, label, col, x: gx + x1 * R, y: gy - z2 * R, depth: y2, pos: !!label });
    }
    return { gx, gy, axes: out.sort((a, b) => b.depth - a.depth) };
  }
  hitGizmo(px, py, touch) {
    const { axes } = this.gizmoAxes();
    let best = null, bd = touch ? 21 : 13;
    for (const a of axes) { const d = Math.hypot(a.x - px, a.y - py); if (d < bd) { bd = d; best = a.name; } }
    return best;
  }
  drawGizmo(ctx) {
    const { gx, gy, axes } = this.gizmoAxes();
    ctx.save();
    ctx.globalAlpha = 1;
    ctx.fillStyle = 'rgba(30,31,34,0.55)'; ctx.beginPath(); ctx.arc(gx, gy, 43, 0, TAU); ctx.fill();
    for (const a of axes) {
      const hot = this.hover === a.name;
      if (a.pos) { ctx.strokeStyle = a.col; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(gx, gy); ctx.lineTo(a.x, a.y); ctx.stroke(); }
      ctx.fillStyle = a.pos ? a.col : 'rgba(60,62,66,0.9)'; ctx.globalAlpha = a.pos ? 1 : 0.9;
      ctx.beginPath(); ctx.arc(a.x, a.y, a.pos ? 9.5 : 7, 0, TAU); ctx.fill();
      if (!a.pos) { ctx.strokeStyle = a.col; ctx.lineWidth = 1.2; ctx.stroke(); }
      if (hot) { ctx.globalAlpha = 1; ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.6; ctx.beginPath(); ctx.arc(a.x, a.y, (a.pos ? 9.5 : 7) + 2.5, 0, TAU); ctx.stroke(); }
      if (a.label) { ctx.globalAlpha = 1; ctx.fillStyle = '#17181a'; ctx.font = '700 11px Inter, system-ui, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(a.label, a.x, a.y + 0.5); }
    }
    ctx.restore();
  }
  drawScan(ctx, project) {
    const b = this.scene.bounds, radial = this.scene.scanMode === 'radial', z = radial ? 0 : lerp(b.zmin, b.zmax, clamp(this.prog / 0.85)), R = radial ? (this.scene.scanR || 2.6) * clamp(this.prog) : (this.scene.scanR || 2.6);
    ctx.save();
    ctx.strokeStyle = 'rgba(245,160,44,0.9)'; ctx.lineWidth = 1.6; ctx.beginPath();
    for (let i = 0; i <= 48; i++) { const a = (i / 48) * TAU, p = project(Math.cos(a) * R, Math.sin(a) * R, z); if (i) ctx.lineTo(p[0], p[1]); else ctx.moveTo(p[0], p[1]); }
    ctx.stroke();
    ctx.strokeStyle = 'rgba(245,160,44,0.25)'; ctx.lineWidth = 1; ctx.beginPath();
    for (let i = 0; i <= 48; i++) { const a = (i / 48) * TAU, p = project(Math.cos(a) * R * 1.06, Math.sin(a) * R * 1.06, z - 0.05); if (i) ctx.lineTo(p[0], p[1]); else ctx.moveTo(p[0], p[1]); }
    ctx.stroke();
    ctx.restore();
  }
  draw() {
    if (!this.scene) return;
    const ctx = this.ctx;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    const cx = typeof this.cxRatio === 'function' ? this.cxRatio(this.W) : this.cxRatio;
    const portrait = this.W / this.H < 1.1, zoom = portrait ? (SCENES[this.sceneKey].portraitZoom || 1) : 1;   /* phones: fill the narrow canvas */
    const info = renderScene(ctx, this.W, this.H, this.scene, { cam: this.cam, mode: this.mode, flags: this.flags, time: this.time, prog: this.prog, cx, cy: 0.5, focal: (this.focal || 0.95) * zoom, noBloom: this.noBloom });
    if (this.prog > 0 && this.prog < 1) this.drawScan(ctx, info.project);
    if (this.showGizmo) this.drawGizmo(ctx);
    this.dirty = false;
  }
  step(ts, dt) {
    this.time += NO_MOTION ? 0 : dt;
    if (this.anim) {
      const a = this.anim;
      if (a.start == null) a.start = ts;
      const t = clamp((ts - a.start) / a.ms);
      this.prog = lerp(a.from, a.to, ease(t));
      if (t >= 1) { this.anim = null; this.prog = a.to; a.resolve(); }
      this.dirty = true;
    }
    if (this.goal) {
      const k = 1 - Math.exp(-dt * 6), g = this.goal;
      this.cam.yaw += angDiff(this.cam.yaw, g.yaw) * k; this.cam.pitch += (g.pitch - this.cam.pitch) * k; this.cam.dist += (g.dist - this.cam.dist) * k;
      for (let i = 0; i < 3; i++) this.cam.target[i] += (g.target[i] - this.cam.target[i]) * k;
      if (Math.abs(angDiff(this.cam.yaw, g.yaw)) < 0.002 && Math.abs(g.pitch - this.cam.pitch) < 0.002 && Math.abs(g.dist - this.cam.dist) < 0.01) this.jump();
      this.dirty = true;
    } else if (this.auto && !this.drag && ts > this.idleUntil) { this.cam.yaw += dt * 0.11; this.dirty = true; }
  }
}

const viewports = new Set();
let lastTs = 0;
function loop(ts) {
  const dt = Math.min(0.05, (ts - lastTs) / 1000 || 0);
  lastTs = ts;
  if (!document.hidden) {
    for (const vp of viewports) {
      if (!vp.visible) continue;
      vp.step(ts, dt);
      if (vp.dirty || vp.animating) {
        const t0 = performance.now();
        vp.draw();
        const cost = performance.now() - t0;
        vp.slowFrames = cost > 24 ? vp.slowFrames + 1 : Math.max(0, vp.slowFrames - 1);
        if (vp.slowFrames > 40 && !vp.noBloom) { vp.noBloom = true; if (vp.dprCap > 1) { vp.dprCap = 1; vp.resize(); } }
      }
    }
  }
  requestAnimationFrame(loop);
}

/* ================================================================== text: the simulated agent */
const MATCHERS = [
  ['room', /\b(room|rooms|living|interior|home|house|bedroom|office|apartment|flat|ghar|kamra)\b/i],
  ['galaxy', /\b(galaxy|galaxies|space|star|stars|nebula|planet|cosmos|universe|milky|aakash|sitare)\b/i],
  ['mountains', /mountain|terrain|hill|pahad|landscape/i],
  ['campfire', /fire|camp|aag|bonfire|torch/i],
];
const matchScene = (text) => { for (const [k, re] of MATCHERS) if (re.test(text || '')) return k; return null; };

const SIM = {
  campfire: { prompt: 'make a campfire', lines: [
    [450, 'route', 'Route: skill fast path (library_props). No AI request is used.'],
    [700, 'tool', 'library.place campfire: 14 stones, 4 logs, 28 coals, 13 flame meshes, 1 light', { scene: 'campfire' }],
    [1500, 'tool', 'material.recipe fire_flame, ember, rough_stone, charred_wood on the new parts'],
    [650, 'tool', 'light.create Fire_light: warm orange, next to the flames'],
    [650, 'ok', 'Auto-check passed: console clean, vision 8.4/10'],
  ] },
  room: { prompt: 'design a modern living room with a floating ceiling light, a sofa, a bookshelf and a desk', lines: [
    [450, 'route', 'Route: a big request, split into 6 steps. Each step shows its own progress.'],
    [700, 'tool', 'Step 1: floor, back wall, left wall and right wall (front open, no ceiling)', { scene: 'room', variant: 3, duration: 2600 }],
    [1200, 'tool', 'Step 2: wooden slat panels and a dark TV panel on the back wall'],
    [1000, 'tool', 'Step 3: floating ceiling panel, warm LED strip and 3 pendant lamps (material.recipe glow)'],
    [1000, 'tool', 'Step 4: sofa, rug and coffee table, bookshelf with books'],
    [1000, 'tool', 'Step 5: desk, monitor, chair, floor lamp and two plants'],
    [900, 'tool', 'Step 6: light.create x5 and render.setup preset=night'],
    [700, 'ok', 'Auto-check passed: console clean, vision 8.3/10'],
  ] },
  galaxy: { prompt: 'make a spiral galaxy with a ringed planet', lines: [
    [450, 'route', 'Route: no skill matches. Gemini plans 4 tool calls.'],
    [700, 'tool', 'mesh.create two spiral arms: 3,400 star points from one spiral formula', { scene: 'galaxy', duration: 2600 }],
    [1300, 'tool', 'mesh.create bright core and a faint outer halo, then a far star field'],
    [1000, 'tool', 'mesh.sdf planet with a ring, plus a small moon'],
    [900, 'tool', 'material.recipe glow on the stars, world.set near-black blue, render.setup preset=night'],
    [700, 'ok', 'Auto-check passed: console clean, vision 8.0/10'],
  ] },
  mountains: { prompt: 'make mountains', lines: [
    [450, 'route', 'Route: no skill matches. Gemini plans 2 tool calls.'],
    [700, 'tool', 'mesh.terrain preset=mountains seed=7 size=9', { scene: 'mountains' }],
    [1300, 'tool', 'material.recipe water on the lake plane'],
    [500, 'ok', 'Auto-check passed: console clean, vision 7.6/10'],
  ] },
};
const fmtClock = (ms) => { const s = Math.max(0, Math.round(ms / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };

/* ================================================================== text: tool groups */
const TOOL_GROUPS = [
  { id: 'basics', name: 'Scene basics', blurb: 'Make, move, rename and delete objects. Add cameras and lights. Look at what is in the scene. Everything else is built on these.',
    tools: ['scene.inspect', 'object.create', 'object.transform', 'object.duplicate', 'object.rename', 'object.delete', 'camera.create', 'camera.set', 'light.create', 'world.set', 'render.preview'],
    tries: ['add a cube at 2, 0, 0', 'add a warm light above the cube'] },
  { id: 'shapes', name: 'Shape makers', blurb: 'Turn a few numbers into a full 3D shape: bottles and vases, smooth blended solids, gears and stars, terrain, tubes and shapes made from a formula.',
    tools: ['mesh.lathe', 'mesh.sdf', 'mesh.prism', 'mesh.terrain', 'mesh.create', 'mesh.script', 'curve.create'],
    tries: ['make mountains', 'make a spiral galaxy with a ringed planet', 'make a wine glass'] },
  { id: 'edit', name: 'Shape editors', blurb: 'Change a shape the way an artist would: 26 presets such as melted, twisted, bent, crushed and spiky, plus damage and a clean-up that makes tidy quad faces.',
    tools: ['mesh.edit', 'mesh.damage', 'retopology.analyze', 'retopology.remesh', 'modifier.add', 'modifier.configure', 'modifier.remove'],
    tries: ['make the bottle look melted', 'make the top of the bottle look broken'] },
  { id: 'props', name: 'Props and people', blurb: '14 ready-made props, a search over 991 free (CC0) models, and cartoon characters with 8 faces, 7 hair styles, and glasses, caps or hats.',
    tools: ['library.place', 'library.list', 'asset.search_local', 'asset.place_local', 'character.create'],
    tries: ['make a campfire', 'make a cute girl with long blonde hair, blue eyes and glasses, laughing'] },
  { id: 'shading', name: 'Shading and finish', blurb: '14 ready-made materials such as fire, smoke, wood, rough stone, glass and car paint, any custom material, and the final touch: colour, blur and brightness.',
    tools: ['material.recipe', 'material.nodes', 'material.create', 'material.assign', 'material.modify', 'render.setup'],
    tries: ['make the lantern glow warmer'] },
  { id: 'check', name: 'Build and check', blurb: 'For things no ready tool can make, Gemini writes a build script and improves it by looking at pictures. After every task, the Blender console and a picture are checked, and problems are fixed.',
    tools: ['build.iterate', 'vision.observe', 'python.execute (always asks first)'],
    tries: ['design a modern living room with a floating ceiling light, a sofa, a bookshelf and a desk'] },
];

/* ================================================================== page wiring */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const wait = (ms) => new Promise((r) => setTimeout(r, NO_MOTION ? Math.min(ms, 60) : ms));
let labHint = null;

function toast(msg) {
  const el = $('#toast');
  if (!el) return;
  el.textContent = msg; el.classList.add('show');
  clearTimeout(toast.h); toast.h = setTimeout(() => el.classList.remove('show'), 2800);
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (_) {
    const ta = document.createElement('textarea');
    ta.value = text; ta.setAttribute('readonly', ''); ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
    document.body.appendChild(ta); ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (__) { ok = false; }
    ta.remove();
    return ok;
  }
}
function watchVisibility(vp) {
  if (typeof IntersectionObserver !== 'function') return;
  new IntersectionObserver((es) => { for (const e of es) { vp.visible = e.isIntersecting; if (e.isIntersecting) vp.dirty = true; } }, { rootMargin: '80px' }).observe(vp.canvas);
  if (typeof ResizeObserver === 'function') new ResizeObserver(() => vp.resize()).observe(vp.canvas);
  else window.addEventListener('resize', () => vp.resize());
}
function bindModeButtons(group, vp, onChange) {
  const buttons = $$('button[data-mode]', group);
  buttons.forEach((b) => b.addEventListener('click', () => {
    vp.setMode(b.dataset.mode);
    buttons.forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    if (onChange) onChange(b.dataset.mode);
  }));
}

/* ---- workspace tabs follow the scroll position ---- */
function initNav() {
  const links = $$('.workspaces a'), map = new Map(links.map((a) => [a.getAttribute('href').slice(1), a]));
  if (typeof IntersectionObserver !== 'function') return;
  const io = new IntersectionObserver((es) => {
    for (const e of es) if (e.isIntersecting && map.has(e.target.id)) { links.forEach((l) => l.removeAttribute('aria-current')); map.get(e.target.id).setAttribute('aria-current', 'page'); }
  }, { rootMargin: '-45% 0px -50% 0px' });
  $$('main section[id]').forEach((s) => { if (map.has(s.id)) io.observe(s); });
}

/* ---- hero: the viewport and the fake console ---- */
let heroVp = null, runToken = 0;
function logLine(kind, text) {
  const log = $('#log');
  if (!log) return;
  const p = document.createElement('p');
  p.className = 'line ' + kind;
  p.textContent = text;
  log.appendChild(p);
  while (log.children.length > 60) log.removeChild(log.firstChild);
  log.scrollTop = log.scrollHeight;
}
function setProgress(frac, label) {
  const bar = $('#progress');
  if (bar) bar.style.setProperty('--p', String(clamp(frac)));
  const l = $('#progress-label');
  if (l) l.textContent = label;
}
async function runPrompt(raw) {
  const text = (raw || '').trim();
  if (!text || !heroVp) return;
  const token = ++runToken, key = matchScene(text), log = $('#log');
  if (log) log.textContent = '';
  logLine('req', text);
  if (!key) {
    await wait(350);
    if (token !== runToken) return;
    logLine('route', `Route: no demo scene matches "${text.slice(0, 60)}".`);
    logLine('warn', 'This preview can draw 4 things: campfire, room design, galaxy space and mountains.');
    logLine('route', 'The real agent is not limited to these: Gemini, Groq or OpenAI plan the tool calls for open requests.');
    setProgress(0, 'Waiting for a request');
    return;
  }
  const sim = SIM[key], total = sim.lines.length, t0 = performance.now();
  const totalMs = sim.lines.reduce((s, l) => s + l[0], 0);
  let elapsedPlan = 0;
  setProgress(0, `Step 0/${total}`);
  for (let i = 0; i < total; i++) {
    const [delay, kind, line, opt = {}] = sim.lines[i];
    await wait(delay);
    if (token !== runToken) return;
    elapsedPlan += delay;
    logLine(kind, line);
    setProgress((i + 1) / total, i + 1 === total ? `Done in ${fmtClock(performance.now() - t0)}` : `Step ${i + 1}/${total}, about ${fmtClock((totalMs - elapsedPlan) * (NO_MOTION ? 0.05 : 1))} left`);
    if (opt.scene) {
      const p = heroVp.setScene(opt.scene, { variant: opt.variant, duration: opt.duration || (opt.scene === 'campfire' ? 1900 : 1500) });
      if (opt.wait) { await p; if (token !== runToken) return; }
    }
  }
}
function initHero() {
  const canvas = $('#hero-canvas');
  if (!canvas) return;
  const stats = $('#vp-stats'), title = $('#vp-object');
  heroVp = new Viewport(canvas, {
    cx: (W) => (W >= 980 ? 0.66 : 0.5), gizmoPos: (W) => [W - 54, 112],
    onStats: (s) => {
      if (stats) stats.textContent = `Objects ${s.objects}\u00a0\u00a0\u00a0Triangles ${s.tris.toLocaleString('en-US')}` + (s.stars ? `\u00a0\u00a0\u00a0Stars ${s.stars.toLocaleString('en-US')}` : '');
      if (title) title.textContent = SCENES[s.key].label;
    },
  });
  heroVp.setScene('campfire', { animate: false });
  heroVp.prog = NO_MOTION ? 1 : 0;
  watchVisibility(heroVp);
  bindModeButtons($('#shade-hero'), heroVp);
  const form = $('#promptform'), input = $('#prompt');
  if (form) form.addEventListener('submit', (e) => { e.preventDefault(); runPrompt(input.value); });
  $$('#chips button').forEach((b) => b.addEventListener('click', () => { input.value = b.dataset.prompt; runPrompt(b.dataset.prompt); }));
  let typing = true;
  input.addEventListener('focus', () => { typing = false; }, { once: true });
  const intro = async () => {
    const text = SIM.campfire.prompt;
    if (!NO_MOTION) {
      await wait(500);
      for (let i = 1; i <= text.length && typing; i++) { input.value = text.slice(0, i); await wait(42); }
    } else input.value = text;
    if (typing) runPrompt(text);
  };
  if (!NO_MOTION) heroVp.prog = 0;
  intro();
}

/* ---- modeling: outliner + properties ---- */
function tryPrompt(text) {
  if (matchScene(text) && heroVp) {
    const input = $('#prompt');
    input.value = text;
    $('#layout').scrollIntoView({ behavior: NO_MOTION ? 'auto' : 'smooth', block: 'start' });
    setTimeout(() => runPrompt(text), NO_MOTION ? 0 : 450);
  } else {
    copyText(text).then((ok) => toast(ok ? 'Copied. Paste it into the AI Copilot panel in Blender.' : 'Select the text and copy it by hand.'));
  }
}
function initModeling() {
  const list = $('#outliner'), props = $('#props');
  if (!list || !props) return;
  const show = (g) => {
    props.textContent = '';
    const h = document.createElement('h3'); h.textContent = g.name;
    const p = document.createElement('p'); p.textContent = g.blurb;
    const ul = document.createElement('ul'); ul.className = 'pills';
    g.tools.forEach((n) => { const li = document.createElement('li'); const c = document.createElement('code'); c.textContent = n; li.appendChild(c); ul.appendChild(li); });
    const tr = document.createElement('div'); tr.className = 'tries';
    const lab = document.createElement('p'); lab.className = 'tries-label'; lab.textContent = 'Ask it for';
    tr.appendChild(lab);
    g.tries.forEach((q) => { const b = document.createElement('button'); b.type = 'button'; b.className = 'chip'; b.textContent = q; b.addEventListener('click', () => tryPrompt(q)); tr.appendChild(b); });
    props.append(h, p, ul, tr);
  };
  TOOL_GROUPS.forEach((g, i) => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'tree-item'; b.setAttribute('aria-pressed', String(i === 0));
    const name = document.createElement('span'); name.textContent = g.name;
    const count = document.createElement('small'); count.textContent = String(g.tools.length);
    b.append(name, count);
    b.addEventListener('click', () => { $$('.tree-item', list).forEach((x) => x.setAttribute('aria-pressed', String(x === b))); show(g); });
    list.appendChild(b);
  });
  show(TOOL_GROUPS[0]);
}


/* ================================================================== prompt coach */
const COACH = {
  noun: /\b(?:campfire|fire|bonfire|galaxy|planet|room|tent|lantern|lamp|torch|tree|pine|forest|bush|rock|stone|table|chair|bench|stool|bed|sofa|shelf|house|cabin|hut|fence|bottle|vase|glass|cup|bowl|gear|snowman|mountain|terrain|car|truck|bus|bike|boat|ship|plane|robot|dog|cat|horse|dragon|girl|boy|character|face|mushroom|cloud|castle|bridge|road)(?:s|es)?\b/i,
  color: /\b(red|green|blue|yellow|orange|pink|purple|black|white|grey|gray|brown|gold|golden|silver|blonde|teal|navy|cyan)\b/i,
  size: /\b(\d+(\.\d+)?\s?(m|cm|mm|ft|metres?|meters?|feet)\b|one|two|three|four|five|six|seven|eight|nine|ten|dozen|pair|small|tiny|little|big|large|huge|giant|tall|short|long|wide|thin)\b/i,
  style: /\b(wooden|wood|metal|metallic|steel|iron|glass|stone|rusty|rusted|fabric|leather|plastic|marble|realistic|cartoon|low[- ]?poly|stylized|stylised|detailed|toy|cute)\b/i,
  light: /\b(night|sunset|sunrise|morning|noon|daylight|evening|dusk|dawn|studio|warm|cold|foggy|misty|snowy|rainy|moonlight|candlelight|neon|sunny|cloudy)\b/i,
  character: /\b(girl|boy|character|cartoon|chibi|mascot|face|head|avatar|person)\b/i,
  prop: /\b(campfire|fire|bonfire|tent|lantern|torch|pine|tree|trees|bush|rock|stool|mushroom|fence|street ?lamp|cloud|log seat)\b/i,
  hard: /\b(car|cars|truck|bus|van|bike|bicycle|motorcycle|plane|jet|helicopter|boat|ship|train|tank|dog|cat|horse|lion|tiger|elephant|bird|fish|dragon|dinosaur|robot|human|man|woman|castle|guitar|phone|laptop)\b/i,
  real: /\b(realistic|photorealistic|detailed|lifelike|real)\b/i,
  simple: /\b(low[- ]?poly|simple|toy|cartoon|stylized|stylised|blocky)\b/i,
};
const COACH_ITEMS = [
  ['noun', 'Say what it is', 'Say what to build, like campfire, room or mountains.'],
  ['color', 'Colour', 'Add a colour: red, blonde, dark green.'],
  ['size', 'Size or number', 'Say how many or how big: small, huge, two, about 2 m.'],
  ['style', 'Material or look', 'Add a material or a look: wooden, metal, realistic, low poly.'],
  ['light', 'Light or time of day', 'Say when it is: at night, at sunset, in soft studio light.'],
];
const COACH_ADD = {
  color: [['red', 'adj'], ['dark green', 'adj'], ['golden', 'adj']],
  size: [['small', 'adj'], ['huge', 'adj'], ['about 2 m tall', 'end']],
  style: [['wooden', 'adj'], ['realistic', 'adj'], ['low poly', 'adj']],
  light: [['at night', 'end'], ['at sunset', 'end'], ['in soft studio light', 'end']],
};
function coachAnalyze(text) {
  const t = (text || '').trim(), found = {};
  for (const [key] of COACH_ITEMS) found[key] = COACH[key].test(t);
  const detail = COACH_ITEMS.filter(([k]) => found[k]).length;
  /* the agent splits a request into steps only when 3 or more comma/then parts each start with an action word */
  const parts = t.split(/\s*(?:,|;|\band then\b|\bthen\b|\bphir\b)\s*/i).map((x) => x.trim())
    .filter((x) => /^(?:please\s+)?(?:make|add|create|build|place|put|draw|generate|insert|banao|bana)\b/i.test(x)).length;
  let route = '';
  if (!t) route = 'Type a request above to see how the agent would build it.';
  else if (COACH.character.test(t) && !COACH.real.test(t)) route = 'Cartoon character skill. It is built straight away, with no AI request.';
  else if (COACH.prop.test(t)) route = 'Ready-made prop from the built-in library. It is built straight away, with no AI request.';
  else if (COACH.hard.test(t) && COACH.real.test(t)) route = 'Build loop. Gemini writes a build script, pictures are taken from four sides and scored, and the script is fixed for up to three rounds.';
  else if (COACH.hard.test(t) && COACH.simple.test(t)) route = 'A simple, stylised build from basic shapes. The AI model you chose plans it.';
  else if (COACH.hard.test(t)) route = 'It looks for a ready-made model first. If none fits, the build loop starts.';
  else route = 'The AI model you chose plans the steps: shapes, materials and lights.';
  if (parts >= 3) route += ` Your ${parts} parts will run as ${parts} steps. Each step shows its progress and time left.`;
  return { found, detail, route, parts, empty: !t };
}
const coachRank = (w) => (COACH.size.test(w) ? 0 : COACH.color.test(w) ? 1 : COACH.style.test(w) ? 2 : 1.5);
function coachInsert(text, phrase, mode) {
  const t = text.trim();
  if (!t) return phrase;
  if (mode === 'end') return t.replace(/[.,;\s]+$/, '') + ' ' + phrase;
  const m = COACH.noun.exec(t);
  if (!m) return t + ' ' + phrase;
  const before = t.slice(0, m.index).replace(/\s+$/, ''), after = t.slice(m.index);
  /* split what is before the noun into: lead words, optional article, and adjectives that sit right in front of the noun */
  const art = /\b(a|an|the|some)\s+((?:[\w-]+\s*)*)$/i.exec(before);
  let lead, article, adjs;
  if (art) { lead = before.slice(0, art.index); article = art[1].toLowerCase(); adjs = art[2].trim().split(/\s+/).filter(Boolean); }
  else { lead = before + (before ? ' ' : ''); article = ''; adjs = []; }
  const rank = coachRank(phrase);
  let at = adjs.findIndex((w) => coachRank(w) > rank);
  if (at < 0) at = adjs.length;
  adjs.splice(at, 0, phrase);
  if (article === 'a' || article === 'an') article = /^[aeiou]/i.test(adjs[0]) ? 'an' : 'a';
  return (lead + (article ? article + ' ' : '') + adjs.join(' ') + ' ' + after).replace(/\s+/g, ' ');
}
function initCoach() {
  const input = $('#coach-input');
  if (!input) return;
  const list = $('#coach-list'), add = $('#coach-add'), route = $('#coach-route'), score = $('#coach-score'), tryBtn = $('#coach-try');
  const rows = COACH_ITEMS.map(([key, label, tip]) => {
    const li = document.createElement('li');
    const mark = document.createElement('span'); mark.className = 'check-mark'; mark.setAttribute('aria-hidden', 'true');
    const body = document.createElement('span'); body.className = 'check-body';
    const b = document.createElement('b'); b.textContent = label;
    const small = document.createElement('small'); small.textContent = tip;
    body.append(b, small); li.append(mark, body); list.appendChild(li);
    return { key, li, label, tip, small };
  });
  const update = () => {
    const a = coachAnalyze(input.value);
    rows.forEach((r) => {
      const on = !a.empty && a.found[r.key];
      r.li.classList.toggle('on', on);
      r.small.textContent = on ? 'The agent will pick this up.' : r.tip;
    });
    score.textContent = a.empty ? 'Detail level: 0 of 5' : `Detail level: ${a.detail} of 5`;
    route.textContent = a.route;
    tryBtn.disabled = !(matchScene(input.value) && !a.empty);
    add.textContent = '';
    if (!a.empty) {
      COACH_ITEMS.forEach(([key]) => {
        if (a.found[key]) return;
        (COACH_ADD[key] || []).slice(0, 2).forEach(([phrase, mode]) => {
          const bt = document.createElement('button');
          bt.type = 'button'; bt.className = 'chip'; bt.textContent = phrase;
          bt.addEventListener('click', () => { input.value = coachInsert(input.value, phrase, mode); update(); });
          add.appendChild(bt);
        });
      });
    }
  };
  input.addEventListener('input', update);
  $('#coach-copy').addEventListener('click', async () => {
    if (!input.value.trim()) { toast('Type a request first.'); return; }
    toast((await copyText(input.value.trim())) ? 'Request copied. Paste it into the AI Copilot panel in Blender.' : 'Select the text and copy it by hand.');
  });
  tryBtn.addEventListener('click', () => { if (!tryBtn.disabled) tryPrompt(input.value.trim()); });
  input.value = 'make a campfire';
  update();
}

/* ---- shading lab ---- */
function initLab() {
  const canvas = $('#lab-canvas');
  if (!canvas) return;
  const vp = new Viewport(canvas, { cx: 0.5, gizmoPos: (W) => [W - 50, 108] });
  vp.setScene('campfire', { animate: false });
  vp.focal = 1.0;
  watchVisibility(vp);
  const hint = $('#lab-hint'), count = $('#lab-count'), boxes = $$('#lab-rules input[data-flag]');
  labHint = () => {
    if (hint) hint.textContent = vp.mode === 'rendered' ? '' : 'Solid view hides most of this. Switch to Rendered to see it.';
    if (count) count.textContent = `${boxes.filter((b) => b.checked).length} of ${boxes.length} habits on`;
  };
  bindModeButtons($('#shade-lab'), vp, labHint);
  boxes.forEach((b) => b.addEventListener('change', () => { vp.setFlags({ [b.dataset.flag]: b.checked }); labHint(); }));
  const setAll = (on) => { boxes.forEach((b) => { b.checked = on; vp.flags[b.dataset.flag] = on; }); vp.dirty = true; labHint(); };
  $('#lab-plain').addEventListener('click', () => setAll(false));
  $('#lab-full').addEventListener('click', () => setAll(true));
  labHint();
}

/* ---- the self-correcting loop ---- */
const LOOP_ROUNDS = [
  { v: 1, score: 5.5, notes: ['The sofa floats about 25 cm above the floor.', 'No lights are on, so the room looks flat and dark.'] },
  { v: 2, score: 7.4, notes: ['The desk has no monitor, chair or lamp.', 'The ceiling light and the pendant lamps are not glowing.'] },
  { v: 3, score: 8.6, notes: ['Target of 8 reached. The best version stays in the scene.'] },
];
const THUMB_CAMS = {
  front: { yaw: 0, pitch: 0.1, dist: 7.0, target: [0, 0.3, 1.25] },
  left: { yaw: 0.45, pitch: 0.14, dist: 7.0, target: [0, 0.3, 1.25] },
  right: { yaw: -0.45, pitch: 0.14, dist: 7.0, target: [0, 0.3, 1.25] },
  close: { yaw: 0.25, pitch: 0.2, dist: 4.4, target: [0.2, 0.5, 0.95] },
};
function drawThumbs(variant) {
  const scene = getScene('room', variant);
  $$('#loop-thumbs canvas').forEach((cv) => {
    const r = cv.getBoundingClientRect();
    if (r.width < 4) return;
    const dpr = Math.min((typeof devicePixelRatio === 'number' && devicePixelRatio) || 1, 2), W = Math.round(r.width), H = Math.round(r.height);
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const c = THUMB_CAMS[cv.dataset.view];
    renderScene(ctx, W, H, scene, { cam: { yaw: c.yaw, pitch: c.pitch, dist: c.dist, target: c.target.slice() }, mode: 'rendered', flags: DEFAULT_FLAGS(), time: 0, prog: 1, cx: 0.5, cy: 0.52, focal: 0.95, noBloom: true });
  });
}
function initLoop() {
  const box = $('#loop-thumbs');
  if (!box) return;
  const steps = $$('#loop-steps li'), score = $('#loop-score'), scoreText = $('#loop-score-text'), notes = $('#loop-notes'), round = $('#loop-round'), play = $('#loop-play');
  let current = 3, token = 0;
  const showScore = (r) => {
    score.style.setProperty('--p', String(r.score / 10)); scoreText.textContent = `${r.score.toFixed(1)} / 10`;
    notes.textContent = '';
    r.notes.forEach((n) => { const li = document.createElement('li'); li.textContent = n; notes.appendChild(li); });
  };
  const mark = (n) => steps.forEach((li, i) => li.classList.toggle('on', i === n));
  const settle = () => { mark(-1); showScore(LOOP_ROUNDS[2]); round.textContent = 'Round 3 of 3'; drawThumbs(3); current = 3; };
  settle();
  window.addEventListener('resize', () => drawThumbs(current));
  if (typeof IntersectionObserver === 'function') new IntersectionObserver((es) => { if (es[0].isIntersecting) drawThumbs(current); }, { rootMargin: '100px' }).observe(box);
  play.addEventListener('click', async () => {
    const my = ++token;
    play.disabled = true;
    for (let i = 0; i < LOOP_ROUNDS.length; i++) {
      const r = LOOP_ROUNDS[i];
      round.textContent = `Round ${i + 1} of 3`;
      mark(0); await wait(750); if (my !== token) return;
      mark(1); await wait(750); if (my !== token) return;
      mark(2); current = r.v; drawThumbs(r.v); await wait(900); if (my !== token) return;
      mark(3); showScore(r); await wait(1500); if (my !== token) return;
      if (i < LOOP_ROUNDS.length - 1) { mark(4); await wait(900); if (my !== token) return; }
    }
    mark(-1); play.disabled = false;
  });
}

/* ---- copy buttons ---- */
function initCopy() {
  $$('[data-copy]').forEach((b) => b.addEventListener('click', async () => {
    const src = document.getElementById(b.dataset.copy);
    if (!src) return;
    const ok = await copyText(src.textContent.trim());
    toast(ok ? 'Copied' : 'Select the text and copy it by hand.');
  }));
}

/* ---- boot ---- */
function init() {
  initNav();
  initModeling();
  initCoach();
  initHero();
  initLab();
  initLoop();
  initCopy();
  requestAnimationFrame(loop);
}

if (typeof window !== 'undefined') window.BlenderAgentSite = { SCENES, getScene, renderScene, DEFAULT_FLAGS, matchScene, SIM, TOOL_GROUPS, coachAnalyze, coachInsert };
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
}
})();