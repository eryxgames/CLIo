// SPDX-License-Identifier: Apache-2.0
(function (root) {
'use strict';
var FS = 48000, C = 343, P0 = 101325, RHO = 1.204, TRAJ_HZ = 4000, TAU = Math.PI * 2;

/* ---------- helpers ---------- */
function rng(seed) {
  var a = seed | 0;
  return function () {
    a = (a + 0x6D2B79F5) | 0;
    var t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function clamp(x, a, b) { return x < a ? a : x > b ? b : x; }
function dbToLin(d) { return Math.pow(10, d / 20); }
function trimGain(d) { return d <= -40 ? 0 : dbToLin(d); }
function peakOf(L, R) {
  var p = 0, i, v;
  for (i = 0; i < L.length; i++) { v = L[i] < 0 ? -L[i] : L[i]; if (v > p) p = v; }
  if (R) for (i = 0; i < R.length; i++) { v = R[i] < 0 ? -R[i] : R[i]; if (v > p) p = v; }
  return p;
}
function scale(buf, g) { for (var i = 0; i < buf.length; i++) buf[i] *= g; }
function onePoleLP(buf, fc) {
  var a = Math.exp(-TAU * fc / FS), s = 0;
  for (var i = 0; i < buf.length; i++) { s = buf[i] + (s - buf[i]) * a; buf[i] = s; }
}
function onePoleHP(buf, fc) {
  var a = Math.exp(-TAU * fc / FS), s = 0;
  for (var i = 0; i < buf.length; i++) { s = buf[i] + (s - buf[i]) * a; buf[i] -= s; }
}
function biquadCoef(type, f, q, g) {
  var w = TAU * f / FS, cs = Math.cos(w), sn = Math.sin(w), al = sn / (2 * q), A = Math.pow(10, (g || 0) / 40);
  var b0, b1, b2, a0, a1, a2, sq = 2 * Math.sqrt(A) * al;
  if (type === 'lp') { b0 = (1 - cs) / 2; b1 = 1 - cs; b2 = b0; a0 = 1 + al; a1 = -2 * cs; a2 = 1 - al; }
  else if (type === 'hp') { b0 = (1 + cs) / 2; b1 = -(1 + cs); b2 = b0; a0 = 1 + al; a1 = -2 * cs; a2 = 1 - al; }
  else if (type === 'pk') { b0 = 1 + al * A; b1 = -2 * cs; b2 = 1 - al * A; a0 = 1 + al / A; a1 = -2 * cs; a2 = 1 - al / A; }
  else if (type === 'ls') {
    b0 = A * ((A + 1) - (A - 1) * cs + sq); b1 = 2 * A * ((A - 1) - (A + 1) * cs); b2 = A * ((A + 1) - (A - 1) * cs - sq);
    a0 = (A + 1) + (A - 1) * cs + sq; a1 = -2 * ((A - 1) + (A + 1) * cs); a2 = (A + 1) + (A - 1) * cs - sq;
  } else { /* hs */
    b0 = A * ((A + 1) + (A - 1) * cs + sq); b1 = -2 * A * ((A - 1) + (A + 1) * cs); b2 = A * ((A + 1) + (A - 1) * cs - sq);
    a0 = (A + 1) - (A - 1) * cs + sq; a1 = 2 * ((A - 1) - (A + 1) * cs); a2 = (A + 1) - (A - 1) * cs - sq;
  }
  return [b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0];
}
function biquad(buf, type, f, q, g) {
  var c = biquadCoef(type, f, q, g), z1 = 0, z2 = 0, x, y;
  for (var i = 0; i < buf.length; i++) {
    x = buf[i]; y = c[0] * x + z1; z1 = c[1] * x - c[3] * y + z2; z2 = c[2] * x - c[4] * y; buf[i] = y;
  }
}
/* Atmospheric absorption: about 1.5e-9 * f^2 dB per metre. Returns the -3 dB frequency after r metres. */
function airFc(r) { return Math.sqrt(3 / (1.5e-9 * Math.max(r, 1))); }
function airFilter(buf, r) {
  var fc = airFc(r);
  if (fc >= 20000) return;
  onePoleLP(buf, fc / 0.64); onePoleLP(buf, fc / 0.64);
}
/* Integrate an analytic pressure shape over each sample period (band-limits sharp shock fronts). */
function addShape(buf, t0, dur, fn) {
  var n0 = Math.max(0, Math.floor(t0 * FS)), n1 = Math.min(buf.length - 1, Math.ceil((t0 + dur) * FS)), OS = 8;
  for (var n = n0; n <= n1; n++) {
    var acc = 0;
    for (var k = 0; k < OS; k++) {
      var t = (n + (k + 0.5) / OS) / FS - t0;
      if (t >= 0 && t <= dur) acc += fn(t);
    }
    buf[n] += acc / OS;
  }
}
/* Direct path plus one ground bounce (source 1.5 m, ear 1.7 m), then air absorption. */
function postLayer(buf, r, ground) {
  var hs = 1.5, hl = 1.7;
  if (ground > 0) {
    var dDir = Math.hypot(r, hs - hl), dRef = Math.hypot(r, hs + hl);
    var dl = (dRef - dDir) / C * FS, g = ground * dDir / dRef;
    var cp = Float32Array.from(buf);
    onePoleLP(cp, 5000);
    var di = Math.floor(dl), fr = dl - di;
    for (var i = buf.length - 1; i > di; i--) buf[i] += g * (cp[i - di] * (1 - fr) + cp[i - di - 1] * fr);
  }
  airFilter(buf, r);
}

/* ---------- ballistics ---------- */
function cd(M) {
  if (M < 0.8) return 0.22;
  if (M < 1.1) return 0.22 + (M - 0.8) / 0.3 * 0.26;
  return 0.48 * Math.pow(1.1 / M, 0.55);
}
function trajectory(p) {
  var dt = 1 / TRAJ_HZ, d = p.cal / 1000, A = Math.PI * d * d / 4;
  var cdMul = (p.cdScale || 1) * (1 + 6 * p.tumble);
  var hasTarget = p.target !== 'none' && !(p.pathLen > 0);
  var xEnd = p.pathLen > 0 ? p.pathLen : hasTarget ? p.targetDist : p.D + clamp(40 * p.miss, 30, 1500);
  var maxN = Math.round(TRAJ_HZ * (p.maxT || 8));
  var xs = new Float64Array(maxN + 1), vs = new Float64Array(maxN + 1), T = new Float64Array(maxN + 1);
  var x = 0, v = p.swing ? p.v0 * 0.08 : p.v0, n = 0, hit = false;
  for (var i = 0; i <= maxN; i++) {
    xs[i] = x; vs[i] = v; T[i] = i * dt + Math.hypot(p.D - x, p.miss) / C; n = i + 1;
    if (x >= xEnd) { hit = hasTarget; break; }
    if (!p.swing && v < (p.vStop || 6)) break;
    if (p.swing) { v = p.v0 * Math.max(0.08, Math.sin(Math.PI * clamp(x / xEnd, 0, 1))); }
    else { v -= RHO * cd(v / C) * cdMul * A / (2 * p.mass) * v * v * dt; }
    x += v * dt;
  }
  return { n: n, x: xs, v: vs, T: T, hit: hit, xEnd: xEnd };
}
function posAt(tr, t) {
  var u = clamp(t * TRAJ_HZ, 0, tr.n - 1), i = Math.min(tr.n - 2, Math.floor(u)), f = u - i;
  if (tr.n < 2) return { x: tr.x[0], v: tr.v[0] };
  return { x: tr.x[i] + (tr.x[i + 1] - tr.x[i]) * f, v: tr.v[i] + (tr.v[i + 1] - tr.v[i]) * f };
}
function analyzeProj(p) {
  var tr = trajectory(p), n = tr.n, d = p.cal / 1000, i, out = { tr: tr };
  /* Shock arrival: earliest sound from the path, valid when the emitting point is supersonic. */
  var iMin = 0, iPass = n - 1;
  for (i = 1; i < n; i++) if (tr.T[i] < tr.T[iMin]) iMin = i;
  for (i = 0; i < n; i++) if (tr.x[i] >= p.D) { iPass = i; break; }
  out.passed = tr.x[n - 1] >= p.D;
  out.passT = tr.T[iPass]; out.passV = tr.v[iPass]; out.mach = tr.v[iPass] / C;
  out.strouhal = 0.2 * tr.v[iPass] / d;
  out.crack = null;
  if (iMin > 0 && iMin < n - 1 && tr.v[iMin] > C * 1.01) {
    var M = tr.v[iMin] / C, len = d * (p.lenRatio || 4), b = Math.max(p.miss, 0.2), m2 = M * M - 1;
    out.crack = {
      t: tr.T[iMin], x: tr.x[iMin], M: M, tau: iMin / TRAJ_HZ,
      /* Whitham far-field N-wave */
      peak: 0.53 * P0 * Math.pow(m2, 0.125) * d / (Math.pow(b, 0.75) * Math.pow(len, 0.25)),
      dur: 1.82 * M * Math.pow(b, 0.25) * d / (C * Math.pow(m2, 0.375) * Math.pow(len, 0.25))
    };
  }
  var r0 = Math.hypot(p.D, p.miss), E = 0.5 * p.mass * p.v0 * p.v0, e3 = Math.cbrt(E);
  out.r0 = r0; out.launchT = r0 / C; out.muzzleE = E;
  out.blast = null;
  if (p.launch === 'blast') {
    var rb = Math.max(r0, 1), cosT = r0 > 0.01 ? p.D / r0 : 0;
    out.blast = {
      t: r0 / C, r: rb,
      peak: 133 * e3 / rb * dbToLin(6 * cosT),
      T1: 0.00003 * e3 * (1 + 0.6 * Math.log10(1 + rb)),
      jetTau: 0.02 * Math.sqrt(e3 / 15), jetFc: 3000 / Math.sqrt(e3 / 15)
    };
  }
  out.hit = null;
  if (tr.hit) {
    var vh = tr.v[n - 1], xh = tr.x[n - 1], rh = Math.max(0.5, Math.hypot(p.D - xh, p.miss));
    out.hit = { tau: (n - 1) / TRAJ_HZ, t: (n - 1) / TRAJ_HZ + rh / C, x: xh, v: vh, r: rh, E: 0.5 * p.mass * vh * vh };
  }
  out.flight = (n - 1) / TRAJ_HZ;
  return out;
}

/* ---------- layer synthesis ---------- */
function blastBuf(b, rnd) {
  var T1 = b.T1, T2 = T1 * 6;
  var len = Math.ceil((0.06 + b.jetTau * 7 + T2 * 8) * FS) + 2400, buf = new Float32Array(len), i;
  /* Friedlander: instant rise, exponential decay, negative phase */
  addShape(buf, 0.0005, T1 * 10, function (t) { var u = t / T1; return b.peak * (1 - u) * Math.exp(-u); });
  /* slower gas-bubble pulse gives the thump its body */
  addShape(buf, 0.0005 + T1 * 0.5, T2 * 10, function (t) { var u = t / T2; return 0.35 * b.peak * (1 - u) * Math.exp(-u); });
  /* propellant jet noise */
  var a = Math.exp(-TAU * b.jetFc / FS), lp = 0, norm = 1 / Math.sqrt((1 - a) / (1 + a) / 3);
  var s0 = Math.round((0.0005 + T1 * 0.3) * FS);
  for (i = s0; i < len - 2400; i++) {
    var t = (i - s0) / FS, w = rnd() * 2 - 1;
    lp = w + (lp - w) * a;
    buf[i] += lp * norm * 0.16 * b.peak * Math.exp(-t / b.jetTau);
  }
  return buf;
}
function crackBuf(c) {
  var len = Math.ceil((c.dur + 0.02) * FS) + 2400, buf = new Float32Array(len);
  addShape(buf, 0.0005, c.dur, function (t) { return c.peak * (1 - 2 * t / c.dur); });
  return buf;
}

var MATERIALS = {
  steel:    { f0: 520, ratios: [1, 1.58, 2.24, 2.92, 3.6, 4.71, 5.4, 6.8, 8.93, 11.3, 13.3], t60: 1.7, slope: 0.22, contact: 0.00010, eff: 1.0,
              noise: { dur: 0.005, hp: 1500, lp: 16000, gain: 0.7 }, grains: null },
  wood:     { f0: 165, ratios: [1, 2.3, 3.9, 5.6, 8.1, 10.9], t60: 0.10, slope: 0.3, contact: 0.0005, eff: 0.7,
              noise: { dur: 0.018, hp: 300, lp: 5000, gain: 0.9 }, grains: { count: 7, spread: 0.12, type: 'noise', f: [1500, 6000], gain: 0.25 } },
  dirt:     { f0: 70, ratios: [1, 1.9], t60: 0.14, slope: 0.5, contact: 0.002, eff: 0.5,
              noise: { dur: 0.07, hp: 40, lp: 900, gain: 1.2 }, grains: { count: 60, spread: 0.45, type: 'noise', f: [1200, 7000], gain: 0.14 } },
  concrete: { f0: 900, ratios: [1, 1.7, 2.6, 3.9, 5.3], t60: 0.035, slope: 0.2, contact: 0.00018, eff: 0.85,
              noise: { dur: 0.009, hp: 800, lp: 14000, gain: 1.1 }, grains: { count: 35, spread: 0.4, type: 'noise', f: [2000, 9000], gain: 0.16 } },
  glass:    { f0: 1400, ratios: [1, 1.47, 2.09, 2.56, 3.4, 4.3, 5.9, 7.2], t60: 0.28, slope: 0.15, contact: 0.00008, eff: 0.8,
              noise: { dur: 0.004, hp: 2500, lp: 18000, gain: 0.8 }, grains: { count: 34, spread: 0.7, type: 'ping', f: [2200, 9500], gain: 0.22 } },
  string:   { f0: 96, ratios: [1, 2, 3.01, 4.03, 5.06, 6.1], t60: 0.3, slope: 0.35, contact: 0.0008, eff: 0.6,
              noise: { dur: 0.012, hp: 60, lp: 1300, gain: 0.6 }, grains: null }
};
/* Modal body hit by an impulse: decaying partials + broadband contact burst + debris grains. Pressure at 1 m.
   opt.maxModes / t60Scale / noGrains give a light version for the many small hits of debris and fragments. */
function modalHit(name, E, sizeScale, rnd, opt) {
  opt = opt || {};
  var m = matSpec(name), amp = 6 * m.eff * Math.sqrt(Math.max(E, 1e-6)), ts = opt.t60Scale || 1, light = !!opt.maxModes;
  /* a measured object: its own decays, shorter as the piece gets smaller and rings higher */
  var rhoT = m.t60s ? clamp(Math.pow(m.f0 * sizeScale / m.f1, -0.8), 0.05, 3) : 1;
  var useGrains = m.grains && !opt.noGrains, cut = light ? 0.85 : 1.15, slack = light ? 64 : 2400;
  var tail = Math.max(m.t60 * ts * rhoT * cut, useGrains ? m.grains.spread + 0.3 : 0, m.noise.dur * 4 + 0.01, 0.03);
  var len = Math.ceil(tail * FS) + slack, buf = new Float32Array(len), body = len - slack, k, i, gsum = 0, modes = [];
  var nm = light ? Math.min(opt.maxModes, m.ratios.length) : m.ratios.length;
  for (k = 0; k < nm; k++) {
    var f = m.f0 * sizeScale * m.ratios[k] * (1 + (rnd() - 0.5) * 0.07);
    if (f > 19000) continue;
    if (m.t60s) {
      var gm = m.gains[k] * (0.8 + 0.4 * rnd()) / (1 + Math.pow(f * m.contact * 3, 2));
      modes.push({ f: f, g: gm, t60: m.t60s[k] * ts * rhoT * (0.85 + 0.3 * rnd()) }); gsum += gm;
      continue;
    }
    var g = (0.5 + rnd()) / Math.sqrt(1 + k) / (1 + Math.pow(f * m.contact * 3, 2));
    modes.push({ f: f, g: g, t60: m.t60 * ts / (1 + m.slope * k) * (0.8 + 0.4 * rnd()) }); gsum += g;
  }
  modes.forEach(function (mo) {
    var w = TAU * mo.f / FS, R = Math.pow(10, -3 / (mo.t60 * FS)), c1 = 2 * R * Math.cos(w), c2 = R * R;
    var y1, y2, y, A = amp * 0.7 * mo.g / gsum, nn = Math.min(body, Math.ceil(mo.t60 * cut * FS));
    y = Math.sin(w) * R; /* R^n sin(w n), starting from zero */
    buf[1] += A * y; y2 = 0; y1 = y;
    for (i = 2; i < nn; i++) { y = c1 * y1 - c2 * y2; y2 = y1; y1 = y; buf[i] += A * y; }
  });
  var nb = new Float32Array(Math.ceil(m.noise.dur * 4 * FS) + 8);
  for (i = 0; i < nb.length; i++) nb[i] = (rnd() * 2 - 1) * Math.exp(-i / FS / (m.noise.dur / 3));
  onePoleHP(nb, m.noise.hp); onePoleLP(nb, m.noise.lp);
  var np = peakOf(nb) || 1;
  for (i = 0; i < nb.length && i < body; i++) buf[i] += nb[i] / np * amp * m.noise.gain;
  if (useGrains) {
    var G = m.grains;
    for (k = 0; k < G.count; k++) {
      var t0 = 0.01 + G.spread * Math.pow(rnd(), 1.8), ga = amp * G.gain * (0.3 + rnd()) * Math.exp(-t0 / (G.spread * 0.5));
      var gf = G.f[0] * Math.pow(G.f[1] / G.f[0], rnd()), s = Math.floor(t0 * FS), gd, j;
      if (G.type === 'ping') {
        gd = 0.03 + 0.12 * rnd(); var gw = TAU * gf / FS;
        for (j = 0; j < gd * 3 * FS && s + j < body; j++) buf[s + j] += ga * Math.sin(gw * j) * Math.exp(-j / FS / (gd / 3));
      } else {
        gd = 0.002 + 0.008 * rnd(); var st = 0, ca = Math.exp(-TAU * gf / FS);
        for (j = 0; j < gd * 4 * FS && s + j < body; j++) {
          var w2 = rnd() * 2 - 1; st = w2 + (st - w2) * ca;
          buf[s + j] += ga * (w2 - st * 0.7) * Math.exp(-j / FS / gd);
        }
      }
    }
  }
  return buf;
}

/* Aerodynamic wake, synthesised in emission time and re-timed to the ear (Doppler falls out of the geometry). */
var KW = 14;
function wakeLayer(p, tr, cutAtHit, rnd) {
  var n = tr.n, dur = (n - 1) / TRAJ_HZ, ns = Math.floor(dur * FS);
  if (ns < 64) return null;
  var d = p.cal / 1000, src = new Float32Array(ns), k, i;
  var lp = 0, bp = 0, br = 0, ph = 0, l1 = 0, l2 = 0, q = 1.1;
  var fadeIn = Math.min(ns * 0.2, 0.003 * FS), fadeOut = cutAtHit ? 0.001 * FS : ns * 0.18;
  var sizeAmp = Math.pow(d / 0.0114, 1.5) * (1 + 8 * p.tumble);
  for (k = 0; k < ns; k++) {
    var u = k / FS * TRAJ_HZ; i = Math.min(n - 2, Math.floor(u)); var f = u - i;
    var v = tr.v[i] + (tr.v[i + 1] - tr.v[i]) * f, x = tr.x[i] + (tr.x[i + 1] - tr.x[i]) * f;
    var dT = (tr.T[i + 1] - tr.T[i]) * TRAJ_HZ;
    var rate = 1 / Math.max(Math.abs(dT), 0.05);
    var r = Math.max(0.3, Math.hypot(p.D - x, p.miss));
    var w = rnd() * 2 - 1;
    /* vortex shedding: band centred on Strouhal frequency 0.2 v / d */
    var fc = clamp(0.2 * v / d, 40, 7500), fk = 2 * Math.sin(Math.PI * fc / FS);
    lp += fk * bp; var hp = w - lp - q * bp; bp += fk * hp;
    br = w + (br - w) * 0.6;
    var s = bp * Math.sqrt(1 / fk) * 0.9 + br * 0.5;
    if (p.tumble > 0) {
      ph += TAU * p.tumbleHz * Math.pow(Math.max(v, 1) / p.v0, 1.5) / FS;
      s = s * (1 + 0.9 * p.tumble * Math.sin(ph)) +
          p.tumble * 0.8 * (Math.sin(ph) + 0.5 * Math.sin(2 * ph) + 0.33 * Math.sin(3 * ph) + 0.2 * Math.sin(5 * ph));
    }
    var mm = v / C; s *= KW * (mm < 1.2 ? mm * mm * mm : 1.44 * mm) * sizeAmp * Math.min(rate, 4) / r;
    if (k < fadeIn) s *= k / fadeIn;
    if (k > ns - fadeOut) s *= (ns - k) / fadeOut;
    /* air absorption acts on received frequency, so scale the cutoff by the Doppler ratio */
    var a = Math.exp(-TAU * clamp(Math.min(airFc(r), 18000) / rate / 0.64, 30, 20000) / FS);
    l1 = s + (l1 - s) * a; l2 = l1 + (l2 - l1) * a;
    src[k] = l2;
  }
  return retime(src, ns, tr, p.D, p.miss, null);
}

/* Re-time an emission-domain signal to the ear: each path step maps to the stretch of output it arrives in. */
function retime(src, ns, tr, D, miss, fixedPan) {
  var n = tr.n, i, Tmin = Infinity, Tmax = -Infinity;
  for (i = 0; i < n; i++) { if (tr.T[i] < Tmin) Tmin = tr.T[i]; if (tr.T[i] > Tmax) Tmax = tr.T[i]; }
  var outN = Math.ceil((Tmax - Tmin) * FS) + 4, oL = new Float32Array(outN), oR = new Float32Array(outN), step = FS / TRAJ_HZ;
  for (i = 0; i < n - 1; i++) {
    var Ta = tr.T[i], Tb = tr.T[i + 1];
    if (Ta === Tb) continue;
    var lo = Math.min(Ta, Tb), hi = Math.max(Ta, Tb);
    var n0 = Math.ceil((lo - Tmin) * FS), n1 = Math.ceil((hi - Tmin) * FS) - 1;
    if (n1 < n0) continue;
    var xm = (tr.x[i] + tr.x[i + 1]) / 2, pan = fixedPan != null ? fixedPan : (xm - D) / (Math.hypot(xm - D, miss) || 1) * 0.9;
    var gl = Math.cos((pan + 1) * Math.PI / 4), gr = Math.sin((pan + 1) * Math.PI / 4);
    for (var nn = n0; nn <= n1; nn++) {
      var fr = (Tmin + nn / FS - Ta) / (Tb - Ta), ks = (i + fr) * step, k0 = Math.floor(ks);
      if (k0 < 0 || k0 >= ns - 1) continue;
      var sv = src[k0] + (src[k0 + 1] - src[k0]) * (ks - k0);
      oL[nn] += sv * gl; oR[nn] += sv * gr;
    }
  }
  return { L: oL, R: oR, t: Tmin };
}

/* ---------- reverb: 8-line feedback delay network ---------- */
function fdn(inL, inR, o) {
  var N = inL.length, K = o.delays.length, outL = new Float32Array(N), outR = new Float32Array(N), k, n;
  var len = o.delays.map(function (ms) { return Math.max(8, Math.round(ms * FS / 1000)); });
  var bufs = len.map(function (l) { return new Float32Array(l); }), idx = new Int32Array(K);
  var g = len.map(function (l) { return Math.pow(10, -3 * l / (o.rt60 * FS)); });
  var a = Math.exp(-TAU * o.damp / FS), lp = new Float64Array(K), pre = Math.round((o.pre || 0) * FS / 1000);
  for (n = 0; n < N; n++) {
    var m = n - pre, xl = m >= 0 ? inL[m] : 0, xr = m >= 0 ? inR[m] : 0, sum = 0, ol = 0, or = 0;
    for (k = 0; k < K; k++) { var v = bufs[k][idx[k]]; lp[k] = v + (lp[k] - v) * a; sum += lp[k]; }
    sum *= 2 / K;
    for (k = 0; k < K; k++) {
      bufs[k][idx[k]] = ((k & 1) ? xr : xl) + (lp[k] - sum) * g[k];
      if (++idx[k] >= len[k]) idx[k] = 0;
      var sg = (k & 2) ? -lp[k] : lp[k];
      if (k & 1) or += sg; else ol += sg;
    }
    outL[n] = ol * 0.5; outR[n] = or * 0.5;
  }
  (o.taps || []).forEach(function (t) {
    var dl = Math.round(t.ms * FS / 1000), gl = t.g * Math.cos((t.pan + 1) * Math.PI / 4), gr = t.g * Math.sin((t.pan + 1) * Math.PI / 4);
    for (n = 0; n + dl < N; n++) { var x = (inL[n] + inR[n]) * 0.5; outL[n + dl] += x * gl; outR[n + dl] += x * gr; }
  });
  return { L: outL, R: outR };
}
var ENVS = {
  none:   { name: 'Anechoic', rt60: 0 },
  field:  { name: 'Open field', delays: [83, 109, 131, 157, 193, 227, 263, 311], rt60: 1.4, damp: 2500, wet: -15 },
  forest: { name: 'Forest', delays: [23, 31, 41, 53, 67, 79, 97, 113], rt60: 0.9, damp: 1800, wet: -10 },
  urban:  { name: 'Street', delays: [37, 53, 71, 89, 113, 139, 167, 199], rt60: 1.8, damp: 5000, wet: -9,
            taps: [{ ms: 60, g: 0.5, pan: -0.7 }, { ms: 95, g: 0.4, pan: 0.6 }, { ms: 170, g: 0.3, pan: -0.3 }] },
  valley: { name: 'Mountain valley', delays: [211, 283, 353, 431, 509, 613, 727, 853], rt60: 4.5, damp: 1400, wet: -12,
            taps: [{ ms: 480, g: 0.35, pan: 0.5 }, { ms: 900, g: 0.25, pan: -0.6 }, { ms: 1500, g: 0.15, pan: 0.2 }] },
  indoor: { name: 'Indoor range', delays: [9, 14, 17, 22, 30, 38, 48, 56], rt60: 1.1, damp: 6000, wet: -5 },
  water:  { name: 'Deep water', delays: [131, 197, 263, 347, 431, 523, 617, 733], rt60: 3.8, damp: 900, wet: -9 },
  ir:     { name: 'Recorded room', ir: true }
};

/* ---------- shared bits for the event sources ---------- */
function shapedNoise(n, rnd, lpF, hpF) {
  var b = new Float32Array(n), s = 0;
  for (var i = 0; i < n; i++) { s = s * 0.995 + (rnd() * 2 - 1) * 0.1; b[i] = s; }
  if (lpF) { onePoleLP(b, lpF); onePoleLP(b, lpF); }
  if (hpF) onePoleHP(b, hpF);
  return b;
}
function toPeak(b, target) { var pk = peakOf(b); if (pk > 0) scale(b, target / pk); }

/* ---------- explosion ---------- */
/* Free-air blast by cube-root (Hopkinson-Cranz) scaling, W in kg TNT. Overpressure fit after Mills (1987). */
function blastParams(W, r) {
  var w3 = Math.cbrt(W), Z = Math.max(r, 0.3) / w3, Zc = Math.max(Z, 0.6);
  var kPa = 1772 / (Zc * Zc * Zc) - 114 / (Zc * Zc) + 108 / Zc;
  if (Zc > 40) kPa *= Math.sqrt(Math.log(40) / Math.log(Zc));
  return { Z: Z, peak: kPa * 1000, td: w3 * (1.2 + 2.2 * Math.log10(1 + Zc)) / 1000 };
}
function planExplosion(W, r, nFrag, nDebris, rnd) {
  var b = blastParams(W, r), w3 = Math.cbrt(W), i, frags = [], debris = [];
  for (i = 0; i < nFrag; i++) {
    var miss = Math.min(0.4 * Math.pow(60, rnd()), r * 0.95), cal = 4 + 14 * rnd(), d = cal / 1000;
    var fp = { v0: 250 + 1100 * Math.pow(rnd(), 1.5), cal: cal, mass: 7800 * Math.PI / 6 * d * d * d * 2, lenRatio: 1.5, cdScale: 1.3,
      tumble: 0.5 + 0.5 * rnd(), tumbleHz: 150 + 550 * rnd(), swing: false, pathLen: 0, D: Math.sqrt(r * r - miss * miss), miss: miss,
      launch: 'none', target: 'none', targetDist: 0, maxT: 2.5, vStop: 25 };
    frags.push({ p: fp, an: analyzeProj(fp), flip: rnd() < 0.5 });
  }
  var span = clamp(2.2 * Math.pow(W, 0.18), 1, 7), rho = 8 * w3, tFirst = Infinity;
  for (i = 0; i < nDebris; i++) {
    var t = 0.35 + span * Math.pow(rnd(), 1.4), dd = rho * Math.pow(rnd(), 0.7) * (0.3 + t / span), phi = TAU * rnd();
    var dx = dd * Math.cos(phi), dy = dd * Math.sin(phi), rj = Math.max(1, Math.hypot(r - dx, dy));
    var m = 0.005 * Math.pow(1 / (rnd() + 0.02), 1.2), vl = 9.81 * t / 2;
    debris.push({ t: t, dx: dx, dy: dy, r: rj, pan: clamp(dy / rj, -1, 1) * 0.9, m: m, E: 0.5 * m * vl * vl });
    if (t + rj / C < tFirst) tFirst = t + rj / C;
  }
  return { blast: b, t: r / C, frags: frags, debris: debris, span: span, tGround: r / 1500, tDebris: tFirst };
}
/* Fragments and debris are far below the blast physically; these offsets make them usable in a mix. */
var FRAG_BOOST_DB = 0, DEBRIS_BOOST_DB = 56;
function explosionLayers(pl, o, rnd, layers, ev, lab) {
  var b = pl.blast, W = o.W, buf, n, i, tB = o.t0 + pl.t;
  if (o.gBlast > 0) {
    buf = new Float32Array(Math.ceil((b.td * 14 + 0.02) * FS) + 2400);
    addShape(buf, 0.0005, b.td * 9, function (t) { var u = t / b.td; return b.peak * (1 - u) * Math.exp(-1.2 * u); });
    var t2 = b.td * 0.7;
    /* weaker second shock from the fireball re-collapsing */
    addShape(buf, 0.0005 + b.td * 3.5, t2 * 9, function (t) { var u = t / t2; return 0.18 * b.peak * (1 - u) * Math.exp(-1.2 * u); });
    postLayer(buf, o.r, o.ground);
    layers.push({ m: buf, t: tB, pan: o.pan, g: o.gBlast });
  }
  ev.push({ k: 'launch', t: tB, label: lab ? 'blast' : '' });
  if (o.gRumble > 0) {
    var tau = 0.18 * Math.pow(W, 0.25), fc = clamp(220 / Math.pow(W, 1 / 6), 35, 400);
    n = Math.ceil(tau * 6 * FS); buf = shapedNoise(n, rnd, fc, 18);
    for (i = 0; i < n; i++) { var t = i / FS; buf[i] *= (1 - Math.exp(-t / 0.015)) * Math.exp(-t / tau); }
    toPeak(buf, 0.3 * b.peak); airFilter(buf, o.r);
    layers.push({ m: buf, t: tB + b.td, pan: o.pan, g: o.gRumble });
    /* the ground carries the shock about four times faster than the air */
    var lead = pl.t - pl.tGround;
    if (lead > 0.06) {
      var gl = Math.min(lead, 0.9); n = Math.ceil((gl + 0.35) * FS); buf = shapedNoise(n, rnd, 45, 14);
      for (i = 0; i < n; i++) { var tt = i / FS; buf[i] *= tt < gl ? Math.pow(tt / gl, 2) : Math.exp(-(tt - gl) / 0.1); }
      toPeak(buf, 0.1 * b.peak);
      layers.push({ m: buf, t: tB - gl, pan: o.pan, g: o.gRumble });
      ev.push({ k: 'pass', t: tB - gl, label: lab ? 'ground' : '' });
    }
  }
  if (o.gFrag > 0) {
    var gF = o.gFrag * dbToLin(FRAG_BOOST_DB);
    pl.frags.forEach(function (f) {
      var a = f.an, sgn = f.flip ? -1 : 1;
      if (!a.passed) return;
      if (a.crack) {
        var rc = Math.hypot(f.p.D - a.crack.x, f.p.miss), cb = crackBuf(a.crack);
        postLayer(cb, rc, o.ground);
        layers.push({ m: cb, t: o.t0 + a.crack.t, pan: sgn * (a.crack.x - f.p.D) / rc * 0.9, g: gF });
      }
      var wk = wakeLayer(f.p, a.tr, false, rnd);
      if (wk) layers.push({ L: f.flip ? wk.R : wk.L, R: f.flip ? wk.L : wk.R, t: o.t0 + wk.t, g: gF });
    });
  }
  if (o.gDebris > 0 && pl.debris.length) {
    var gD = o.gDebris * dbToLin(DEBRIS_BOOST_DB);
    pl.debris.forEach(function (d) {
      var sc = clamp(Math.pow(0.05 / d.m, 1 / 3), 0.5, 3);
      var hb = o.grains ? grainHit(o.grains, d.E, sc, 1, rnd) : modalHit(MATERIALS[o.surface] ? o.surface : 'dirt', d.E, sc, rnd, { maxModes: 4, t60Scale: clamp(1 / sc, 0.3, 1.5), noGrains: true });
      scale(hb, 1 / d.r); airFilter(hb, d.r);
      layers.push({ m: hb, t: o.t0 + d.t + d.r / C, pan: clamp(d.pan + o.pan, -1, 1), g: gD });
    });
    ev.push({ k: 'impact', t: o.t0 + pl.tDebris, label: lab ? 'debris' : '' });
  }
}

/* ---------- implosion ---------- */
/* Rayleigh-Plesset collapse of a spherical cavity with residual gas and acoustic radiation damping.
   Far-field pressure is rho * d/dt(R^2 dR/dt) / r. Exact for liquids; for air it is an approximation. */
function planImplosion(p) {
  var water = p.imMedium === 'water', rho = water ? 1000 : RHO, c = water ? 1480 : C, gam = 1.4;
  var pInf = p.imDp * P0, pg0 = p.imGas * pInf, R0 = p.imR0;
  var tc = 0.915 * R0 * Math.sqrt(rho / (pInf - pg0));
  var Tsim = Math.min(1.6, tc * 14 + 0.02), N = Math.ceil(Tsim * FS) + 2, Q = new Float64Array(N);
  var R = R0, U = 0, t = 0, n = 0, steps = 0, Rmin = R0, tMin = 0, dtMax = 1 / (2 * FS), uMax = (water ? 2.5 : 1.2) * c, floor = 1e-5 * R0;
  var damp = (water ? 0.6 : 0.8) / tc, ct = [0], cr = [1], lastT = 0, lastR = 1, mins = [], prevU = 0;
  function acc(Rx, Ux) {
    var pg = pg0 * Math.pow(R0 / Rx, 3 * gam);
    return ((pg - pInf) / rho - 1.5 * Ux * Ux - 3 * gam * pg * Ux / (rho * c)) / Rx;
  }
  while (t < Tsim && steps < 1200000) {
    var dt = Math.min(dtMax, 0.004 * R / (Math.abs(U) + 1e-6));
    if (dt < 1e-10) dt = 1e-10;
    var a1 = acc(R, U), Rm = Math.max(floor, R + U * dt / 2), Um = U + a1 * dt / 2;
    var Rn = Math.max(floor, R + Um * dt), Un = clamp((U + acc(Rm, Um) * dt) * (1 - damp * dt), -uMax, uMax), tn = t + dt;
    while (n < N && n / FS <= tn) { var f = (n / FS - t) / dt, Ri = R + (Rn - R) * f, Ui = U + (Un - U) * f; Q[n++] = Ri * Ri * Ui; }
    if (prevU < 0 && Un >= 0 && mins.length < 6) mins.push(tn);
    if (Rn < Rmin) { Rmin = Rn; tMin = tn; }
    if (tn - lastT > Tsim / 500 || Math.abs(Rn / R0 - lastR) > 0.01) { ct.push(tn); cr.push(Rn / R0); lastT = tn; lastR = Rn / R0; }
    prevU = Un; R = Rn; U = Un; t = tn; steps++;
  }
  for (; n < N; n++) Q[n] = R * R * U;
  return { R0: R0, tc: tc, tMin: tMin, Rmin: Rmin, Tsim: Tsim, Q: Q, ct: ct, cr: cr, c: c, rho: rho, water: water,
    E: (pInf - pg0) * 4 / 3 * Math.PI * R0 * R0 * R0, period: mins.length > 1 ? mins[1] - mins[0] : 0, r: Math.max(p.imDist, R0 * 2) };
}
var SHELL_DENSITY = { glass: 2500, steel: 7800 };
function implosionLayers(pl, p, o, rnd, layers, ev, lab) {
  var r = pl.r, tA = o.t0 + r / pl.c, n = pl.Q.length - 1, i, buf = new Float32Array(n + 2400);
  for (i = 0; i < n; i++) buf[i] = pl.rho * (pl.Q[i + 1] - pl.Q[i]) * FS / r;
  var pk = peakOf(buf) || 1;
  function path(b) { if (pl.water) onePoleLP(b, 9000); else airFilter(b, r); }
  if (o.g1 > 0) { if (pl.water) onePoleLP(buf, 9000); else postLayer(buf, r, o.ground); layers.push({ m: buf, t: tA, pan: o.pan, g: o.g1 }); }
  ev.push({ k: 'crack', t: tA + pl.tMin, label: lab ? 'collapse' : '' });
  if (p.imShell === 'none') return;
  /* shell layers are levelled against the collapse pulse rather than measured */
  var sc = clamp(Math.pow(0.15 / pl.R0, 0.8), 0.2, 4), eff = 6 * MATERIALS[p.imShell].eff;
  if (o.g2 > 0 && p.imGroan > 0.05) {
    var gb = groanBuf(DS[p.imShell].groan, p.imShell, sc, p.imGroan, rnd);
    toPeak(gb, pk * 0.05); path(gb);
    layers.push({ m: gb, t: tA - p.imGroan, pan: o.pan, g: o.g2 }); ev.push({ k: 'pass', t: tA - p.imGroan, label: lab ? 'stress' : '' });
  }
  if (o.g3 > 0) {
    var fb = modalHit(p.imShell, 1, sc, rnd); toPeak(fb, pk * 0.3); path(fb);
    layers.push({ m: fb, t: tA, pan: o.pan, g: o.g3 });
    var cnt = p.imShell === 'steel' ? 14 : 24, win = Math.max(pl.tMin * 1.8, 0.02);
    for (i = 0; i < cnt; i++) {
      var cb = modalHit(p.imShell, 1, sc * (1.2 + 2.5 * rnd()), rnd, { maxModes: 4, t60Scale: 0.5, noGrains: true });
      toPeak(cb, pk * 0.12 * (0.3 + rnd())); path(cb);
      layers.push({ m: cb, t: tA + win * rnd(), pan: clamp(o.pan + (rnd() - 0.5) * 0.6, -1, 1), g: o.g3 });
    }
  }
  if (o.g4 > 0 && !pl.water) {
    var mass = 4 * Math.PI * pl.R0 * pl.R0 * 0.003 * SHELL_DENSITY[p.imShell];
    var dp = planDestruction({ mat: p.imShell, mass: mass, height: 1, pieces: p.imShell === 'glass' ? 30 : 8, dist: r, spread: pl.R0 * 4 }, rnd);
    var big = eff * Math.sqrt(dp.Emax) / r;
    fragmentLayers(dp, p.imShell, o.t0 + pl.tMin, o.g4 * pk * 0.15 / big, o.pan, rnd, layers);
    ev.push({ k: 'impact', t: tA + pl.tMin + dp.tFirst, label: lab ? 'debris' : '' });
  }
}

/* ---------- destruction ---------- */
var DS = {
  glass:    { e: 0.25, brittle: 1.0, groan: 'tick', fine: 3 },
  wood:     { e: 0.35, brittle: 0.35, groan: 'creak', fine: 1 },
  concrete: { e: 0.15, brittle: 0.6, groan: 'rumble', fine: 2, rubble: true },
  steel:    { e: 0.45, brittle: 0.15, groan: 'groan', fine: 1 }
};
/* Break-up plan: power-law piece masses, release spread over the fracture time, free fall, bounces by restitution. */
function planDestruction(o, rnd) {
  var d = DS[o.mat], n = Math.max(1, Math.round(o.pieces)), i, ws = [], sum = 0, frs = [], g = 9.81;
  var Tfrac = (0.04 + 0.25 * Math.log10(1 + o.mass)) * (1.3 - d.brittle * 0.6), tEnd = 0, tFirst = Infinity, Emax = 0, big = 0, lands = [];
  for (i = 0; i < n; i++) { var w = Math.pow(rnd() + 0.03, -0.9); ws.push(w); sum += w; }
  for (i = 0; i < n; i++) {
    var m = o.mass * 0.85 * ws[i] / sum, h = o.height * (0.15 + 0.85 * rnd()), t0 = Tfrac * Math.pow(rnd(), 1.5), v = Math.sqrt(2 * g * h);
    var x = o.spread * (rnd() * 2 - 1), r = Math.max(1, Math.hypot(o.dist, x)), tt = t0 + v / g, vb = v, hits = [{ t: tt, E: m * g * h, v: v }];
    for (var b = 0; b < 3; b++) {
      vb *= d.e * (0.7 + 0.6 * rnd()); var dt = 2 * vb / g;
      if (dt < 0.03) break;
      tt += dt; hits.push({ t: tt, E: 0.5 * m * vb * vb, v: vb });
    }
    if (tt > tEnd) tEnd = tt;
    if (hits[0].t < tFirst) tFirst = hits[0].t;
    if (hits[0].E > Emax) Emax = hits[0].E;
    if (m > big) big = m;
    lands.push(hits[0].t);
    frs.push({ m: m, h: h, t0: t0, x: x, r: r, pan: x / r * 0.9, hits: hits, sc: clamp(Math.pow(0.2 / m, 1 / 3), 0.25, 5) });
  }
  lands.sort(function (a, b2) { return a - b2; });
  var scs = frs.map(function (f) { return f.sc; }).sort(function (a, b2) { return a - b2; });
  var nCr = Math.round(clamp(n * 1.5 * d.brittle + 6, 6, 160)), cracks = [], bs = clamp(Math.pow(0.2 / o.mass, 1 / 3), 0.25, 5);
  for (i = 0; i < nCr; i++) cracks.push({ t: Tfrac * Math.pow(rnd(), 2), E: o.mass * g * o.height * 0.002 * (0.2 + rnd()), sc: Math.min(6, bs * (1.5 + 3 * rnd())), x: o.spread * (rnd() - 0.5) });
  return { frs: frs, cracks: cracks, Tfrac: Tfrac, E: o.mass * g * o.height, tEnd: tEnd, tFirst: tFirst, tMed: lands[lands.length >> 1], Emax: Emax, big: big, baseSc: bs, n: n, scMed: scs[scs.length >> 1] || 1 };
}
/* Stick-slip before failure: a jittered slip train that speeds up toward the break and rings the body's modes. */
function groanBuf(type, mat, sc, dur, rnd) {
  var N = Math.ceil(dur * FS), tot = N + Math.ceil(0.4 * FS), buf = new Float32Array(tot + 64), M = matSpec(mat), k, n;
  var base = { groan: 0.5, creak: 0.06, rumble: 0.08, tick: 0.04 }[type], rate0 = { groan: 28, creak: 140, rumble: 16, tick: 3 }[type];
  var c1 = [], c2 = [], y1 = [], y2 = [], gg = [];
  for (k = 0; k < Math.min(5, M.ratios.length); k++) {
    var f = M.f0 * sc * M.ratios[k] * (1 + (rnd() - 0.5) * 0.1); if (f > 12000) break;
    var R = Math.pow(10, -3 / (base / (1 + 0.3 * k) * FS));
    c1.push(2 * R * Math.cos(TAU * f / FS)); c2.push(R * R); y1.push(0); y2.push(0); gg.push(1 / (1 + k));
  }
  var ph = rnd(), K = c1.length;
  for (n = 0; n < tot; n++) {
    var x = 0, u = Math.min(1, n / N), ts = n / FS;
    if (n < N) {
      var gate = type === 'creak' ? (Math.sin(TAU * 1.3 * ts + 2 * Math.sin(TAU * 0.37 * ts)) > -0.2 ? 1 : 0) : 1;
      ph += rate0 * (1 + 2.5 * u * u * u) / FS;
      if (ph >= 1) { ph -= 1 + (rnd() - 0.5) * 0.3; x = gate * (0.5 + rnd()) * (0.25 + 0.75 * u); }
    }
    var y = 0;
    for (k = 0; k < K; k++) { var v = c1[k] * y1[k] - c2[k] * y2[k] + x * gg[k]; y2[k] = y1[k]; y1[k] = v; y += v; }
    buf[n] = y;
  }
  if (type === 'rumble') {
    var nz = shapedNoise(tot, rnd, 160, 20), pk = peakOf(buf) || 1; toPeak(nz, pk * 0.8);
    for (n = 0; n < tot; n++) { var uu = Math.min(1, n / N); buf[n] += nz[n] * uu * uu * (n < N ? 1 : Math.exp(-(n - N) / FS / 0.08)); }
  }
  return buf;
}
function fragmentLayers(pl, mat, t0, gain, pan, rnd, layers, grains) {
  pl.frs.forEach(function (f) {
    f.hits.forEach(function (h, bi) {
      /* a measured object scales its own decays with size; the built-in materials use this rule of thumb */
      var ts = typeof mat !== 'string' ? (bi ? 0.8 : 1) : clamp(Math.pow(f.sc, -0.6), 0.25, mat === 'steel' ? 0.7 : 1.5) * (bi ? 0.8 : 1);
      var hb = grains ? grainHit(grains, h.E, f.sc, pl.scMed, rnd) : modalHit(mat, h.E, f.sc, rnd, { maxModes: f.m > 1 ? 6 : 4, t60Scale: ts, noGrains: true });
      scale(hb, 1 / f.r); airFilter(hb, f.r);
      layers.push({ m: hb, t: t0 + h.t + f.r / C, pan: clamp(f.pan + pan, -1, 1), g: gain });
    });
  });
}
function destructionLayers(pl, p, o, rnd, layers, ev, lab) {
  var mat = dsMaterial(p), d = DS[p.dsMat === 'measured' ? p.dsLike : p.dsMat], r = Math.max(1, p.dsDist), tA = o.t0 + r / C, buf, i;
  var grains = p.dsDebris === 'rec' ? getGrains(p.grAsset) : null;
  var trigPk = 6 * matSpec(mat).eff * Math.sqrt(pl.E * 0.25) / r;
  if (o.g1 > 0) {
    buf = modalHit(mat, pl.E * 0.25, pl.baseSc, rnd); scale(buf, 1 / r); postLayer(buf, r, o.ground);
    layers.push({ m: buf, t: tA, pan: o.pan, g: o.g1 });
    pl.cracks.forEach(function (c) {
      var cb = modalHit(mat, c.E, c.sc, rnd, { maxModes: 3, t60Scale: 0.4, noGrains: true }), rr = Math.hypot(r, c.x);
      scale(cb, 1 / rr); airFilter(cb, rr);
      layers.push({ m: cb, t: o.t0 + c.t + rr / C, pan: clamp(o.pan + c.x / rr * 0.9, -1, 1), g: o.g1 });
    });
  }
  ev.push({ k: 'crack', t: tA, label: lab ? 'break' : '' });
  if (o.g2 > 0 && p.dsGroan > 0.05) {
    buf = groanBuf(d.groan, mat, pl.baseSc, p.dsGroan, rnd); toPeak(buf, trigPk * 0.2); airFilter(buf, r);
    layers.push({ m: buf, t: tA - p.dsGroan, pan: o.pan, g: o.g2 }); ev.push({ k: 'pass', t: tA - p.dsGroan, label: lab ? 'stress' : '' });
  }
  if (o.g4 > 0) fragmentLayers(pl, mat, o.t0, o.g4, o.pan, rnd, layers, grains);
  ev.push({ k: 'impact', t: tA + pl.tFirst, label: lab ? 'landing' : '' });
  if (o.g3 > 0) {
    /* fine debris scattered by each first landing */
    pl.frs.forEach(function (f) {
      for (var k = 0; k < d.fine; k++) {
        var fe = f.hits[0].E * 0.01 * (0.2 + rnd()), fsc = Math.min(6, f.sc * (2 + 3 * rnd()));
        var fb = grains ? grainHit(grains, fe, fsc, pl.scMed, rnd) : modalHit(mat, fe, fsc, rnd, { maxModes: 3, t60Scale: 0.35, noGrains: true });
        scale(fb, 1 / f.r); airFilter(fb, f.r);
        layers.push({ m: fb, t: o.t0 + f.hits[0].t + 0.02 + 0.33 * rnd() + f.r / C, pan: clamp(f.pan + o.pan + (rnd() - 0.5) * 0.3, -1, 1), g: o.g3 });
      }
    });
    if (d.rubble) {
      var n = Math.ceil((pl.tEnd + 1.2) * FS), env = new Float32Array(n), nz = shapedNoise(n, rnd, 1400, 90), s = 0, a = Math.exp(-1 / (0.25 * FS));
      pl.frs.forEach(function (f) { var ix = Math.floor(f.hits[0].t * FS); if (ix < n) env[ix] += Math.sqrt(f.hits[0].E); });
      for (i = 0; i < n; i++) { s = s * a + env[i]; nz[i] *= s; }
      onePoleLP(nz, 3000); toPeak(nz, trigPk * 0.25); airFilter(nz, r);
      layers.push({ m: nz, t: tA, pan: o.pan, g: o.g3 });
    }
  }
}

/* ---------- projectile scene ---------- */
var LAUNCH_MODAL = { string: ['string', 1], ricSteel: ['steel', 2.6], ricStone: ['concrete', 2.6] };
function projLayers(an, p, o, rnd, layers, ev, lab) {
  var tr = an.tr, buf, g, t0 = o.t0;
  function L(s) { return lab ? s : ''; }
  var pan0 = an.r0 > 0.01 ? -p.D / an.r0 * 0.9 : 0;
  g = o.g2;
  if (an.blast && g > 0) {
    buf = blastBuf(an.blast, rnd); postLayer(buf, an.blast.r, p.ground);
    layers.push({ m: buf, t: t0 + an.blast.t, pan: pan0, g: g }); ev.push({ k: 'launch', t: t0 + an.blast.t, label: L('thump') });
  } else if (LAUNCH_MODAL[p.launch] && g > 0) {
    var lm = LAUNCH_MODAL[p.launch], r1 = Math.max(an.r0, 1);
    buf = modalHit(lm[0], an.muzzleE * lm[1], Math.pow(0.008 / (p.cal / 1000), 0.3), rnd);
    scale(buf, 1 / r1); postLayer(buf, r1, p.ground);
    layers.push({ m: buf, t: t0 + an.launchT, pan: pan0, g: g }); ev.push({ k: 'launch', t: t0 + an.launchT, label: L(lm[0] === 'string' ? 'release' : 'strike') });
  }
  g = o.g1;
  if (an.crack && g > 0) {
    var rc = Math.hypot(p.D - an.crack.x, p.miss);
    buf = crackBuf(an.crack); postLayer(buf, rc, p.ground);
    layers.push({ m: buf, t: t0 + an.crack.t, pan: (an.crack.x - p.D) / rc * 0.9, g: g }); ev.push({ k: 'crack', t: t0 + an.crack.t, label: L('crack') });
  }
  g = o.g3;
  if (g > 0) {
    var wk = wakeLayer(p, tr, !!an.hit, rnd);
    if (wk) { layers.push({ L: wk.L, R: wk.R, t: t0 + wk.t, g: g }); if (an.passed) ev.push({ k: 'pass', t: t0 + an.passT, label: L('pass') }); }
  }
  g = o.g4;
  if (an.hit && g > 0) {
    var hp = (an.hit.x - p.D) / an.hit.r * 0.9;
    buf = modalHit(p.target, an.hit.E, Math.pow(0.008 / (p.cal / 1000), 0.3), rnd);
    scale(buf, 1 / an.hit.r); postLayer(buf, an.hit.r, p.ground * 0.5);
    layers.push({ m: buf, t: t0 + an.hit.t, pan: hp, g: g }); ev.push({ k: 'impact', t: t0 + an.hit.t, label: L('impact') });
    if (an.pay) explosionLayers(an.pay, { W: p.payload, r: an.hit.r, surface: p.target, t0: t0 + an.hit.tau, pan: hp, ground: p.ground,
      gBlast: g, gRumble: g, gFrag: g, gDebris: g }, rnd, layers, ev, lab);
  }
}

/* ---------- sustained sources that move: synthesise in emission time, then re-time to the ear ---------- */
function movingSource(tr, D, miss, gen, fixedPan) {
  var n = tr.n, ns = Math.floor((n - 1) / TRAJ_HZ * FS);
  if (ns < 64) return null;
  var src = new Float32Array(ns), l1 = 0, l2 = 0, k, i, f;
  for (k = 0; k < ns; k++) {
    var u = k / FS * TRAJ_HZ; i = Math.min(n - 2, Math.floor(u)); f = u - i;
    var x = tr.x[i] + (tr.x[i + 1] - tr.x[i]) * f, dT = (tr.T[i + 1] - tr.T[i]) * TRAJ_HZ, rate = 1 / Math.max(Math.abs(dT), 0.05);
    var r = Math.max(1, Math.hypot(D - x, miss)), s = gen(k, i, f, x, r) / r;
    var a = Math.exp(-TAU * clamp(Math.min(airFc(r), 18000) / rate / 0.64, 30, 20000) / FS);
    l1 = s + (l1 - s) * a; l2 = l1 + (l2 - l1) * a; src[k] = l2;
  }
  return retime(src, ns, tr, D, miss, fixedPan);
}
function shockFromTraj(tr, miss, d, lenRatio) {
  var n = tr.n, iMin = 0, i;
  for (i = 1; i < n; i++) if (tr.T[i] < tr.T[iMin]) iMin = i;
  if (!(iMin > 0 && iMin < n - 1 && tr.v[iMin] > C * 1.01)) return null;
  var M = tr.v[iMin] / C, len = d * lenRatio, b = Math.max(miss, 0.2), m2 = M * M - 1;
  return { t: tr.T[iMin], x: tr.x[iMin], M: M, tau: iMin / TRAJ_HZ,
    peak: 0.53 * P0 * Math.pow(m2, 0.125) * d / (Math.pow(b, 0.75) * Math.pow(len, 0.25)),
    dur: 1.82 * M * Math.pow(b, 0.25) * d / (C * Math.pow(m2, 0.375) * Math.pow(len, 0.25)) };
}
function passInfo(tr, D, out) {
  var n = tr.n, iPass = n - 1, i;
  for (i = 0; i < n; i++) if (tr.x[i] >= D) { iPass = i; break; }
  out.passed = tr.x[n - 1] >= D; out.passT = tr.T[iPass]; out.passV = tr.v[iPass]; out.mach = tr.v[iPass] / C;
  out.flight = (n - 1) / TRAJ_HZ;
}
/* A filter applied to one period of a loop must itself come out periodic: run it over two periods, keep the second. */
function periodicApply(buf, fn) {
  var n = buf.length, t = new Float32Array(2 * n); t.set(buf); t.set(buf, n); fn(t);
  return t.slice(n);
}
function tile3(b) { var n = b.length, t = new Float32Array(3 * n); t.set(b); t.set(b, n); t.set(b, 2 * n); return t; }
var LOOP_S = 4;

/* ---------- jets and rockets ---------- */
/* Jet mixing noise: broad hump around the Strouhal peak, about 6 dB per octave either side. Unit rms. */
function jetNoise(n, fpk, rnd, periodic) {
  var w = new Float32Array(n), out = new Float32Array(n), a1 = Math.exp(-TAU * Math.min(fpk * 1.5, 16000) / FS), a2 = Math.exp(-TAU * fpk * 0.5 / FS);
  var lp = 0, hp = 0, i, pass, e = 0;
  for (i = 0; i < n; i++) w[i] = rnd() * 2 - 1;
  for (pass = periodic ? 0 : 1; pass < 2; pass++) for (i = 0; i < n; i++) { lp = w[i] + (lp - w[i]) * a1; hp = lp + (hp - lp) * a2; out[i] = lp - hp; }
  for (i = 0; i < n; i++) e += out[i] * out[i];
  scale(out, 1 / (Math.sqrt(e / n) || 1));
  return out;
}
/* Crackle of a supersonic exhaust: sparse, steep, positive-skewed pressure spikes. Unit rms. */
function crackleNoise(n, fpk, rnd, periodic) {
  var fx = clamp(6 * fpk, 900, 5000), dec = Math.exp(-TAU * fx / FS), rate = 0.25 * fx / FS, imp = new Float32Array(n), out = new Float32Array(n);
  var s = 0, h = 0, a = Math.exp(-TAU * fx / 4 / FS), i, pass, e = 0;
  for (i = 0; i < n; i++) if (rnd() < rate) imp[i] = -Math.log(rnd() + 1e-9);
  for (pass = periodic ? 0 : 1; pass < 2; pass++) for (i = 0; i < n; i++) { s = s * dec + imp[i]; h = s + (h - s) * a; out[i] = s - h; }
  for (i = 0; i < n; i++) e += out[i] * out[i];
  scale(out, 1 / (Math.sqrt(e / n) || 1));
  return out;
}
/* Path from thrust, mass and drag. Modes: launch from rest, fly-by at constant speed, landing with a braking burn. */
function trajThrust(q) {
  var dt = 1 / TRAJ_HZ, maxN = Math.round(TRAJ_HZ * q.maxT), xs = new Float64Array(maxN + 1), vs = new Float64Array(maxN + 1), T = new Float64Array(maxN + 1), th = new Float32Array(maxN + 2);
  var A = Math.PI * q.dia * q.dia / 4, mdot = q.F / q.Ue, m = q.m0, mMin = 0.2 * q.m0, g = q.vertical ? 9.81 : 0;
  var x = 0, v = 0, n = 0, hit = false, i, t, thr = 0, iBurn = -1, iCut = -1, vTd = 0, mode = q.mode, xStop = Infinity, post = -1, vmax = 0;
  /* a fly-by is trimmed to about four seconds of approach and five of departure */
  if (mode === 'flyby') { v = q.v0; thr = 1; xStop = q.D + Math.min(clamp(25 * q.miss, 30, 2000), q.v0 * 5); x = Math.max(0, q.D - q.v0 * 4); iBurn = 0; }
  if (mode === 'landing') v = q.v0;
  var vT = 1.5, burning = false;
  for (i = 0; i <= maxN; i++) {
    t = i * dt;
    if (mode === 'launch') {
      if (iBurn < 0) iBurn = 0;
      if (t < q.burn && m > mMin) thr = Math.min(1, t / q.ramp); else { if (iCut < 0) iCut = i; thr = Math.max(0, thr - dt / 0.06); }
    } else if (mode === 'landing') {
      if (post >= 0) thr = Math.max(0, thr - dt / 0.25);
      else {
        /* braking burn: throttle to the deceleration that reaches touchdown speed exactly at the pad */
        var aReq = Math.max(0, v * v - vT * vT) / (2 * Math.max(q.D - x, 0.05)), aMax = Math.max(0.5, q.F / m - g);
        if (!burning && aReq >= 0.85 * aMax) { burning = true; iBurn = i; }
        if (burning) { var want = clamp(m * (aReq + g) / q.F, 0.12, 1); thr += clamp(want - thr, -dt / q.ramp, dt / q.ramp); }
      }
    }
    xs[i] = x; vs[i] = v; th[i] = thr; T[i] = t + Math.hypot(q.D - x, q.miss) / C; n = i + 1;
    if (v > vmax) vmax = v;
    if (post >= 0) { if (++post > 0.4 * TRAJ_HZ) break; continue; }
    if (mode === 'landing') {
      if (x >= q.D) { hit = true; vTd = v; post = 0; x = q.D; v = 0; if (iCut < 0) iCut = i; continue; }
      if (burning) { v += (g - q.F * thr / m) * dt; if (v < vT) v = vT; m = Math.max(mMin, m - mdot * thr * dt); }
      x += v * dt; if (x > q.D) x = q.D;
    } else if (mode === 'flyby') {
      if (q.hasTarget && x >= q.targetDist) { hit = true; vTd = v; break; }
      if (x >= xStop) break;
      x += v * dt;
    } else {
      if (q.hasTarget && x >= q.targetDist) { hit = true; vTd = v; break; }
      if (iCut >= 0 && thr <= 0 && !q.hasTarget) break;
      var a = (q.F * thr - 0.5 * RHO * 0.35 * A * v * v) / m - g;
      if (x <= 0 && a < 0) { a = 0; v = 0; }
      v += a * dt; x += v * dt; if (x < 0) { x = 0; v = 0; }
      m = Math.max(mMin, m - mdot * thr * dt);
      if (iCut >= 0 && q.hasTarget && v < 5) break;
    }
  }
  th[n] = th[n - 1];
  return { n: n, x: xs, v: vs, T: T, th: th, hit: hit, iBurn: Math.max(0, iBurn), iCut: iCut, vTd: vTd, vmax: vmax, mEnd: m };
}
/* Acoustic output from mechanical jet power: efficiency rises steeply with exhaust Mach number and levels off near 0.5 percent. */
function planRocket(p, grnd) {
  var mode = p.rkMode, F = p.rkThrust, Ue = p.rkUe, De = p.rkNozzle, Mj = Ue / C, vert = p.rkPath === 'vertical';
  var eta = Math.min(0.005, 1e-4 * Math.pow(Mj, 5)), Pm = 0.5 * F * Ue, Wa = eta * Pm, p1 = Math.sqrt(Wa * RHO * C / (4 * Math.PI));
  var fpk = clamp(clamp(0.2 / Mj, 0.03, 0.2) * Ue / De, 25, 9000), g = vert ? 9.81 : 0;
  var out = { F: F, Ue: Ue, De: De, Mj: Mj, eta: eta, Pm: Pm, Wa: Wa, p1: p1, fpk: fpk, mode: mode, vert: vert,
    crk: p.rkCrackle * clamp((Mj - 1.2) / 1.5, 0, 1), accel: F / p.rkMass - g, tr: null, crack: null, hit: null, pay: null };
  if (mode === 'static') { out.r = Math.max(p.miss, 1); return out; }
  var hasTarget = mode !== 'landing' && p.target !== 'none';
  var tr = trajThrust({ mode: mode, F: F, Ue: Ue, m0: p.rkMass, burn: p.rkBurn, v0: p.rkV0, dia: De * 1.4, D: p.D, miss: p.miss, vertical: vert,
    hasTarget: hasTarget, targetDist: p.targetDist, ramp: clamp(0.02 + 0.08 * Math.sqrt(De), 0.02, 0.6),
    maxT: mode === 'launch' ? Math.min(14, p.rkBurn + (hasTarget ? 8 : 0.5)) : 14 });
  out.tr = tr; passInfo(tr, p.D, out);
  out.r0 = Math.hypot(p.D, p.miss); out.launchT = out.r0 / C;
  out.crack = shockFromTraj(tr, p.miss, De * 1.4, 8);
  if (tr.hit) {
    var xh = tr.x[tr.n - 1], tau = (tr.n - 1) / TRAJ_HZ, rh = Math.max(0.5, Math.hypot(p.D - xh, p.miss));
    if (mode === 'landing') { for (var i = 0; i < tr.n; i++) if (tr.x[i] >= p.D) { tau = i / TRAJ_HZ; break; } }
    out.hit = { tau: tau, t: tau + rh / C, x: xh, v: tr.vTd, r: rh, E: 0.5 * tr.mEnd * tr.vTd * tr.vTd };
    if (mode !== 'landing' && p.payload >= 0.01) out.pay = planExplosion(p.payload, rh, Math.round(p.exFrags), Math.round(p.exDebris), grnd);
  }
  return out;
}
function ignitionBuf(rk, rnd, sign) {
  var td = clamp(rk.De / C * 4, 0.0006, 0.04), fw = clamp(0.5 * rk.fpk, 20, 220), n = Math.ceil((td * 10 + 4 / fw + 0.05) * FS), buf = new Float32Array(n + 2400), i;
  addShape(buf, 0.0005, td * 9, function (t) { var u = t / td; return sign * 2.5 * rk.p1 * (1 - u) * Math.exp(-u); });
  for (i = 0; i < n; i++) { var t = i / FS; buf[i] += sign * 1.5 * rk.p1 * Math.sin(TAU * fw * t) * Math.exp(-t * fw / 1.5) * (1 - Math.exp(-t / 0.002)); }
  var nb = shapedNoise(Math.round(0.04 * FS), rnd, 2500, 60);
  for (i = 0; i < nb.length; i++) nb[i] *= Math.exp(-i / FS / 0.012);
  toPeak(nb, 0.8 * rk.p1);
  for (i = 0; i < nb.length; i++) buf[i] += nb[i];
  return buf;
}
function rocketLayers(rk, p, o, rnd, layers, ev, lab) {
  var tr = rk.tr, t0 = o.t0, ns = Math.floor((tr.n - 1) / TRAJ_HZ * FS), buf;
  function Lb(s) { return lab ? s : ''; }
  function panAt(x, r) { return rk.vert || r < 0.01 ? 0 : (x - p.D) / r * 0.9; }
  if (ns >= 64 && (o.g1 > 0 || o.g3 > 0)) {
    var nz = jetNoise(ns, rk.fpk, rnd, false), ck = rk.crk > 0 ? crackleNoise(ns, rk.fpk, rnd, false) : null;
    var exS = rk.mode === 'landing' ? 1 : -1, fch = clamp(60 / Math.sqrt(rk.De), 25, 400), cph = 0, wph = 0, rough = 0, fw = p.rkWhineHz;
    var wk = movingSource(tr, p.D, p.miss, function (k, i, f, x, r) {
      var thr = tr.th[i] + (tr.th[i + 1] - tr.th[i]) * f;
      if (thr <= 0.0005) return 0;
      /* loudest about 45 degrees off the exhaust axis */
      var dir = dbToLin(6 * (exS * (p.D - x) / r * 0.697 + p.miss / r * 0.717) - 3);
      var h = rk.vert ? (rk.mode === 'landing' ? p.D - x : x) : 1e9, ge = 1 + Math.exp(-Math.max(0, h) / (6 * rk.De));
      rough += ((rnd() * 2 - 1) - rough) * 0.0008; cph += TAU * fch / FS; wph += TAU * fw * (0.6 + 0.4 * thr) / FS;
      var s = (nz[k] * (1 - 0.5 * rk.crk) + (ck ? ck[k] * rk.crk : 0)) * (1 + 9 * rough) * (1 + 0.6 * p.rkChug * Math.sin(cph + 30 * rough));
      var wh = p.rkWhine > 0 ? p.rkWhine * 0.35 * thr * (Math.sin(wph) + 0.5 * Math.sin(2 * wph + 1) + 0.4 * Math.sin(1.37 * wph)) : 0;
      return rk.p1 * dir * (o.g1 * s * Math.sqrt(thr) * ge + o.g3 * wh);
    }, rk.vert ? 0 : null);
    if (wk) layers.push({ L: wk.L, R: wk.R, t: t0 + wk.t, g: 1 });
  }
  if (rk.mode !== 'flyby') {
    var xi = tr.x[tr.iBurn], ri = Math.max(1, Math.hypot(p.D - xi, p.miss)), ti = t0 + tr.T[tr.iBurn];
    if (o.g2 > 0) { buf = ignitionBuf(rk, rnd, 1); scale(buf, 1 / ri); postLayer(buf, ri, p.ground); layers.push({ m: buf, t: ti, pan: panAt(xi, ri), g: o.g2 }); }
    ev.push({ k: 'launch', t: ti, label: Lb('ignition') });
    if (rk.mode === 'launch' && tr.iCut >= 0 && tr.iCut < tr.n) {
      var xc = tr.x[tr.iCut], rc = Math.max(1, Math.hypot(p.D - xc, p.miss)), tc = t0 + tr.T[tr.iCut];
      if (o.g2 > 0) { buf = ignitionBuf(rk, rnd, -0.4); scale(buf, 1 / rc); airFilter(buf, rc); layers.push({ m: buf, t: tc, pan: panAt(xc, rc), g: o.g2 }); }
      ev.push({ k: 'pass', t: tc, label: Lb('cutoff') });
    }
  } else if (rk.passed) ev.push({ k: 'pass', t: t0 + rk.passT, label: Lb('pass') });
  if (rk.crack && o.g3 > 0) {
    var rb = Math.hypot(p.D - rk.crack.x, p.miss);
    buf = crackBuf(rk.crack); postLayer(buf, rb, p.ground);
    layers.push({ m: buf, t: t0 + rk.crack.t, pan: panAt(rk.crack.x, rb), g: o.g3 }); ev.push({ k: 'crack', t: t0 + rk.crack.t, label: Lb('boom') });
  }
  if (rk.hit && o.g4 > 0) {
    var h = rk.hit, hp = panAt(h.x, h.r), sc = clamp(Math.pow(0.2 / p.rkMass, 1 / 3), 0.25, 3), surf = p.target !== 'none' ? p.target : 'concrete';
    if (rk.mode === 'landing') {
      buf = modalHit('steel', h.E, sc, rnd); scale(buf, 1 / h.r); postLayer(buf, h.r, p.ground * 0.5); layers.push({ m: buf, t: t0 + h.t, pan: hp, g: o.g4 });
      buf = modalHit(surf, h.E, sc, rnd); scale(buf, 1 / h.r); airFilter(buf, h.r); layers.push({ m: buf, t: t0 + h.t, pan: hp, g: o.g4 });
      ev.push({ k: 'impact', t: t0 + h.t, label: Lb('touchdown') });
    } else {
      buf = modalHit(surf, h.E, sc, rnd); scale(buf, 1 / h.r); postLayer(buf, h.r, p.ground * 0.5); layers.push({ m: buf, t: t0 + h.t, pan: hp, g: o.g4 });
      ev.push({ k: 'impact', t: t0 + h.t, label: Lb('impact') });
      if (rk.pay) explosionLayers(rk.pay, { W: p.payload, r: h.r, surface: surf, t0: t0 + h.tau, pan: hp, ground: p.ground,
        gBlast: o.g4, gRumble: o.g4, gFrag: o.g4, gDebris: o.g4 }, rnd, layers, ev, lab);
    }
  }
}
/* Static burn, one seamless period: every modulation runs on a whole number of cycles per loop. */
function rocketStatic(rk, p, o, rnd, Np) {
  var a = jetNoise(Np, rk.fpk, rnd, true), b = jetNoise(Np, rk.fpk, rnd, true), ck = rk.crk > 0 ? crackleNoise(Np, rk.fpk, rnd, true) : null;
  var Lp = Np / FS, fch = Math.round(clamp(60 / Math.sqrt(rk.De), 25, 400) * Lp) / Lp, fw = Math.round(p.rkWhineHz * Lp) / Lp, fw2 = Math.round(1.37 * p.rkWhineHz * Lp) / Lp;
  var comps = [], k, i, mid = new Float32Array(Np), side = new Float32Array(Np), dir = dbToLin(6 * 0.717 - 3);
  for (k = 1; k <= 6; k++) comps.push([0.06 / Math.sqrt(k) * (0.5 + rnd()), rnd() * TAU, k]);
  for (i = 0; i < Np; i++) {
    var t = i / FS, rough = 0;
    for (k = 0; k < 6; k++) rough += comps[k][0] * Math.sin(TAU * comps[k][2] * t / Lp + comps[k][1]);
    var mod = (1 + rough) * (1 + 0.6 * p.rkChug * Math.sin(TAU * fch * t + 3 * rough));
    var s = a[i] * (1 - 0.5 * rk.crk) + (ck ? ck[i] * rk.crk : 0);
    var wh = p.rkWhine > 0 ? p.rkWhine * 0.35 * (Math.sin(TAU * fw * t) + 0.5 * Math.sin(TAU * 2 * fw * t + 1) + 0.4 * Math.sin(TAU * fw2 * t)) : 0;
    mid[i] = rk.p1 * dir * (o.g1 * s * mod + o.g3 * wh); side[i] = rk.p1 * dir * o.g1 * b[i] * mod * 0.35;
  }
  return { mid: mid, side: side };
}

/* ---------- rotors ---------- */
var SINT = new Float32Array(8192);
(function () { for (var i = 0; i < 8192; i++) SINT[i] = Math.sin(TAU * i / 8192); })();
function fsin(cyc) { return SINT[((cyc - Math.floor(cyc)) * 8192) | 0]; }
function trajKin(dur, D, miss, xfn) {
  var n = Math.round(dur * TRAJ_HZ) + 1, xs = new Float64Array(n), vs = new Float64Array(n), T = new Float64Array(n), i;
  for (i = 0; i < n; i++) { var t = i / TRAJ_HZ; xs[i] = xfn(t); T[i] = t + Math.hypot(D - xs[i], miss) / C; vs[i] = i ? (xs[i] - xs[i - 1]) * TRAJ_HZ : 0; }
  if (n > 1) vs[0] = vs[1];
  return { n: n, x: xs, v: vs, T: T };
}
/* Hover speed follows from weight: thrust per rotor = kT * rho * n^2 * D^4. Sound power is a small, tip-Mach-dependent share of shaft power. */
function planRotor(p, grnd) {
  var N = clamp(Math.round(p.rtCount), 1, 8), B = clamp(Math.round(p.rtBlades), 2, 7), Dm = p.rtDia, m = p.rtMass;
  var kT = clamp(0.11 * Math.pow(0.3 / Dm, 0.3), 0.04, 0.11), n0 = Math.sqrt(m * 9.81 / (N * kT * RHO * Math.pow(Dm, 4))), over = false;
  if (Math.PI * Dm * n0 > 0.92 * C) { n0 = 0.92 * C / (Math.PI * Dm); over = true; }
  var vtip = Math.PI * Dm * n0, Mt = vtip / C, A1 = Math.PI * Dm * Dm / 4, T1 = m * 9.81 / N;
  var Pm = N * Math.pow(T1, 1.5) / Math.sqrt(2 * RHO * A1), Wa = Pm * 1e-3 * Math.pow(Mt, 3), p1 = Math.sqrt(Wa * RHO * C / (4 * Math.PI));
  var mode = p.rtMode, v = p.rtSpeed, dur, tauF, xF, evs = [], D = p.D;
  if (mode === 'hover') { dur = LOOP_S; D = 0; tauF = function () { return 1; }; xF = function () { return 0; }; }
  else if (mode === 'flyby') {
    var xs = p.D + Math.min(clamp(15 * p.miss, 20, 300), v * 4.5), x0 = Math.max(0, p.D - v * 4.5); dur = Math.max(0.5, (xs - x0) / v);
    tauF = function () { return 1.08; }; xF = function (t) { return x0 + v * t; };
  } else if (mode === 'takeoff') {
    dur = 5.5;
    tauF = function (t) { return t < 0.5 ? 0.7 * t : t < 1 ? 0.35 : t < 1.6 ? 0.35 + 0.95 * (t - 1) / 0.6 : t < 3 ? 1.3 : 1.3 - 0.2 * Math.min(1, (t - 3) / 0.5); };
    xF = function (t) { var s = Math.max(0, t - 1.5), ta = v / 3; return s < ta ? 1.5 * s * s : 1.5 * ta * ta + v * (s - ta); };
    evs.push(['liftoff', 1.5]);
  } else {
    var dd = Math.max(p.D, 2), tl = Math.min(2 * dd / v, 8), v0 = 2 * dd / tl; D = dd; dur = tl + 1.6;
    tauF = function (t) { return t < tl - 0.6 ? 0.93 : t < tl ? 0.93 + 0.3 * (1 - (tl - t) / 0.6) : Math.max(0, 1.23 * (1 - (t - tl) / 1.2)); };
    xF = function (t) { return t < tl ? v0 * t - 0.5 * v0 / tl * t * t : dd; };
    evs.push(['touchdown', tl]);
  }
  var RS = 200, nr = Math.ceil(dur * RS) + 2, nj = [], j, k, i, hover = mode === 'hover';
  for (j = 0; j < N; j++) {
    var det = (grnd() * 2 - 1) * 0.012, comps = [], arr = new Float32Array(nr);
    for (k = 1; k <= 5; k++) comps.push([0.009 / k * (0.5 + grnd()), grnd() * TAU, k]);
    /* in a loop every rotor must complete a whole number of blade passes */
    var base = hover ? Math.round(n0 * (1 + p.rtWander * det) * B * dur) / (B * dur) : n0;
    for (i = 0; i < nr; i++) {
      var t = i / RS, w = hover ? 0 : det;
      for (k = 0; k < 5; k++) w += comps[k][0] * Math.sin(TAU * comps[k][2] * t / dur + comps[k][1]);
      arr[i] = base * (1 + p.rtWander * w) * Math.sqrt(tauF(Math.min(t, dur)));
    }
    nj.push(arr);
  }
  var out = { N: N, B: B, Dm: Dm, n0: n0, vtip: vtip, Mt: Mt, Pm: Pm, Wa: Wa, p1: p1, over: over, mode: mode, dur: dur, nj: nj, RS: RS, nr: nr,
    bpf: B * n0, load: m * 9.81 / (N * A1), D: D, r: Math.max(1, p.miss), evs: evs, tr: null, passed: false, passT: 0 };
  if (!hover) { out.tr = trajKin(dur, D, p.miss, xF); passInfo(out.tr, D, out); }
  return out;
}
/* Rotor source at 1 m: blade-pass tones from a wavetable, vortex noise modulated at blade rate, slap pulses, motor whine. */
function rotorSignal(rt, p, o, rnd, ns, periodic) {
  var N = rt.N, B = rt.B, size = 2048, M = clamp(Math.floor(15000 / (rt.bpf * 1.4)), 2, 40), tone = new Float32Array(size + 1), slapT = new Float32Array(size + 1);
  var kx = clamp(2.2 - 1.8 * rt.Mt, 0.5, 2.2), m, i, j, k, e = 0;
  for (m = 1; m <= M; m++) {
    var am = Math.pow(m, -kx), ph = rnd() * TAU;
    for (i = 0; i < size; i++) { var th = TAU * i / size; tone[i] += am * Math.sin(m * th + ph); slapT[i] += Math.cos(m * th); }
  }
  for (i = 0; i < size; i++) e += tone[i] * tone[i];
  e = Math.sqrt(e / size) || 1;
  for (i = 0; i < size; i++) { tone[i] /= e; slapT[i] *= 1.0 / Math.sqrt(M / 2); }
  tone[size] = tone[0]; slapT[size] = slapT[0];
  var fb0 = 0.25 * rt.vtip / (0.02 * rt.Dm + 0.004), bbShare = clamp(0.9 - 0.25 * Math.log10(rt.Dm / 0.1), 0.3, 0.9);
  var wn = new Float32Array(ns), bb = new Float32Array(ns), lp = 0, bp = 0, pass, eb = 0;
  for (i = 0; i < ns; i++) wn[i] = rnd() * 2 - 1;
  for (pass = periodic ? 0 : 1; pass < 2; pass++) for (i = 0; i < ns; i++) {
    var iu0 = Math.min(rt.nr - 1, Math.floor(i / FS * rt.RS)), fc = clamp(fb0 * rt.nj[0][iu0] / rt.n0, 80, 7500), fk = 2 * Math.sin(Math.PI * fc / FS);
    lp += fk * bp; var hp = wn[i] - lp - 1.4 * bp; bp += fk * hp; bb[i] = bp;
  }
  for (i = 0; i < ns; i++) eb += bb[i] * bb[i];
  scale(bb, 1 / (Math.sqrt(eb / ns) || 1));
  var c = new Float64Array(N), mB = Math.max(1, Math.round(clamp(1200 / rt.bpf, 3, 400))), mid = new Float32Array(ns), side = new Float32Array(ns), gN = 1 / Math.sqrt(N);
  var gS = o.g4 * p.rtSlap, gW = o.g3 * p.rtWhine * 0.5;
  for (k = 0; k < ns; k++) {
    var u = k / FS * rt.RS, iu = Math.min(rt.nr - 2, Math.floor(u)), fu = u - iu, sm = 0, ss = 0, amod = 0, fr = 0;
    for (j = 0; j < N; j++) {
      var nn = rt.nj[j][iu] + (rt.nj[j][iu + 1] - rt.nj[j][iu]) * fu;
      c[j] += B * nn / FS; if (c[j] >= 1) c[j] -= Math.floor(c[j]);
      var pos = c[j] * size, ip = Math.floor(pos), fp = pos - ip;
      var s = o.g1 * (tone[ip] + (tone[ip + 1] - tone[ip]) * fp) + gS * (slapT[ip] + (slapT[ip + 1] - slapT[ip]) * fp);
      if (gW > 0) s += gW * (fsin(mB * c[j]) + 0.4 * fsin(2 * mB * c[j] + 0.16));
      sm += s; ss += (j & 1) ? -s : s; amod += 1 + 0.7 * fsin(c[j] + 0.25 + j * 0.3); fr += nn;
    }
    fr /= N * rt.n0;
    var amp = rt.p1 * Math.pow(fr, 2.5);
    mid[k] = amp * (sm * gN + o.g2 * bbShare * bb[k] * amod / N); side[k] = amp * ss * gN * 0.45;
  }
  return { mid: mid, side: side };
}
function rotorLayers(rt, p, o, rnd, layers, ev, lab) {
  var tr = rt.tr, ns = Math.floor((tr.n - 1) / TRAJ_HZ * FS);
  if (ns < 64) return;
  var sig = rotorSignal(rt, p, o, rnd, ns, false);
  var wk = movingSource(tr, rt.D, p.miss, function (k) { return sig.mid[k]; }, null);
  if (wk) layers.push({ L: wk.L, R: wk.R, t: o.t0 + wk.t, g: 1 });
  if (rt.mode === 'flyby' && rt.passed) ev.push({ k: 'pass', t: o.t0 + rt.passT, label: lab ? 'pass' : '' });
  rt.evs.forEach(function (e) { var i = Math.min(tr.n - 1, Math.round(e[1] * TRAJ_HZ)); ev.push({ k: 'launch', t: o.t0 + tr.T[i], label: lab ? e[0] : '' }); });
}

/* ---------- electric discharge ---------- */
function addN(buf, t0, dur, peak) {
  var n0 = Math.max(0, Math.floor(t0 * FS)), n1 = Math.min(buf.length - 1, Math.ceil((t0 + dur) * FS)), n, k, acc, t;
  for (n = n0; n <= n1; n++) {
    acc = 0;
    for (k = 0; k < 4; k++) { t = (n + (k + 0.5) / 4) / FS - t0; if (t >= 0 && t <= dur) acc += 1 - 2 * t / dur; }
    buf[n] += peak * acc / 4;
  }
}
function walkChannel(start, main, len, ds, tort, rnd) {
  var n = Math.max(2, Math.round(len / ds)), pts = [start.slice()], u = main.slice(), q = start.slice(), i, k;
  for (i = 0; i < n; i++) {
    for (k = 0; k < 3; k++) u[k] = u[k] * 0.8 + main[k] * 0.2 + tort * 0.9 * (rnd() - 0.5);
    var m = Math.hypot(u[0], u[1], u[2]) || 1;
    q = [q[0] + u[0] / m * ds, q[1] + u[1] / m * ds, Math.max(0, q[2] + u[2] / m * ds)]; pts.push(q);
  }
  return pts;
}
/* Thunder after Few: the channel heats a cylinder of relaxation radius Rc = sqrt(E per metre / (pi P0));
   every stretch of it sends an N-wave about 2.6 Rc / c long, and the ear hears them spread out by distance. */
function planDischarge(p, grnd) {
  var E = p.dcEnergy, Lc = p.dcLength, El = E / Lc, Rc = Math.sqrt(El / (Math.PI * P0)), d = p.dcDist;
  /* a channel shorter than its own shock radius acts as a point source */
  if (Rc > Lc / 2) Rc = Math.cbrt(3 * E / (4 * Math.PI * P0));
  var Tn = 2.6 * Rc / C;
  var nSeg = clamp(Math.round(Lc / Math.max(4 * Rc, Lc / 300)), 3, 300), ds = Lc / nSeg, vert = p.dcOrient === 'vertical', ear = [0, 0, 1.7];
  var start = vert ? [d, 0, Lc * 0.85] : [d, -Lc * 0.42, 1.5], main = vert ? [0, 0, -1] : [0, 1, 0];
  var pts = walkChannel(start, main, Lc, ds, p.dcTort, grnd), segs = [], bsegs = [], bpts = [], r0 = Math.max(ds / 2, Rc), i, b;
  function add(list, a, c, gain) {
    var mid = [(a[0] + c[0]) / 2, (a[1] + c[1]) / 2, (a[2] + c[2]) / 2], r = Math.max(Math.hypot(mid[0] - ear[0], mid[1] - ear[1], mid[2] - ear[2]), Rc, 0.05);
    list.push({ r: r, t: r / C, pan: clamp(mid[1] / r, -1, 1) * 0.9, pk: gain * 0.2 * P0 * Math.pow(Rc / r0, 0.75) * r0 / Math.max(r, r0) * Math.min(1, ds / (2 * r0)) });
  }
  for (i = 0; i < pts.length - 1; i++) add(segs, pts[i], pts[i + 1], 1);
  for (b = 0; b < Math.round(p.dcBranches); b++) {
    var from = pts[1 + Math.floor(grnd() * (pts.length - 2))], dir = [main[0] + (grnd() - 0.5) * 1.6, main[1] + (grnd() - 0.5) * 1.6, main[2] + (grnd() - 0.5) * 1.6];
    var bp = walkChannel(from, dir, Lc * (0.1 + 0.25 * grnd()), ds, p.dcTort, grnd);
    for (i = 0; i < bp.length - 1; i++) add(bsegs, bp[i], bp[i + 1], 0.35);
    bpts.push(bp);
  }
  var rMin = Infinity, rMax = 0, rSum = 0;
  segs.concat(bsegs).forEach(function (s) { if (s.r < rMin) rMin = s.r; if (s.r > rMax) rMax = s.r; });
  segs.forEach(function (s) { rSum += s.r; });
  function flat(a) { return a.map(function (q) { return [q[0], vert ? q[2] : q[1]]; }); }
  return { El: El, Rc: Rc, Tn: Tn, segs: segs, bsegs: bsegs, rMin: rMin, rMax: rMax, rMean: rSum / segs.length, tFirst: rMin / C, tLast: rMax / C,
    pts2: flat(pts), bpts2: bpts.map(flat), ear2: [0, vert ? 1.7 : 0], vert: vert, dev: Math.max(d, 0.3), tC: p.dcCharge > 0.05 ? p.dcCharge : 0 };
}
function dischargeLayers(pl, p, o, rnd, layers, ev, lab) {
  var tC = pl.tC, t0 = o.t0, span = pl.tLast - pl.tFirst, NB = 6, i, lr = Math.log(pl.rMax / pl.rMin) || 1;
  var len = Math.ceil((span + pl.Tn * 4 + 0.4) * FS), bins = [], pkMain = 0;
  function strike(segs, tS, gain, tnS, bl, br) {
    segs.forEach(function (s) {
      var L = bl, R = br;
      if (!L) { var bi = Math.min(NB - 1, Math.floor(Math.log(s.r / pl.rMin) / lr * NB)); if (!bins[bi]) bins[bi] = { L: new Float32Array(len), R: new Float32Array(len), r: 0, n: 0 }; L = bins[bi].L; R = bins[bi].R; bins[bi].r += s.r; bins[bi].n++; }
      var pk = s.pk * gain * (0.6 + 0.8 * rnd()), T = pl.Tn * tnS * (0.8 + 0.45 * rnd()), ts = s.t - pl.tFirst + tS + 0.001;
      addN(L, ts, T, pk * Math.cos((s.pan + 1) * Math.PI / 4)); addN(R, ts, T, pk * Math.sin((s.pan + 1) * Math.PI / 4));
    });
  }
  var tS = 0, sg = [1, 0.7, 0.55, 0.45, 0.4];
  for (i = 0; i < clamp(Math.round(p.dcStrokes), 1, 5); i++) { strike(pl.segs, tS, sg[i], 1); if (!i) strike(pl.bsegs, 0, 1, 0.7); tS += 0.03 + 0.05 * rnd(); }
  bins.forEach(function (b) {
    if (!b) return;
    var pk = peakOf(b.L, b.R); if (pk > pkMain) pkMain = pk;
    airFilter(b.L, b.r / b.n); airFilter(b.R, b.r / b.n);
    if (o.g1 > 0) layers.push({ L: b.L, R: b.R, t: t0 + tC + pl.tFirst - 0.001, g: o.g1 });
  });
  ev.push({ k: 'crack', t: t0 + tC + pl.tFirst, label: lab ? 'strike' : '' });
  if (p.dcSustain > 0.05 && o.g2 > 0) {
    /* a sustained arc re-strikes along the same channel; plasma hiss follows the re-strike rate */
    var bn = Math.ceil((p.dcSustain + span + 0.15) * FS), bl = new Float32Array(bn), br = new Float32Array(bn), step = Math.ceil(pl.segs.length / 40);
    var sub = pl.segs.filter(function (s, k) { return k % step === 0; }), t = 0.02 + tS;
    while (t < p.dcSustain) { strike(sub, t, 0.5 * (1 - 0.5 * t / p.dcSustain) * (0.4 + rnd()), 0.6, bl, br); t += (1 + 0.3 * (rnd() - 0.5)) / p.dcRate; }
    var hn = Math.ceil(p.dcSustain * FS), hs = new Float32Array(hn);
    for (i = 0; i < hn; i++) hs[i] = (rnd() * 2 - 1) * (0.5 + 0.5 * Math.abs(fsin(0.5 * p.dcRate * i / FS))) * (1 - 0.6 * i / hn);
    onePoleHP(hs, 2500); onePoleLP(hs, 9000); toPeak(hs, 0.2 * (peakOf(bl, br) || pkMain));
    for (i = 0; i < hn; i++) { bl[i] += hs[i]; br[i] += hs[i]; }
    airFilter(bl, pl.rMean); airFilter(br, pl.rMean);
    layers.push({ L: bl, R: br, t: t0 + tC + pl.tFirst, g: o.g2 });
  }
  if (tC > 0 && o.g3 > 0) {
    /* charger whine: converter pitch climbs along the capacitor charge curve, then stops dead at the discharge */
    var cn = Math.ceil(tC * FS), cb = new Float32Array(cn + 2400), ph = 0, k1 = 1 - Math.exp(-3);
    for (i = 0; i < cn; i++) {
      var u = i / cn, f = 1500 + (p.dcChargeHz - 1500) * (1 - Math.exp(-3 * u)) / k1; ph += f / FS;
      cb[i] = (fsin(ph) + 0.3 * fsin(2 * ph) + 0.15 * fsin(0.5 * ph)) * (0.15 + 0.85 * u) * Math.min(1, i / 480) * Math.min(1, (cn - i) / 96);
    }
    toPeak(cb, 0.12 * pkMain); airFilter(cb, pl.dev);
    layers.push({ m: cb, t: t0 + pl.dev / C, pan: 0, g: o.g3 }); ev.push({ k: 'pass', t: t0 + pl.dev / C, label: lab ? 'charge' : '' });
  }
  if (p.dcKick > 0.01 && o.g4 > 0) {
    /* magnetic forces jolt the conductors, and the circuit rings down at its LC frequency */
    var kb = modalHit('steel', 1, 0.6, rnd); toPeak(kb, 0.3 * pkMain * p.dcKick);
    var rn = Math.ceil(0.7 * FS), rb = new Float32Array(rn + 2400), tau = 14 / (Math.PI * p.dcRingHz);
    for (i = 0; i < rn; i++) { var tt = i / FS; rb[i] = Math.exp(-tt / tau) * (fsin(p.dcRingHz * tt) + 0.3 * fsin(2 * p.dcRingHz * tt)); }
    toPeak(rb, 0.2 * pkMain * p.dcKick);
    for (i = 0; i < kb.length && i < rb.length; i++) rb[i] += kb[i];
    airFilter(rb, pl.dev);
    layers.push({ m: rb, t: t0 + tC + pl.dev / C, pan: 0, g: o.g4 });
  }
}

/* ---------- dispersive line: the struck slinky or guy-wire behind the classic blaster ---------- */
/* Waves on a stiff line obey w^2 = cT^2 k^2 + kappa^2 k^4: bending makes high frequencies travel faster,
   so a strike arrives as a falling sweep. Each end reflection adds a longer, darker repeat. */
var BODIES = { can: { f: [420, 1130, 1870, 2960, 4100], q: 30 }, tube: { f: [180, 360, 545, 730, 920, 1105], q: 25 }, plate: { f: [260, 411, 582, 759, 936, 1225, 1404, 1768], q: 60 } };
function planBlaster(p) {
  var Lw = p.bpLength, kap = p.bpStiff, cT = p.bpTension < 2 ? 0 : p.bpTension, f = [], tau = [], i, j;
  for (i = 0; i <= 320; i++) {
    var k = 1e-3 * Math.pow(1e7, i / 320), w = k * Math.sqrt(cT * cT + kap * kap * k * k), fq = w / TAU;
    if (fq < 40 || fq > 18000) continue;
    f.push(fq); tau.push(Lw * w / (cT * cT * k + 2 * kap * kap * k * k * k));
  }
  var K = f.length, echoes = [{ m: 1, g: 1 }];
  for (j = 1; j <= Math.round(p.bpEchoes); j++) { if ((2 * j + 1) * tau[0] > 6) break; echoes.push({ m: 2 * j + 1, g: Math.pow(p.bpRefl, j) }); }
  return { Lw: Lw, f: f, tau: tau, K: K, echoes: echoes, tFirst: tau[K - 1], tSweep: tau[0] - tau[K - 1], tEnd: echoes[echoes.length - 1].m * tau[0],
    tThump: cT ? Lw / cT : 0, fTrans: cT ? Math.SQRT2 * cT * cT / (TAU * kap) : 0, fLo: f[0] };
}
function chirpInto(buf, pl, p, m, gain) {
  var f = pl.f, tau = pl.tau, j = pl.K - 1, n0 = Math.ceil(m * tau[j] * FS), n1 = Math.min(buf.length - 1, Math.floor(m * tau[0] * FS)), ph = 0, n;
  var fh = p.bpHard, dk = p.bpDamp * 0.02 * m * pl.Lw;
  for (n = n0; n <= n1; n++) {
    var tm = n / FS / m;
    while (j > 0 && tau[j - 1] < tm) j--;
    if (j === 0) break;
    var w = (tm - tau[j]) / (tau[j - 1] - tau[j]), fq = f[j] * Math.pow(f[j - 1] / f[j], w);
    /* stationary phase: amplitude follows the square root of the sweep rate */
    var dfdt = Math.min(3e6, (f[j] - f[j - 1]) / (m * (tau[j - 1] - tau[j])));
    ph += fq / FS;
    buf[n] += gain * Math.sqrt(dfdt) / (1 + (fq / fh) * (fq / fh)) * Math.exp(-dk * fq / 1000) * Math.min(1, (n - n0) / 32) * fsin(ph);
  }
}
/* ---------- weapon chain: launcher, bolt in flight, target response ----------
   The dispersive line above is one launcher. Rail, coil and gas launchers ring as bars, coils, chambers and pipes.
   The bolt heats a channel of air, or flies as a slug. The target flash-boils at the hit and rings with bending waves. */
function addAt(dst, src, t, g) {
  var n0 = Math.round(t * FS), i, n = Math.min(src.length, dst.length - n0);
  if (g == null) g = 1;
  for (i = Math.max(0, -n0); i < n; i++) dst[n0 + i] += src[i] * g;
}
function dampedSine(buf, t0, f, q, amp) {
  var n0 = Math.round(t0 * FS), tau = q / (Math.PI * f), n = Math.min(buf.length - n0, Math.ceil(tau * 7 * FS)), i;
  for (i = 0; i < n; i++) { var t = i / FS; buf[n0 + i] += amp * Math.exp(-t / tau) * fsin(f * t) * Math.min(1, i / 24); }
}
function noiseBurst(buf, t0, dur, hp, lp, amp, rnd, attack) {
  var n0 = Math.round(t0 * FS), n = Math.min(buf.length - n0, Math.ceil(dur * 5 * FS)), b, i, pk;
  if (n < 8) return;
  b = new Float32Array(n);
  for (i = 0; i < n; i++) b[i] = rnd() * 2 - 1;
  if (lp) { onePoleLP(b, lp); onePoleLP(b, lp); }
  if (hp) onePoleHP(b, hp);
  pk = peakOf(b) || 1;
  for (i = 0; i < n; i++) { var t = i / FS; buf[n0 + i] += amp * b[i] / pk * Math.exp(-t / dur) * Math.min(1, t / (attack || 0.0005)); }
}
/* charger whine: converter pitch climbs along the capacitor charge curve, then stops dead at the discharge */
function chargeWhine(dur, fEnd) {
  var cn = Math.ceil(dur * FS), cb = new Float32Array(cn + 2400), ph = 0, k1 = 1 - Math.exp(-3), i;
  for (i = 0; i < cn; i++) {
    var u = i / cn, f = 1500 + (fEnd - 1500) * (1 - Math.exp(-3 * u)) / k1; ph += f / FS;
    cb[i] = (fsin(ph) + 0.3 * fsin(2 * ph) + 0.15 * fsin(0.5 * ph)) * (0.15 + 0.85 * u) * Math.min(1, i / 480) * Math.min(1, (cn - i) / 96);
  }
  return cb;
}

/* Bending waves in a plate (kappa = sqrt(D / rho h)) or a bar (kappa = sqrt(EI / rho A)) have group speed
   2 sqrt(kappa w): after a distance d, frequency f arrives at t = d / (2 sqrt(2 pi kappa f)), so every path from
   the hit is a falling sweep. Amplitude follows the sweep rate (stationary phase); loss eta damps highs first. */
function bendChirp(buf, t0, d, kap, gain, fHi, fLo, eta, hard, ph0) {
  var K = d * d / (8 * Math.PI * kap), ta = Math.sqrt(K / fHi), tb = Math.sqrt(K / Math.max(fLo, 1));
  var n0 = Math.ceil((t0 + ta) * FS), n1 = Math.min(buf.length - 1, Math.floor((t0 + tb) * FS)), fade = Math.max(8, Math.min(512, (n1 - n0) >> 2)), n, q = 0;
  for (n = n0; n <= n1; n++) {
    var t = n / FS - t0, f = K / (t * t), sw = 2 * K / (t * t * t);
    var a = gain * Math.sqrt(sw) / (1 + (f / hard) * (f / hard)) * Math.exp(-Math.PI * eta * f * t);
    if (q < 24) a *= ++q / 24;
    if (n1 - n < fade) a *= (n1 - n) / fade;
    buf[n] += a * fsin(ph0 + K * (1 / ta - 1 / t));
  }
}
/* The struck body as an impulse response: dispersive sweeps along the strongest paths, then its modes ring on. Peak 1. */
function bendIR(s, hard, rnd) {
  var tEnd = 0, tTail = 0, i, n;
  s.paths.forEach(function (q) { var tb = q.d / (2 * Math.sqrt(TAU * s.kap * s.fLo)); if (tb > tEnd) tEnd = tb; });
  s.modes.forEach(function (md) { md.t60 = Math.min(s.tailMax, 2.2 / (s.eta * md.f)); if (md.t60 > tTail) tTail = md.t60; });
  n = Math.ceil((Math.min(Math.max(tEnd, tTail), 6) + 0.05) * FS);
  var ir = new Float32Array(n), tl = new Float32Array(n);
  s.paths.forEach(function (q) { bendChirp(ir, 0, q.d, s.kap, q.g, Math.min(16000, hard * 2.5), s.fLo, s.eta, hard, rnd()); });
  s.modes.forEach(function (md) {
    var R = Math.pow(10, -3 / (md.t60 * FS)), w = TAU * md.f / FS, c1 = 2 * R * Math.cos(w), c2 = R * R, y1 = R * Math.sin(w), y2 = 0, y;
    var A = md.a / (1 + (md.f / hard) * (md.f / hard)), nn = Math.min(n, Math.ceil(md.t60 * FS));
    tl[1] += A * y1;
    for (i = 2; i < nn; i++) { y = c1 * y1 - c2 * y2; y2 = y1; y1 = y; tl[i] += A * y; }
  });
  var pc = peakOf(ir) || 1, pt = peakOf(tl) || 1;
  for (i = 0; i < n; i++) ir[i] = ir[i] / pc + s.tail * tl[i] / pt;
  toPeak(ir, 1);
  return ir;
}
var PLATES = {
  steel:     { E: 200e9, rho: 7850, nu: 0.3,  eta: 0.0012, tick: 'steel' },
  aluminium: { E: 70e9,  rho: 2700, nu: 0.33, eta: 0.002,  tick: 'steel' },
  glass:     { E: 70e9,  rho: 2500, nu: 0.22, eta: 0.003,  tick: 'glass' },
  ice:       { E: 9e9,   rho: 917,  nu: 0.33, eta: 0.005,  tick: 'glass' },
  wood:      { E: 11e9,  rho: 600,  nu: 0.3,  eta: 0.025,  tick: 'wood' }
};
function plateKappa(m, h) { return h * Math.sqrt(m.E / (12 * m.rho * (1 - m.nu * m.nu))); }
/* A rectangular plate: edge reflections as image sources (2D spreading, 10 percent lost per reflection),
   simply supported modes f = (pi / 2) kappa ((i / a)^2 + (j / b)^2) for the long ring. */
function planPlate(mat, h, size) {
  var m = PLATES[mat], kap = plateKappa(m, h), a = size, b = size * 0.72, x0 = 0.37 * a, y0 = 0.41 * b, xo = 0.63 * a, yo = 0.57 * b;
  var paths = [], modes = [], i, j, sx, sy;
  for (i = -5; i <= 5; i++) for (j = -5; j <= 5; j++) for (sx = 0; sx < 2; sx++) for (sy = 0; sy < 2; sy++) {
    var X = 2 * i * a + (sx ? -x0 : x0), Y = 2 * j * b + (sy ? -y0 : y0), d = Math.max(0.02, Math.hypot(X - xo, Y - yo));
    paths.push({ d: d, g: Math.pow(0.9, Math.abs(2 * i - sx) + Math.abs(2 * j - sy)) / Math.sqrt(d) });
  }
  paths.sort(function (u, v) { return v.g - u.g; });
  paths = paths.slice(0, 40);
  var f11 = Math.PI / 2 * kap * (1 / (a * a) + 1 / (b * b));
  for (i = 1; i <= 30; i++) for (j = 1; j <= 30; j++) {
    var f = Math.PI / 2 * kap * (i * i / (a * a) + j * j / (b * b));
    if (f < 20 || f > 10000) continue;
    var w = Math.sin(i * Math.PI * x0 / a) * Math.sin(j * Math.PI * y0 / b) * Math.sin(i * Math.PI * xo / a) * Math.sin(j * Math.PI * yo / b);
    if (Math.abs(w) > 0.05) modes.push({ f: f, a: w });
  }
  modes.sort(function (u, v) { return u.f - v.f; });
  if (modes.length > 64) {
    /* keep 64 spread over the band; each stands for the ones skipped around it */
    var st = modes.length / 64, kept = [];
    for (i = 0; i < 64; i++) { var md = modes[Math.floor(i * st)]; kept.push({ f: md.f, a: md.a * Math.sqrt(st) }); }
    modes = kept;
  }
  return { kap: kap, paths: paths, modes: modes, fLo: Math.max(f11, 25), eta: m.eta, tailMax: 3, tail: 0.4, f11: f11, a: a, b: b, cb1k: Math.sqrt(kap * TAU * 1000), mat: mat };
}
/* A rail: a free-free steel bar 4 cm deep, struck near the breech and heard from its middle. */
function planRail(L) {
  var kap = 0.04 / Math.sqrt(12) * Math.sqrt(200e9 / 7850), xs = 0.05 * L, xo = 0.5 * L, paths = [], modes = [], k, beta = [4.730, 7.853, 10.996, 14.137, 17.279];
  for (k = -6; k <= 6; k++) {
    paths.push({ d: Math.max(0.05, Math.abs(2 * k * L + xs - xo)), g: Math.pow(0.85, Math.abs(2 * k)) });
    paths.push({ d: Math.max(0.05, Math.abs(2 * k * L - xs - xo)), g: Math.pow(0.85, Math.abs(2 * k - 1)) });
  }
  paths.sort(function (u, v) { return v.g - u.g; });
  paths = paths.slice(0, 16);
  for (k = 0; k < 60; k++) {
    var bl = k < 5 ? beta[k] : (k + 1.5) * Math.PI, f = bl * bl * kap / (TAU * L * L);
    if (f > 9000) break;
    if (f > 20) modes.push({ f: f, a: (k & 1 ? -1 : 1) / Math.sqrt(1 + k) });
  }
  return { kap: kap, paths: paths, modes: modes, fLo: 30, eta: 0.008, tailMax: 2.5, tail: 0.5, f1: modes.length ? modes[0].f : 0, L: L };
}

/* Line launcher: the struck dispersive line with its echoes, thump and body, all on the launcher level. */
function lineLauncher(pl, p, gL, tA, pan, r, layers, ev, lab) {
  ev.push({ k: 'crack', t: tA + pl.tFirst, label: lab ? 'shot' : '' });
  if (gL <= 0) return;
  var nD = Math.ceil((pl.tau[0] + 0.06) * FS), nE = Math.ceil((pl.tEnd + 0.06) * FS), i, j;
  var dir = new Float32Array(nD + 64), ech = new Float32Array(nE + 64), amp1 = 3 * Math.sqrt(p.bpEnergy);
  chirpInto(dir, pl, p, 1, 1);
  for (j = 1; j < pl.echoes.length; j++) chirpInto(ech, pl, p, pl.echoes[j].m, pl.echoes[j].g);
  var sc = amp1 / (peakOf(dir) || 1);
  scale(dir, sc); scale(ech, sc);
  function put(b) { scale(b, 1 / r); airFilter(b, r); layers.push({ m: b, t: tA, pan: pan, g: gL }); }
  if (p.bpBody !== 'none') {
    var bd = BODIES[p.bpBody], body = new Float32Array(nE + Math.ceil(0.5 * FS));
    bd.f.forEach(function (bf, bi) {
      var R = Math.exp(-Math.PI * bf / (bd.q * FS)), c1 = 2 * R * Math.cos(TAU * bf / FS), c2 = R * R, y1 = 0, y2 = 0, y, g = 1 / (1 + bi * 0.5);
      for (i = 0; i < body.length; i++) { y = c1 * y1 - c2 * y2 + (i < nD ? dir[i] : 0) + (i < nE ? ech[i] : 0); y2 = y1; y1 = y; body[i] += g * y; }
    });
    toPeak(body, 0.8 * amp1); put(body);
  }
  if (pl.tThump > 0) {
    var fL = clamp(pl.fTrans * 0.5, 40, 400), th = new Float32Array(nE + Math.ceil(0.2 * FS));
    pl.echoes.forEach(function (e) { addShape(th, e.m * pl.tThump, 3 / fL, function (t) { var u = t * fL * 4; return 0.8 * amp1 * e.g * (1 - u) * Math.exp(-u); }); });
    put(th); ev.push({ k: 'impact', t: tA + pl.tThump, label: lab ? 'thump' : '' });
  }
  put(dir);
  if (pl.echoes.length > 1) put(ech);
}

function planLauncher(q, vExit) {
  var t = q.lnType, out = { type: t, tC: 0, transit: 0, marks: [] }, i;
  if ((t === 'rail' || t === 'coil') && q.lnCharge > 0.05) out.tC = q.lnCharge;
  if (t === 'line') out.line = planBlaster(q);
  else if (t === 'rail') {
    out.rail = planRail(q.lnLength); out.rail2 = planRail(q.lnLength * 1.013);
    out.transit = q.lnLength / Math.max(vExit / 2, 50);
  } else if (t === 'coil') {
    /* each stage adds the same energy, so speed grows as the square root of the stage count:
       the stages fire closer and closer together and each pull is shorter, so higher */
    var N = clamp(Math.round(q.lnStages), 2, 24), s = q.lnLength / N, st = [], tt = 0, vPrev = 0;
    for (i = 1; i <= N; i++) {
      var vi = Math.max(vExit, 5) * Math.sqrt(i / N), dt = s / Math.max((vPrev + vi) / 2, 2.5);
      st.push({ t: tt, v: vi, d: clamp(dt / 2, 0.0001, 0.08) }); tt += dt; vPrev = vi;
    }
    out.stages = st; out.transit = tt;
  } else if (t === 'gas') {
    var Lb = clamp(q.lnLength, 0.05, 2);
    out.Lb = Lb;
    out.pipe = C / (4 * (Lb + 0.006));                                    // barrel: closed at the breech, open at the muzzle
    out.helm = C / TAU * Math.sqrt(2.83e-5 / (q.lnChamber * 1e-6 * 0.012)); // chamber behind a 6 mm port, 12 mm long
    out.transit = 0.007;
  }
  return out;
}
function launcherLayers(ln, p, gL, t0, r0, pan0, rnd, layers, ev, lab) {
  if (ln.type === 'none') return;
  var tA = t0 + r0 / C, tF = tA + ln.tC, buf, i, k, E = p.lnEnergy;
  var lvl = 3 * Math.sqrt(Math.max(E, 1));   // Pa at 1 m for the launcher's loudest part: set against the bolt, not measured
  function put(b, t, pn, g) { scale(b, 1 / r0); airFilter(b, r0); layers.push({ m: b, t: t, pan: pn == null ? pan0 : pn, g: gL * (g == null ? 1 : g) }); }
  if (ln.tC > 0) {
    ev.push({ k: 'pass', t: tA, label: lab ? 'charge' : '' });
    if (gL > 0) { buf = chargeWhine(ln.tC, p.lnChargeHz); toPeak(buf, 0.05 * lvl); put(buf, tA); }
  }
  if (ln.type === 'line') { lineLauncher(ln.line, p, gL, tF, pan0, r0, layers, ev, lab); return; }
  ev.push({ k: 'launch', t: tF, label: lab ? 'fire' : '' });
  if (gL <= 0) return;
  if (ln.type === 'rail') {
    /* capacitor dump: switch crack and LC ring, then the armature arc along the rails and a plasma flash at the muzzle */
    buf = new Float32Array(Math.ceil(1.2 * FS));
    addN(buf, 0.0005, 0.00012, 0.5 * lvl);
    dampedSine(buf, 0.0005, p.lnRingHz, 9, 0.35 * lvl);
    noiseBurst(buf, 0.0005, Math.max(ln.transit, 0.004) * 0.6, 900, 9000, 0.45 * lvl, rnd, 0.0003);
    put(buf, tF);
    var b = blastParams(clamp(E * 0.02 / 4.184e6, 1e-7, 50), Math.max(r0, 0.5)), fb = new Float32Array(Math.ceil((b.td * 14 + 0.02) * FS) + 2400);
    addShape(fb, 0.0005, b.td * 9, function (t) { var u = t / b.td; return b.peak * (1 - u) * Math.exp(-1.2 * u); });
    airFilter(fb, r0); layers.push({ m: fb, t: tF + ln.transit, pan: pan0, g: gL });
    /* the rails ring: bending waves run from the breech and reflect at the free ends, then the bar modes ring on */
    var ir1 = bendIR(ln.rail, 8000, rnd), ir2 = bendIR(ln.rail2, 8000, rnd);
    toPeak(ir1, 0.5 * lvl); toPeak(ir2, 0.4 * lvl);
    put(ir1, tF, clamp(pan0 - 0.25, -1, 1)); put(ir2, tF + 0.0003, clamp(pan0 + 0.25, -1, 1));
    buf = modalHit('steel', E * 0.001, clamp(2 / p.lnLength, 0.2, 2), rnd); toPeak(buf, 0.4 * lvl); put(buf, tF + ln.transit);
  } else if (ln.type === 'coil') {
    buf = new Float32Array(Math.ceil((ln.transit + 0.8) * FS));
    ln.stages.forEach(function (s, k2) {
      addN(buf, s.t + 0.0003, 0.00008, 0.25 * lvl);   // thyristor switch click
      /* the coil pulls while the slug crosses it: one cycle of force, shorter at every stage */
      var n0 = Math.round((s.t + 0.0003) * FS), nn = Math.round(2 * s.d * FS), a = 0.6 * lvl * Math.sqrt((k2 + 1) / ln.stages.length);
      for (i = 0; i < nn && n0 + i < buf.length; i++) { var u = i / nn; buf[n0 + i] += a * Math.sin(Math.PI * u) * Math.sin(TAU * u); }
      dampedSine(buf, s.t + 0.0003, clamp(1 / s.d, 200, 6000), 6, 0.12 * lvl);
      if (k2) ev.push({ k: 'pass', t: tF + s.t, label: '' });
    });
    dampedSine(buf, ln.transit, p.lnRingHz, 9, 0.25 * lvl);
    put(buf, tF);
  } else if (ln.type === 'gas') {
    buf = new Float32Array(Math.ceil(1.0 * FS));
    noiseBurst(buf, 0, 0.02, 1500, 9000, 0.5 * lvl, rnd, 0.0004);                 // valve opens
    dampedSine(buf, 0.002, ln.helm, 8, 0.35 * lvl);                                // chamber pops (Helmholtz)
    var ph = modalHit('steel', 2, 1.6, rnd, { maxModes: 6, t60Scale: 0.5, noGrains: true });
    toPeak(ph, 0.45 * lvl); addAt(buf, ph, 0.004);                                // driver blade strikes
    for (k = 1; k <= 7; k += 2) dampedSine(buf, ln.transit, ln.pipe * k, 30, 0.3 * lvl / k);   // barrel rings as a quarter-wave pipe
    if (p.lnSpring > 0.01) {
      /* the return spring twangs: waves on a helix are dispersive too, so each pass along it falls in pitch */
      var sp = new Float32Array(Math.ceil(0.6 * FS));
      for (k = 0; k < 6; k++) bendChirp(sp, 0, 0.6 * (2 * k + 1), 0.15, Math.pow(0.8, k), 9000, 60, 0.01, 5000, rnd());
      toPeak(sp, 0.3 * lvl * p.lnSpring); addAt(buf, sp, 0.022);
    }
    var ck = modalHit('steel', 0.6, 2.2, rnd, { maxModes: 4, t60Scale: 0.3, noGrains: true });
    toPeak(ck, 0.3 * lvl); addAt(buf, ck, 0.045);                                 // driver returns
    noiseBurst(buf, 0.06, 0.12, 400, 6000, 0.18 * lvl, rnd, 0.004);              // exhaust
    put(buf, tF);
  }
}

/* A straight heated channel. Each stretch is heated as the bolt passes (at once for a beam) and sends an N-wave
   about 2.6 Rc / c long, Rc = sqrt(energy per metre / (pi P0)), as in the thunder model above. */
function planChannel(L, El, D, miss, v, rnd) {
  var Rc = Math.sqrt(El / (Math.PI * P0)), n = Math.max(2, Math.ceil(L / Math.max(4 * Rc, L / 240))), ds = L / n, r0 = Math.max(ds / 2, Rc), segs = [], i;
  for (i = 0; i < n; i++) {
    var x = (i + 0.5) * ds, y = (rnd() - 0.5) * 0.15 * ds, z = (rnd() - 0.5) * 0.15 * ds, r = Math.max(Math.hypot(D - x, miss - y, z), Rc, 0.05);
    segs.push({ x: x, r: r, ta: x / v + r / C, pan: clamp((x - D) / r, -1, 1) * 0.9,
      pk: 0.2 * P0 * Math.pow(Rc / r0, 0.75) * r0 / Math.max(r, r0) * Math.min(1, ds / (2 * r0)) });
  }
  return { Rc: Rc, Tn: 2.6 * Rc / C, segs: segs, ds: ds };
}
function planBolt(q, rnd) {
  var t = q.bvType, xEnd = q.tgMat !== 'none' ? q.targetDist : q.D + clamp(20 * q.miss, 20, 400), out = { type: t, xEnd: Math.max(0.1, xEnd), flight: 0, pulses: 1, period: 0 };
  if (t === 'bolt' || t === 'beam') {
    var v = t === 'beam' ? 3e8 : Math.max(q.bvSpeed, 5);
    out.v = v; out.ch = planChannel(out.xEnd, q.bvChannel, q.D, q.miss, v, rnd); out.flight = out.xEnd / v;
    if (t === 'beam') { out.pulses = clamp(Math.round(q.bvPulses), 1, 60); out.period = 1 / Math.max(q.bvRate, 1); }
    else out.tr = trajKin(out.flight, q.D, q.miss, function (s) { return v * s; });
  } else if (t === 'slug') {
    var d = q.bvCal / 1000, lr = q.lnType === 'gas' ? 20 : 3;
    var fp = { v0: q.bvSpeed, cal: q.bvCal, mass: 7800 * Math.PI / 4 * d * d * lr * d, lenRatio: lr, cdScale: 1, tumble: 0, tumbleHz: 200, swing: false,
      pathLen: q.tgMat !== 'none' ? Math.max(0.05, q.targetDist) : 0, D: q.D, miss: q.miss, launch: 'none', target: 'none', targetDist: 0, maxT: 6 };
    var a = analyzeProj(fp);
    out.fp = fp; out.an = a; out.v = q.bvSpeed; out.mass = fp.mass; out.tr = a.tr;
    out.flight = (a.tr.n - 1) / TRAJ_HZ; out.vHit = a.tr.v[a.tr.n - 1];
    out.reached = q.tgMat !== 'none' && a.tr.x[a.tr.n - 1] >= fp.pathLen * 0.995;
  }
  return out;
}
function boltLayers(bo, p, gB, t0, rnd, layers, ev, lab) {
  if (bo.type === 'none') return;
  var mv;
  if (bo.type === 'slug') {
    var a = bo.an, fp = bo.fp;
    if (a.crack) ev.push({ k: 'crack', t: t0 + a.crack.t, label: lab ? 'crack' : '' });
    else if (a.passed) ev.push({ k: 'pass', t: t0 + a.passT, label: lab ? 'pass' : '' });
    if (gB <= 0) return;
    if (a.crack) { var rc = Math.hypot(fp.D - a.crack.x, fp.miss), cb = crackBuf(a.crack); postLayer(cb, rc, p.ground); layers.push({ m: cb, t: t0 + a.crack.t, pan: (a.crack.x - fp.D) / rc * 0.9, g: gB }); }
    var wk = wakeLayer(fp, a.tr, bo.reached, rnd);
    if (wk) layers.push({ L: wk.L, R: wk.R, t: t0 + wk.t, g: gB });
    /* plasma sheath: above about Mach 4 the air behind the bow shock ionises and sizzles */
    var sh = p.bvSizzle * clamp((bo.v / C - 3.5) / 3, 0, 1), lp0 = 0;
    if (sh > 0.01) {
      mv = movingSource(a.tr, fp.D, fp.miss, function () { var w = rnd() * 2 - 1; lp0 += (w - lp0) * 0.3; return 25 * sh * (w - lp0); }, null);
      if (mv) layers.push({ L: mv.L, R: mv.R, t: t0 + mv.t, g: gB });
    }
    return;
  }
  var ch = bo.ch, segs = ch.segs, tMin = Infinity, tMax = 0, rMin = Infinity, rMax = 0, NB = 6, bins = [], k;
  segs.forEach(function (s) { if (s.ta < tMin) tMin = s.ta; if (s.ta > tMax) tMax = s.ta; if (s.r < rMin) rMin = s.r; if (s.r > rMax) rMax = s.r; });
  ev.push({ k: 'crack', t: t0 + tMin, label: lab ? (bo.type === 'beam' ? 'beam' : 'channel') : '' });
  if (gB <= 0) return;
  var lr = Math.log(rMax / rMin) || 1, len = Math.ceil((tMax - tMin + (bo.pulses - 1) * bo.period * 1.05 + ch.Tn * 4 + 0.12) * FS), close = segs[0];
  for (k = 0; k < bo.pulses; k++) {
    var tp = k * bo.period * (1 + 0.04 * (rnd() - 0.5)), gk = k ? 0.75 + 0.3 * rnd() : 1;
    segs.forEach(function (s) {
      var bi = Math.min(NB - 1, Math.floor(Math.log(s.r / rMin) / lr * NB));
      if (!bins[bi]) bins[bi] = { L: new Float32Array(len), R: new Float32Array(len), r: 0, n: 0 };
      var bn = bins[bi], pk = s.pk * gk * (0.6 + 0.8 * rnd()), T = ch.Tn * (0.8 + 0.45 * rnd()), ts = s.ta - tMin + tp + 0.001;
      if (!k) { bn.r += s.r; bn.n++; }
      addN(bn.L, ts, T, pk * Math.cos((s.pan + 1) * Math.PI / 4)); addN(bn.R, ts, T, pk * Math.sin((s.pan + 1) * Math.PI / 4));
    });
  }
  segs.forEach(function (s) { if (s.r < close.r) close = s; });
  var body = new Float32Array(len), pkAll = 0;
  bins.forEach(function (b) {
    if (!b) return;
    var pk = peakOf(b.L, b.R); if (pk > pkAll) pkAll = pk;
    for (var i = 0; i < len; i++) body[i] += (b.L[i] + b.R[i]) * 0.5;
    airFilter(b.L, b.r / b.n); airFilter(b.R, b.r / b.n);
    layers.push({ L: b.L, R: b.R, t: t0 + tMin - 0.001, g: gB });
  });
  /* the heated core expands and the air rushes back in behind it: a low whump under the crack */
  onePoleLP(body, 160); onePoleLP(body, 160); onePoleLP(body, 160);
  toPeak(body, 0.35 * pkAll);
  layers.push({ m: body, t: t0 + tMin - 0.001, pan: close.pan, g: gB });
  if (bo.type === 'bolt' && p.bvSizzle > 0.01 && bo.tr) {
    /* the bolt's own voice: a hot plasma ball hums, hisses and spits as it flies past, with Doppler */
    var ph = 0, lp = 0, ck = 0, hum = p.bvTone;
    mv = movingSource(bo.tr, p.D, p.miss, function (kk) {
      ph += hum * (1 + 0.03 * fsin(kk * 6 / FS)) / FS;
      var w = rnd() * 2 - 1; lp += (w - lp) * 0.35; ck *= 0.97;
      if (rnd() < 0.004) ck += (rnd() - 0.5) * 4;
      return 8 * p.bvSizzle * ((fsin(ph) + 0.4 * fsin(2 * ph + 0.1) + 0.25 * fsin(3 * ph + 0.3)) * 0.5 + 0.6 * (w - lp) + ck);
    }, null);
    if (mv) layers.push({ L: mv.L, R: mv.R, t: t0 + mv.t, g: gB });
  }
}

/* ---------- the target ---------- */
var ABL = { steel: { frac: 0.12, hiss: 0.25 }, aluminium: { frac: 0.18, hiss: 0.3 }, glass: { frac: 0.1, hiss: 0.2 }, ice: { frac: 0.35, hiss: 0.7 },
  wood: { frac: 0.25, hiss: 0.45 }, concrete: { frac: 0.2, hiss: 0.25 }, water: { frac: 0.45, hiss: 0.9 } };
var SPATTER = { steel: 'steel', aluminium: 'steel', glass: 'glass', ice: 'glass', wood: 'wood', concrete: 'concrete' };
function planTarget(q, bo, exitT) {
  if (q.tgMat === 'none') return null;
  if (bo.type === 'slug' && !bo.reached) return null;
  var E = bo.type === 'slug' ? 0.5 * bo.mass * bo.vHit * bo.vHit : q.tgEnergy, hits = [], k, P = bo.pulses || 1, x = Math.max(0, q.targetDist);
  for (k = 0; k < P; k++) hits.push({ te: exitT + bo.flight + k * bo.period, E: E / P });
  var rT = Math.max(0.5, Math.hypot(q.D - x, q.miss));
  return { mat: q.tgMat, x: x, rT: rT, pan: clamp((x - q.D) / rT, -1, 1) * 0.9, E: E, hits: hits,
    /* a kinetic hit only flash-boils the surface at hypervelocity; a plain strike (no bolt) does not at all */
    abl: bo.type === 'slug' ? clamp(bo.vHit / 3000, 0.05, 1) : bo.type === 'none' ? 0 : 1,
    plate: PLATES[q.tgMat] ? planPlate(q.tgMat, q.tgThick / 1000, q.tgSize) : null };
}
var BUBBLE = null;
function bubblePulse() {
  /* one collapse of a 5 mm steam bubble from the Rayleigh-Plesset model above, reused at every size */
  if (BUBBLE) return BUBBLE;
  var im = planImplosion({ imMedium: 'water', imDp: 1, imGas: 0.05, imR0: 0.005, imDist: 1 }), n = im.Q.length - 1, b = new Float32Array(n), i, pk = 0, ip = 0;
  for (i = 0; i < n; i++) { b[i] = im.rho * (im.Q[i + 1] - im.Q[i]) * FS; if (Math.abs(b[i]) > pk) { pk = Math.abs(b[i]); ip = i; } }
  var a = Math.max(0, ip - Math.round(0.0015 * FS)), e = Math.min(n, ip + Math.round(0.006 * FS)), out = b.slice(a, e);
  for (i = 0; i < out.length; i++) out[i] *= Math.min(1, i / 16, (out.length - i) / 64);
  toPeak(out, 1);
  return (BUBBLE = out);
}
function targetLayers(tg, p, g3, g4, t0, rnd, layers, ev, lab) {
  var rT = tg.rT, mat = tg.mat, Et = tg.E, first = tg.hits[0], last = tg.hits[tg.hits.length - 1], i, k, buf;
  var tH = t0 + first.te + rT / C, lvl = 10 * Math.sqrt(Math.max(Et, 0.01));   // Pa at 1 m for the struck body: set against the bolt, not measured
  function put(b, t, g) { scale(b, 1 / rT); airFilter(b, rT); layers.push({ m: b, t: t, pan: tg.pan, g: g }); }
  ev.push({ k: 'impact', t: tH, label: lab ? 'impact' : '' });
  if (g3 > 0) {
    /* ablation: the energy that boils the surface off acts as a small blast, then the vapour jet hisses */
    var A = ABL[mat], abl = [];
    for (k = 0; k < (tg.abl > 0 ? Math.min(3, tg.hits.length) : 0); k++) {
      var Eh = tg.hits[k].E, b = blastParams(clamp(Eh * A.frac * tg.abl / 4.184e6, 1e-9, 100), rT);
      var ab = new Float32Array(Math.ceil((b.td * 14 + 0.3) * FS) + 2400);
      addShape(ab, 0.0005, b.td * 9, function (t) { var u = t / b.td; return b.peak * (1 - u) * Math.exp(-1.2 * u); });
      noiseBurst(ab, 0.0008, 0.02 + 0.04 * Math.log10(1 + Eh / 50), 1500, 12000, A.hiss * b.peak * 0.5 * tg.abl, rnd, 0.0005);
      postLayer(ab, rT, p.ground * 0.5); abl.push(ab);
    }
    if (abl.length) tg.hits.forEach(function (h, kk) { layers.push({ m: abl[kk % abl.length], t: t0 + h.te + rT / C, pan: tg.pan, g: g3 }); });
    if (tg.plate) {
      /* the plate rings with bending waves; a pulsed beam strikes it again before it settles */
      var ir = bendIR(tg.plate, mat === 'wood' ? 3000 : 7000, rnd), P = tg.hits.length;
      toPeak(ir, lvl);
      if (P > 1) {
        var span = Math.round((last.te - first.te) * FS), cv = new Float32Array(ir.length + span + 8);
        tg.hits.forEach(function (h) { addAt(cv, ir, h.te - first.te, (0.7 + 0.3 * rnd()) / Math.sqrt(P)); });
        ir = cv;
      }
      put(ir, tH, g3);
    } else if (mat === 'concrete') {
      buf = modalHit('concrete', Et * 0.2, clamp(Math.pow(500 / Math.max(Et, 1), 0.15), 0.3, 2), rnd); toPeak(buf, 0.8 * lvl); put(buf, tH, g3);
    } else if (mat === 'water') {
      buf = new Float32Array(Math.ceil(2.5 * FS));
      noiseBurst(buf, 0, 0.18 + 0.1 * Math.log10(1 + Et / 1000), 150, 3000, 0.6 * lvl, rnd, 0.002);   // splash
      var bp = bubblePulse(), nb = Math.round(10 + 30 * Math.log10(1 + Et / 100));
      for (k = 0; k < nb; k++) {
        /* steam bubbles collapse in the cold water around the hit: a crackle of sharp pulses */
        var R = 0.0005 + 0.0035 * Math.pow(rnd(), 1.5), st = stretch(bp, Math.max(0.15, R / 0.005)), tt = 0.01 + 0.25 * -Math.log(1 - rnd() * 0.97);
        addAt(buf, st, tt, 0.12 * lvl * (R / 0.004) * (0.5 + rnd()));
      }
      put(buf, tH, g3);
    }
    if (SPATTER[mat]) {
      /* molten droplets, shards or chips land around the hit */
      var ns = Math.round(3 + 5 * Math.log10(1 + Et / 100) * (mat === 'glass' || mat === 'concrete' ? 2 : 1)), sp = new Float32Array(Math.ceil(1.2 * FS));
      for (k = 0; k < ns; k++) {
        var hb = modalHit(SPATTER[mat], 0.02 * (0.2 + rnd()), 2.5 + 3 * rnd(), rnd, { maxModes: 3, t60Scale: 0.35, noGrains: true });
        addAt(sp, hb, 0.04 + 0.5 * Math.pow(rnd(), 1.5), 0.5 + rnd());
      }
      toPeak(sp, 0.12 * lvl); put(sp, tH, g3);
    }
  }
  if (g4 > 0 && p.tgHeat > 0.01) {
    var heat = p.tgHeat, t1 = t0 + last.te + rT / C, steam = mat === 'ice' || mat === 'water';
    /* sizzle: the hot spot boils and spits, then calms as it cools */
    var ts = (steam ? 0.8 : 0.3) + (steam ? 2.2 : 1.6) * heat, n = Math.ceil((ts * 3 + 0.1) * FS), sz = new Float32Array(n), lp = 0, ck = 0, nf = n / 3;
    for (i = 0; i < n; i++) {
      var t = i / FS, w = rnd() * 2 - 1; lp += (w - lp) * (steam ? 0.25 : 0.12); ck *= 0.92;
      if (rnd() < 0.002 * Math.exp(-t / ts) * (steam ? 0.5 : 1.5)) ck += (rnd() - 0.3) * 6;
      sz[i] = ((w - lp) * (steam ? 1 : 0.5) + ck) * Math.exp(-t / ts) * Math.min(1, t / 0.02, (n - i) / nf);
    }
    toPeak(sz, lvl * 1.2 * heat * (steam ? 1.6 : 1)); put(sz, t1 + 0.01, g4);
    if (mat !== 'water') {
      /* ticks: the hot spot contracts and the body clicks. Ice cracks instead, and each crack sings along the sheet */
      var nt = Math.round(heat * (mat === 'ice' ? 10 : 22)), tau = 0.5 + 1.6 * heat, tb = new Float32Array(Math.ceil((tau * 3 + 1.4) * FS));
      for (k = 0; k < nt; k++) {
        var tt2 = 0.2 + tau * -Math.log(1 - rnd() * 0.95);
        if (mat === 'ice' && tg.plate) {
          var cr = new Float32Array(Math.ceil(1.2 * FS));
          bendChirp(cr, 0, 5 + 60 * rnd(), tg.plate.kap, 1, 9000, 40, 0.004, 6000, rnd());
          toPeak(cr, 0.3 + 0.7 * rnd()); addAt(tb, cr, tt2);
        } else {
          var tk = modalHit(SPATTER[mat] || 'steel', 0.01 * (0.2 + rnd()), 2.5 + 3 * rnd(), rnd, { maxModes: 3, t60Scale: 0.35, noGrains: true });
          toPeak(tk, 0.3 + 0.7 * rnd()); addAt(tb, tk, tt2);
        }
      }
      toPeak(tb, lvl * (mat === 'ice' ? 1.5 : 0.6) * heat); put(tb, t1, g4);
    }
    ev.push({ k: 'pass', t: t1 + 0.2, label: lab ? (mat === 'ice' ? 'cracks' : steam ? 'steam' : 'cooling') : '' });
  }
}

/* sweep curves for the diagram: frequency against arrival time, per dispersive path */
function sweepCurve(t0, d, kap, fHi, fLo) {
  var K = d * d / (8 * Math.PI * kap), pts = [], i;
  for (i = 0; i <= 32; i++) { var f = fHi * Math.pow(fLo / fHi, i / 32); pts.push([t0 + Math.sqrt(K / f), f]); }
  return pts;
}
function planWeapon(q, grnd) {
  var vExit = q.bvType === 'slug' || q.bvType === 'bolt' ? q.bvSpeed : 2000;
  var ln = planLauncher(q, vExit), exitT = ln.tC + ln.transit, bo = planBolt(q, grnd), tg = planTarget(q, bo, exitT);
  var r0 = Math.max(0.5, Math.hypot(q.D, q.miss)), curves = [], tA = r0 / C + ln.tC, i, j;
  if (ln.line) {
    var bp = ln.line;
    bp.echoes.forEach(function (e, k) { var pts = []; for (i = 0; i < bp.K; i += 2) pts.push([tA + e.m * bp.tau[i], bp.f[i]]); curves.push({ pts: pts, w: k ? Math.max(0.3, e.g) : 1, c: k ? 'shock' : 'tracer' }); });
  }
  if (ln.rail) {
    var rp = ln.rail.paths.slice().sort(function (u, v) { return u.d - v.d; }).slice(0, 6);
    rp.forEach(function (q2, k) { curves.push({ pts: sweepCurve(tA, q2.d, ln.rail.kap, 16000, 30), w: Math.max(0.3, 1 - k * 0.12), c: 'ink' }); });
  }
  if (tg && tg.plate) {
    var tT = tg.hits[0].te + tg.rT / C, pp = tg.plate.paths.slice().sort(function (u, v) { return u.d - v.d; }).slice(0, 8);
    pp.forEach(function (q2, k) { curves.push({ pts: sweepCurve(tT, q2.d, tg.plate.kap, 16000, tg.plate.fLo), w: Math.max(0.3, 1 - k * 0.1), c: k ? 'shock' : 'tracer' }); });
  }
  var marks = [];
  if (ln.tC > 0) marks.push([r0 / C, 'charge']);
  if (ln.type !== 'none') marks.push([tA, 'fire']);
  if (ln.stages) for (j = 1; j < ln.stages.length; j++) marks.push([tA + ln.stages[j].t, '']);
  if (tg) marks.push([tg.hits[0].te + tg.rT / C, 'impact']);
  return { ln: ln, bo: bo, tg: tg, exitT: exitT, r0: r0, pan0: -q.D / r0 * 0.9, curves: curves, marks: marks };
}
function weaponLayers(wp, p, o, rnd, layers, ev, lab) {
  launcherLayers(wp.ln, p, o.g1, o.t0, wp.r0, clamp(wp.pan0 + o.pan, -1, 1), rnd, layers, ev, lab);
  boltLayers(wp.bo, p, o.g2, o.t0 + wp.exitT, rnd, layers, ev, lab);
  if (wp.tg) targetLayers(wp.tg, p, o.g3, o.g4, o.t0, rnd, layers, ev, lab);
}

/* ---------- forcefield: a driven sheet of modes, two detuned generators and a struck response ----------
   Patterns: membrane, plate and harmonic are analogies. Plasma is a reduced magnetohydrodynamic model:
   a magnetised plasma carries shear, fast and slow waves whose speeds follow field strength, density,
   pressure (beta) and direction. Pitch is scaled into hearing; the scale factor is reported. */
var FF_RATIOS = { membrane: [1, 1.594, 2.136, 2.296, 2.653, 2.918, 3.156, 3.501, 3.6, 4.06, 4.6, 5.1, 5.54, 6.1, 6.75, 7.4, 8.3, 9.2, 10.4, 11.9],
  plate: [1, 2.3, 3.9, 5.4, 6.3, 8.2, 9.6, 11.4, 13.1], harmonic: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] };
var MU0 = 4e-7 * Math.PI, MPROT = 1.6726e-27;
function planField(p, grnd) {
  var mode = p.ffMode, plasma = p.ffType === 'plasma', f0 = p.ffBase, modes = [], k, rs = null, top = 0;
  function mk(f, r, a, fam) { modes.push({ f: f, r: r, a: a, ph: grnd(), lf: 1 + Math.floor(grnd() * 9), lp: grnd(), fam: fam }); if (f > top) top = f; }
  if (plasma) {
    /* Alfven speed B / sqrt(mu0 rho): pitch rises with field strength and falls with density */
    f0 = clamp(p.ffBase * p.ffB * Math.sqrt(1e19 / p.ffDens), 15, 800);
    var th = p.ffAngle * Math.PI / 180, cs2 = 5 / 6 * p.ffBeta, c2 = Math.cos(th) * Math.cos(th), sum = 1 + cs2, disc = Math.sqrt(Math.max(0, sum * sum - 4 * cs2 * c2)), wt = [0.55, 1, 0.8];
    rs = [Math.sqrt(Math.max(1e-4, (sum - disc) / 2)), Math.max(0.02, Math.cos(th)), Math.sqrt((sum + disc) / 2)];
    for (var fam = 0; fam < 3; fam++) for (k = 1; k <= 6; k++) {
      var f = f0 * rs[fam] * k * (1 + (grnd() - 0.5) * 0.004);
      if (f >= 18 && f <= 9000) mk(f, rs[fam] * k, wt[fam] * (0.7 + 0.6 * grnd()) / Math.pow(k, 1.2), fam);
    }
    /* surface ripple answers at half the drive frequency (Faraday waves); capillary dispersion makes each harmonic drift */
    if (p.ffSurface > 0.01) for (k = 1; k <= 10; k++) {
      var fs = f0 / 2 * k - 0.35 * Math.pow(k, 1.5);
      if (fs >= 18) mk(fs, k / 2, p.ffSurface * 0.7 * (0.7 + 0.6 * grnd()) / k, 3);
    }
    if (!modes.length) mk(f0, 1, 1, 1);
  } else {
    var rat = FF_RATIOS[p.ffType] || FF_RATIOS.membrane;
    for (k = 0; k < rat.length; k++) {
      var fm = f0 * rat[k] * (1 + (grnd() - 0.5) * 0.012);
      if (fm > 9000) break;
      mk(fm, rat[k], (0.6 + 0.8 * grnd()) / Math.pow(1 + k, 1.1), k ? 2 : 1);
    }
  }
  var vA = plasma ? p.ffB / Math.sqrt(MU0 * p.ffDens * MPROT) : 0;
  return { f0: f0, modes: modes, mode: mode, dur: mode === 'hum' ? LOOP_S : mode === 'impact' ? 4.2 : 3.6,
    tHit: mode === 'impact' || mode === 'powerdown' ? 0.9 : 0, r: Math.max(0.5, p.ffDist), beat: p.ffBeat, top: top,
    plasma: plasma, rs: rs, vA: vA, fReal: vA / 4, sawT: plasma && p.ffSaw > 0.01 ? clamp(p.ffSawT, 0.2, 6) : 0 };
}
var FF_HUM = 2;
/* gliding tone with a sin^2 envelope; curve < 0 gives the 1/t^2 fall of a whistler */
function addTone(mid, side, t0, len, fA, fB, amp, pan, periodic, curve) {
  var ns = mid.length, n0 = Math.round(t0 * FS), n = Math.round(len * FS), ph = 0, q = Math.sqrt(fA / fB) - 1, i;
  for (i = 0; i < n; i++) {
    var u = i / n, f = curve < 0 ? fA / Math.pow(1 + u * q, 2) : fA + (fB - fA) * Math.pow(u, curve), idx = n0 + i;
    ph += f / FS;
    if (idx >= ns) { if (!periodic) break; idx -= ns; }
    var e = Math.sin(Math.PI * u), s = amp * e * e * fsin(ph);
    mid[idx] += s; side[idx] += s * pan;
  }
}
/* a soliton passing the listener: sech^2 pulse, taller ones are narrower and brighter, sweeping across the image */
function addSoliton(mid, side, tc, A, f0, amp, periodic, rnd) {
  var ns = mid.length, w = 0.09 / Math.sqrt(A), n = Math.round(w * 8 * FS), n0 = Math.round((tc - 4 * w) * FS), f = f0 * (2 + 2 * A), lp = 0, i;
  for (i = 0; i < n; i++) {
    var x = (i / FS - 4 * w) / w, sech = 1 / Math.cosh(x), idx = n0 + i;
    lp += ((rnd() * 2 - 1) - lp) * 0.12;
    if (idx < 0) { if (!periodic) continue; idx += ns; } else if (idx >= ns) { if (!periodic) break; idx -= ns; }
    var s = amp * A * sech * sech * (0.7 * fsin(f * i / FS) + 1.6 * lp);
    mid[idx] += s; side[idx] += s * Math.tanh(x) * 0.8;
  }
}
function sparkCluster(mid, side, t0, count, spread, amp, rnd) {
  for (var k = 0; k < count; k++) {
    var ts = t0 + 0.001 - Math.log(rnd() + 1e-6) * spread, pk = amp * (0.15 + 0.85 * rnd()), T = 0.00008 + 0.00022 * rnd(), pn = (rnd() * 2 - 1) * 0.7;
    if (ts + T < mid.length / FS - 0.001) { addN(mid, ts, T, pk); addN(side, ts, T, pk * pn); }
  }
}
function fieldSignal(pl, p, o, rnd, ns, periodic) {
  var Lp = ns / FS, Ls = periodic ? Lp : 4, M = pl.modes.length, plasma = pl.plasma, fa = [], fb = [], pa = new Float64Array(M), pb = new Float64Array(M);
  var mid = new Float32Array(ns), side = new Float32Array(ns), gA = new Float32Array(ns), pA = new Float32Array(ns), k, i, e = 0, hz = null, pm = 0;
  var saw = pl.sawT ? p.ffSaw : 0, Ts = pl.sawT || 1, kph = 0, td = -1, crashes = [];
  if (periodic && saw) Ts = Lp / Math.max(1, Math.round(Lp / Ts));
  /* level and pitch envelopes first, so loop frequencies can be fitted to the average pitch */
  for (i = 0; i < ns; i++) {
    var t = i / FS, g = 1, pf = 1, dt, falling = pl.mode === 'powerdown' && t > pl.tHit;
    if (pl.mode === 'impact' && t > pl.tHit) { dt = t - pl.tHit; g = 1 + 1.6 * Math.exp(-dt / 0.12) - 0.45 * Math.exp(-dt / 0.9) * (1 - Math.exp(-dt / 0.15)); pf = 1 + 0.04 * Math.exp(-dt / 0.25); }
    else if (pl.mode === 'powerup') { g = Math.min(1, Math.pow(t / 1.6, 1.5)) * (1 + 0.25 * Math.exp(-Math.pow((t - 1.6) / 0.25, 2))); pf = 0.5 + 0.5 * (1 - Math.exp(-t / 0.45)); }
    else if (falling) {
      dt = t - pl.tHit;
      if (plasma) {
        /* kink instability: a helical wobble that grows exponentially until the column disrupts */
        var d = 0.05 * Math.exp(dt / 0.35);
        if (d < 1) { kph += (5 + 9 * d) / FS; g = 1 + 0.7 * d * fsin(kph); pf = 1 + 0.09 * d * fsin(kph + 0.25); }
        else { if (td < 0) td = t; g = 1.7 * Math.exp(-(t - td) / 0.12); pf = Math.exp(-(t - td) / 0.3); }
      } else { g = Math.exp(-dt / 0.55); pf = 0.25 + 0.75 * Math.exp(-dt / 0.8); }
    }
    if (saw && !falling) {
      /* reconnection cycle: stress builds along a ramp, then the field snaps back in a few milliseconds */
      var s = (t / Ts) % 1, eps = 0.004 / Ts, st = s < 1 - eps ? s : (1 - eps) * (1 - (s - (1 - eps)) / eps);
      pf *= 1 + 0.05 * saw * (st - 0.5); g *= 1 + saw * (0.3 * st - 0.2);
    }
    gA[i] = g; pA[i] = pf; pm += pf;
  }
  pm /= ns;
  if (saw) for (k = periodic ? 0 : 1; k * Ts < Lp - 0.06; k++) if (!(pl.mode === 'powerdown' && k * Ts > pl.tHit)) crashes.push(k * Ts);
  for (k = 0; k < M; k++) {
    var f1 = pl.modes[k].f, f2 = f1 + pl.beat * pl.modes[k].r;
    if (periodic) { f1 = Math.round(f1 * pm * Lp) / (pm * Lp); f2 = Math.round(f2 * pm * Lp) / (pm * Lp); }
    fa.push(f1); fb.push(f2); pa[k] = pl.modes[k].ph; pb[k] = pl.modes[k].ph + 0.37; e += pl.modes[k].a * pl.modes[k].a;
  }
  var norm = 1 / Math.sqrt(e);
  if (o.g2 > 0 && p.ffCorona > 0) {
    var w = new Float32Array(ns), a1 = Math.exp(-TAU * 2500 / FS), a2 = Math.exp(-TAU * 9000 / FS), s1 = 0, s2 = 0, pass, eh = 0;
    hz = new Float32Array(ns);
    for (i = 0; i < ns; i++) w[i] = rnd() * 2 - 1;
    for (pass = periodic ? 0 : 1; pass < 2; pass++) for (i = 0; i < ns; i++) { s1 = w[i] + (s1 - w[i]) * a1; var h = w[i] - s1; s2 = h + (s2 - h) * a2; hz[i] = s2; }
    for (i = 0; i < ns; i++) eh += hz[i] * hz[i];
    scale(hz, 1 / (Math.sqrt(eh / ns) || 1));
  }
  var fc0 = periodic ? Math.round(fa[0] * Lp) / Lp : fa[0];
  for (i = 0; i < ns; i++) {
    var tt = i / FS, A = 0, Bv = 0, gg = gA[i], pp = pA[i];
    for (k = 0; k < M; k++) {
      var md = pl.modes[k], sh = 1 + p.ffShimmer * 0.8 * (k / M) * fsin(md.lf * tt / Ls + md.lp);
      pa[k] += fa[k] * pp / FS; pb[k] += fb[k] * pp / FS;
      A += md.a * sh * fsin(pa[k]); Bv += md.a * sh * fsin(pb[k]);
    }
    var hum = o.g1 * FF_HUM * norm * gg;
    /* corona hisses twice per drive cycle */
    var cor = hz ? o.g2 * p.ffCorona * 0.5 * FF_HUM * hz[i] * gg * (0.55 + 0.45 * Math.abs(fsin(fc0 * tt))) : 0;
    mid[i] = hum * (A + Bv) * 0.5 + cor; side[i] = hum * (A - Bv) * 0.35;
  }
  if (plasma) {
    var live = pl.mode === 'powerdown' ? (td > 0 ? td : pl.tHit + 1) : Lp;
    if (o.g4 > 0) crashes.forEach(function (tc) { sparkCluster(mid, side, tc, 6 + Math.floor(8 * rnd()), 0.008, o.g4 * FF_HUM * 1.5 * saw, rnd); });
    if (o.g2 > 0 && p.ffChorus > 0.01) {
      /* chorus: short rising tones, as in whistler-mode emissions from a stressed magnetosphere */
      var nc = Math.round(p.ffChorus * live * 4);
      for (k = 0; k < nc; k++) {
        /* chorus sits below the electron gyrofrequency, so its band rises with field strength, not with the hum */
        var fA = clamp(900 * Math.sqrt(p.ffB) * (1 + 0.6 * rnd()), 300, 3500), len = 0.12 + 0.33 * rnd(), t0 = rnd() * (periodic ? Lp : Math.max(0.1, live - len));
        addTone(mid, side, t0, len, fA, Math.min(7000, fA * (1.6 + 0.8 * rnd())), o.g2 * FF_HUM * 0.18 * p.ffChorus * (0.3 + 0.7 * rnd()), (rnd() * 2 - 1) * 0.7, periodic, 1.3);
      }
    }
    if (o.g1 > 0 && p.ffSoliton > 0.01) {
      var sa = o.g1 * FF_HUM * 0.5 * p.ffSoliton, j;
      if (pl.mode === 'impact') {
        /* an impact launches solitons round the field; taller ones travel faster, so the returns drift apart */
        for (k = 0; k < 2 + Math.round(p.ffSoliton * 3); k++) {
          var Ak = 0.4 + 0.6 * rnd(), Tk = 0.9 / (0.6 + Ak);
          for (j = 1; pl.tHit + j * Tk < Lp - 0.5; j++) addSoliton(mid, side, pl.tHit + j * Tk, Ak * Math.exp(-0.35 * (j - 1)), pl.f0, sa * 1.6, false, rnd);
        }
      } else if (pl.mode === 'hum') {
        for (k = 0; k < 1 + Math.round(p.ffSoliton * 2); k++) {
          var Ah = 0.5 + 0.5 * rnd(), np = 2 + Math.round(Ah * 3) + k, off = rnd();
          for (j = 0; j < np; j++) addSoliton(mid, side, (j + off) * Lp / np, Ah, pl.f0, sa, periodic, rnd);
        }
      }
    }
  }
  return { mid: mid, side: side, td: td };
}
function fieldLayers(pl, p, o, rnd, layers, ev, lab) {
  var ns = Math.ceil(pl.dur * FS), r = pl.r, tA = o.t0 + r / C, sig = fieldSignal(pl, p, o, rnd, ns, false), i, k;
  var L = new Float32Array(ns), R = new Float32Array(ns), fi = Math.round(0.15 * FS), fo = Math.round(0.3 * FS);
  for (i = 0; i < ns; i++) { var fd = Math.min(1, i / fi, (ns - i) / fo); L[i] = (sig.mid[i] + sig.side[i]) / r * fd; R[i] = (sig.mid[i] - sig.side[i]) / r * fd; }
  airFilter(L, r); airFilter(R, r);
  layers.push({ L: L, R: R, t: tA, g: 1 });
  var E = pl.mode === 'impact' ? p.ffHitE : pl.mode === 'powerup' ? 100 : 30, hit = FF_HUM * Math.pow(E, 0.25);
  var tEv = pl.plasma && pl.mode === 'powerdown' && sig.td > 0 ? sig.td : pl.tHit;
  if (pl.mode === 'impact' && o.g3 > 0) {
    /* struck sheet: stretched modes start sharp and settle, the higher ones bloom late like a gong */
    var rn = Math.ceil(3.2 * FS), rb = new Float32Array(rn + 64), beta = p.ffGlide * 0.7, fl = [], last = pl.top;
    pl.modes.forEach(function (m) { fl.push(m.f); });
    for (k = 1; fl.length < 18 && last + k * 0.55 * pl.f0 < 9000; k++) fl.push(last + k * 0.55 * pl.f0);
    fl.sort(function (a, b) { return a - b; });
    if (fl.length > 22) fl = fl.filter(function (f, q) { return q % 2 === 0 || q < 6; });
    var ph = new Float64Array(fl.length), en = new Float64Array(fl.length), at = new Float64Array(fl.length), dd = [], da = [];
    for (k = 0; k < fl.length; k++) { en[k] = 1; at[k] = 1; dd.push(Math.exp(-6.9 / (2.5 / (1 + 0.25 * k) * FS))); da.push(Math.exp(-1 / ((0.004 + 0.03 * k * p.ffGlide) * FS))); }
    var gl = 1, gd = Math.exp(-1 / (0.22 * FS));
    for (i = 0; i < rn; i++) {
      var pf = Math.sqrt(1 + beta * gl), y = 0; gl *= gd;
      for (k = 0; k < fl.length; k++) { ph[k] += fl[k] * pf / FS; en[k] *= dd[k]; at[k] *= da[k]; y += fsin(ph[k]) * en[k] * (1 - at[k]) / Math.pow(1 + k, 0.6); }
      rb[i] = y;
    }
    toPeak(rb, 0.6 * hit / r); airFilter(rb, r);
    layers.push({ m: rb, t: tA + pl.tHit, pan: o.pan, g: o.g3 });
  }
  if (o.g4 > 0) {
    var cn = Math.ceil(2.2 * FS), cm = new Float32Array(cn), cs = new Float32Array(cn), disrupt = pl.plasma && pl.mode === 'powerdown';
    var cnt = pl.mode === 'impact' ? 34 : pl.mode === 'powerup' ? 18 : pl.mode === 'powerdown' ? 26 : 0;
    if (cnt) {
      if (pl.mode !== 'powerdown' || disrupt) addN(cm, 0.001, 0.00025, 1.2 * hit);
      sparkCluster(cm, cs, 0.001, cnt, pl.mode === 'powerdown' && !disrupt ? 0.4 : 0.05, 0.5 * hit, rnd);
      if (disrupt) {
        /* the disruption dumps the stored field energy: a low thud under the sparks */
        var tp = 0;
        for (i = 0; i < Math.round(0.5 * FS); i++) { var tq = i / FS; tp += (30 + 70 * Math.exp(-tq / 0.06)) / FS; cm[i] += 2.2 * FF_HUM * fsin(tp) * Math.exp(-tq / 0.16) * (1 - Math.exp(-tq / 0.003)); }
      }
      if (pl.plasma && pl.mode === 'impact') {
        /* each spark sends a whistler: dispersion makes the highs arrive first, so the tone falls */
        for (k = 0; k < 3 + Math.floor(3 * rnd()); k++) addTone(cm, cs, 0.15 + 0.5 * rnd(), 0.8 + 0.6 * rnd(), 5000 + 2000 * rnd(), 300 + 200 * rnd(), 0.12 * hit * (0.5 + 0.5 * rnd()), (rnd() * 2 - 1) * 0.7, false, -1);
      }
      var cl = new Float32Array(cn), cr = new Float32Array(cn);
      for (i = 0; i < cn; i++) { cl[i] = (cm[i] + cs[i]) / r; cr[i] = (cm[i] - cs[i]) / r; }
      airFilter(cl, r); airFilter(cr, r);
      layers.push({ L: cl, R: cr, t: tA + tEv, g: o.g4 });
    }
  }
  var nm = { impact: 'impact', powerup: 'ignite', powerdown: disruptName(pl) }[pl.mode];
  if (nm) ev.push({ k: pl.mode === 'impact' ? 'impact' : 'launch', t: tA + tEv, label: lab ? nm : '' });
}
function disruptName(pl) { return pl.plasma ? 'disruption' : 'collapse'; }

/* ---------- recordings and impulse responses ----------
   Recordings and impulse responses come in from outside as assets: 48 kHz stereo Float32Arrays, set with setAsset()
   (the page decodes the files; the worker gets a copy). Three synthetic examples stand in until a file is loaded. */
var ASSETS = {}, REC_MAX_S = 15, IR_MAX_S = 6;
function setAsset(id, a) {
  var n = Math.min(a.L.length, Math.round(REC_MAX_S * FS)), k;
  ASSETS[id] = { name: a.name || id, L: a.L.subarray(0, n), R: (a.R || a.L).subarray(0, n) };
  for (k in READ) if (k.split('|')[1] === id) delete READ[k];
  return ASSETS[id];
}
function removeAsset(id) {
  delete ASSETS[id];
  for (var k in READ) if (k.split('|')[1] === id) delete READ[k];
}
function getAsset(id) {
  if (ASSETS[id]) return ASSETS[id];
  if (EXAMPLES[id]) { var s = EXAMPLES[id].make(); ASSETS[id] = { name: EXAMPLES[id].name, L: s.L, R: s.R }; return ASSETS[id]; }
  return null;
}
/* an impulse response as loaded: silence before the first sound (bar 1 ms) and after the tail cut, at most IR_MAX_S
   long, peak 1. A recorded clap or knock then starts on time. */
function prepareIR(L, R) {
  R = R || L;
  var pk = peakOf(L, R) || 1, s0 = 0, on = pk * 0.02;
  while (s0 < L.length - 1 && Math.abs(L[s0]) < on && Math.abs(R[s0]) < on) s0++;
  s0 = Math.max(0, s0 - Math.round(0.001 * FS));
  var thr = pk * 1e-4, e = Math.min(L.length, s0 + Math.round(IR_MAX_S * FS)) - 1;
  while (e > s0 && Math.abs(L[e]) < thr && Math.abs(R[e]) < thr) e--;
  var n = Math.max(1, e - s0 + 1);
  var a = new Float32Array(n), b = new Float32Array(n), fo = Math.min(n >> 2, Math.round(0.01 * FS)), i;
  for (i = 0; i < n; i++) { a[i] = L[s0 + i] / pk; b[i] = R[s0 + i] / pk; }
  for (i = 0; i < fo; i++) { a[n - 1 - i] *= i / fo; b[n - 1 - i] *= i / fo; }
  return { L: a, R: b };
}

/* Fast convolution. Two real channels share one complex FFT: (L + iR) * h = L*h + i R*h for a real h. A stereo
   response runs twice, keeping L*hL from the first pass and R*hR from the second. */
function fftConvolve(L, R, hL, hR) {
  var nh = Math.max(hL.length, hR ? hR.length : 0), n = L.length + nh - 1, N = 1, k;
  while (N < n) N <<= 1;
  var Xr = new Float64Array(N), Xi = new Float64Array(N);
  Xr.set(L); Xi.set(R);
  fft(Xr, Xi);
  function pass(h) {
    var Yr = new Float64Array(N), Yi = new Float64Array(N);
    Yr.set(h); fft(Yr, Yi);
    for (k = 0; k < N; k++) {
      var a = Xr[k] * Yr[k] - Xi[k] * Yi[k], b = Xr[k] * Yi[k] + Xi[k] * Yr[k];
      Yr[k] = a; Yi[k] = -b;   // conjugate: a forward FFT of the conjugate is the inverse, conjugated
    }
    fft(Yr, Yi);
    return { re: Yr, im: Yi };
  }
  var p1 = pass(hL), p2 = hR && hR !== hL ? pass(hR) : p1, oL = new Float32Array(n), oR = new Float32Array(n);
  for (k = 0; k < n; k++) { oL[k] = p1.re[k] / N; oR[k] = -p2.im[k] / N; }
  return { L: oL, R: oR };
}

/* ---------- synthetic examples, so that every preset plays before a recording is loaded ---------- */
function makeEngine() {
  /* a four-cylinder engine at about 1800 rpm: 60 firings a second, uneven from cylinder to cylinder,
     through two exhaust resonances, with intake roar */
  var rnd = rng(77), n = 8 * FS, x = new Float32Array(n), ph = 0, i, k = 0;
  for (i = 0; i < n; i++) {
    var t = i / FS, f = 60 * (1 + 0.025 * Math.sin(TAU * 0.31 * t) + 0.01 * Math.sin(TAU * 1.7 * t));
    ph += f / FS;
    if (ph >= 1) { ph -= 1; k++; x[i] += (0.65 + 0.35 * rnd()) * (k % 4 === 1 ? 1.25 : 1); }
  }
  onePoleLP(x, 1200); onePoleLP(x, 1800);
  biquad(x, 'pk', 115, 3, 12); biquad(x, 'pk', 640, 2, 6); biquad(x, 'hp', 35, 0.7);
  var nz = shapedNoise(n, rnd, 2500, 120); toPeak(nz, 0.15 * peakOf(x));
  for (i = 0; i < n; i++) x[i] += nz[i];
  toPeak(x, 0.9);
  return { L: x, R: x.slice() };
}
function makeRain() {
  /* drops at about 250 a second: a click as each one lands, and a rising ping when it traps a bubble
     (the bubble rings near 3.3 kHz per millimetre of radius, Minnaert) */
  var rnd = rng(78), n = 8 * FS, L = new Float32Array(n), R = new Float32Array(n), t = 0, i;
  while (t < 8 - 0.05) {
    t += -Math.log(1 - rnd()) / 250;
    var a = Math.pow(rnd(), 2) * (0.3 + 0.7 * rnd()), pan = rnd() * 2 - 1, gl = Math.cos((pan + 1) * Math.PI / 4), gr = Math.sin((pan + 1) * Math.PI / 4);
    addN(L, t, 0.00015, a * gl); addN(R, t, 0.00015, a * gr);
    if (rnd() < 0.25) {
      var f0 = 3260 / (1 + 2 * rnd()), tau = 0.004 + 0.01 * rnd(), n0 = Math.round((t + 0.0005) * FS), m = Math.round(tau * 6 * FS), ph = 0;
      for (i = 0; i < m && n0 + i < n; i++) {
        var u = i / FS; ph += f0 * (1 + 0.1 * u / tau) / FS;
        var s = 0.5 * a * Math.exp(-u / tau) * fsin(ph);
        L[n0 + i] += s * gl; R[n0 + i] += s * gr;
      }
    }
  }
  var bed = shapedNoise(n, rnd, 6000, 300), bed2 = shapedNoise(n, rnd, 6000, 300);
  toPeak(bed, 0.04); toPeak(bed2, 0.04);
  for (i = 0; i < n; i++) { L[i] += bed[i]; R[i] += bed2[i]; }
  var pk = peakOf(L, R) || 1; scale(L, 0.9 / pk); scale(R, 0.9 / pk);
  return { L: L, R: R };
}
function makeVoice() {
  /* sung vowels a, o, i on 110 Hz: a glottal pulse train through three formant resonances that glide between vowels */
  var rnd = rng(79), n = Math.round(3.6 * FS), x = new Float32Array(n), ph = 0, i, j;
  var V = [[0, 730, 1090, 2440], [1.15, 730, 1090, 2440], [1.45, 570, 840, 2410], [2.2, 570, 840, 2410], [2.5, 270, 2290, 3010], [3.6, 270, 2290, 3010]];
  var y1 = [0, 0, 0], y2 = [0, 0, 0], bw = [80, 90, 120], lp = 0;
  for (i = 0; i < n; i++) {
    var t = i / FS, f0 = 110 * (1 + 0.018 * Math.sin(TAU * 5.2 * t) + 0.004 * (rnd() - 0.5));
    ph += f0 / FS; if (ph >= 1) ph -= 1;
    var g = ph < 0.6 ? 0.5 - 0.5 * Math.cos(Math.PI * ph / 0.6) : Math.cos(Math.PI * (ph - 0.6) / 0.8), src = g - lp; lp = g;
    src += 0.003 * (rnd() - 0.5);
    for (j = 0; j < V.length - 1 && V[j + 1][0] < t; j++);
    var a = V[j], b = V[Math.min(j + 1, V.length - 1)], w = b[0] > a[0] ? (t - a[0]) / (b[0] - a[0]) : 0, out = 0, k;
    for (k = 0; k < 3; k++) {
      var F = a[k + 1] + (b[k + 1] - a[k + 1]) * w, r = Math.exp(-Math.PI * bw[k] / FS), y = src * (1 - r) + 2 * r * Math.cos(TAU * F / FS) * y1[k] - r * r * y2[k];
      y2[k] = y1[k]; y1[k] = y; out += y / (k + 1);
    }
    x[i] = out * Math.min(1, t / 0.08, (3.6 - t) / 0.15);
  }
  toPeak(x, 0.9);
  return { L: x, R: x.slice() };
}
function modeRing(buf, n0, f, t60, a) {
  var w = TAU * f / FS, R = Math.pow(10, -3 / (t60 * FS)), m = Math.min(buf.length - n0, Math.ceil(t60 * 1.3 * FS)), env = a, i;
  for (i = 0; i < m; i++) { buf[n0 + i] += env * Math.sin(w * i); env *= R; }
}
function makeKnock() {
  /* a knuckle on a metal pot: seven modes with known frequencies and decays (the tests measure them back) */
  var rnd = rng(81), n = Math.round(2.8 * FS), x = new Float32Array(n), n0 = Math.round(0.15 * FS), i;
  var F = [311, 742, 1297, 1938, 2716, 3528, 4405], T = [1.6, 1.1, 0.8, 0.55, 0.4, 0.3, 0.22], A = [1, 0.7, 0.55, 0.4, 0.3, 0.2, 0.15];
  for (i = 0; i < F.length; i++) modeRing(x, n0, F[i], T[i], A[i]);
  noiseBurst(x, n0 / FS, 0.0015, 1500, 9000, 0.6, rnd, 0.0002);
  var nz = shapedNoise(n, rnd, 8000, 50); toPeak(nz, 0.0004);
  for (i = 0; i < n; i++) x[i] += nz[i];
  toPeak(x, 0.9);
  return { L: x, R: x.slice() };
}
function makeDoor() {
  /* knuckles on a wooden door, three and four at a time, then the door slams: a body thump and the latch */
  var rnd = rng(82), n = Math.round(4.2 * FS), x = new Float32Array(n), i;
  [[0.25, 0.7], [0.5, 0.55], [0.75, 0.62], [1.45, 0.8], [1.68, 0.62], [1.9, 0.72], [2.12, 0.58]].forEach(function (h) {
    addAt(x, modalHit('wood', h[1] * h[1] * 0.02, 1.6 + 0.2 * rnd(), rnd, { t60Scale: 0.8, noGrains: true }), h[0]);
  });
  addAt(x, modalHit('wood', 0.06, 0.5, rnd, { t60Scale: 2.2 }), 3.1);
  addAt(x, modalHit('steel', 0.004, 4.5, rnd, { maxModes: 4, t60Scale: 0.06, noGrains: true }), 3.104);
  var nz = shapedNoise(n, rnd, 6000, 60); toPeak(nz, 0.0008 * peakOf(x));
  for (i = 0; i < n; i++) x[i] += nz[i];
  toPeak(x, 0.9);
  return { L: x, R: x.slice() };
}
function makeGravel() {
  /* stones landing on stones: short bright clacks, some with a second bounce, spread across the stereo field */
  var rnd = rng(83), n = 6 * FS, L = new Float32Array(n), R = new Float32Array(n), i;
  for (i = 0; i < 70; i++) {
    var t = 0.1 + 5.7 * rnd(), sc = 1.1 + 3.2 * rnd(), E = 0.0004 * Math.pow(rnd(), 2) + 0.00002, pan = rnd() * 2 - 1, k;
    var gl = Math.cos((pan + 1) * Math.PI / 4), gr = Math.sin((pan + 1) * Math.PI / 4);
    for (k = 0; k < (rnd() < 0.4 ? 2 : 1); k++) {
      var b = modalHit('concrete', E * (k ? 0.25 : 1), sc, rnd, { maxModes: 3, t60Scale: 0.7, noGrains: true }), dt = k ? 0.03 + 0.06 * rnd() : 0;
      addAt(L, b, t + dt, gl); addAt(R, b, t + dt, gr);
    }
  }
  var pk = peakOf(L, R) || 1; scale(L, 0.9 / pk); scale(R, 0.9 / pk);
  return { L: L, R: R };
}
function makeClap() {
  /* a hand clap in a concrete stairwell: a 1 ms burst, then the stairwell's dense, bright reverb (about 2.4 s) */
  var rnd = rng(84), n = Math.round(3.2 * FS), x = new Float32Array(n), i;
  noiseBurst(x, 0.1, 0.0012, 600, 7000, 1, rnd, 0.0002);
  var wet = fdn(x, x, { delays: [11, 17, 23, 29, 37, 43, 53, 61], rt60: 2.4, damp: 7000 }), L = new Float32Array(n), R = new Float32Array(n);
  for (i = 0; i < n; i++) { L[i] = x[i] + 0.6 * wet.L[i]; R[i] = x[i] + 0.6 * wet.R[i]; }
  var pk = peakOf(L, R) || 1; scale(L, 0.9 / pk); scale(R, 0.9 / pk);
  return { L: L, R: R };
}
var EXAMPLES = {
  'ex:engine': { name: 'Example: engine (synthetic)', make: makeEngine },
  'ex:rain': { name: 'Example: rain (synthetic)', make: makeRain },
  'ex:voice': { name: 'Example: sung vowels (synthetic)', make: makeVoice },
  'ex:door': { name: 'Example: knocks and a door slam (synthetic)', make: makeDoor },
  'ex:knock': { name: 'Example: knock on a metal pot (synthetic)', make: makeKnock },
  'ex:gravel': { name: 'Example: gravel and stones (synthetic)', make: makeGravel },
  'ex:stair': { name: 'Example: clap in a stairwell (synthetic)', make: makeClap }
};

/* ---------- the Recording source: placed or flying past, optionally driving a body ---------- */
var REC_BODIES = ['steel', 'aluminium', 'glass', 'ice', 'wood', 'rail', 'line', 'spring', 'ir'];
/* the body as an impulse response, peak 1: plates and rails ring with bending waves, the line and the spring sweep */
function recBodyIR(p, rnd) {
  var b = p.rcBody, buf, k;
  if (PLATES[b]) return { m: bendIR(planPlate(b, p.rcThick / 1000, p.rcSize), b === 'wood' ? 3000 : 7000, rnd) };
  if (b === 'rail') return { m: bendIR(planRail(p.rcLength), 8000, rnd) };
  if (b === 'line') {
    var q = { bpLength: p.rcLength, bpStiff: 0.6, bpTension: 0, bpHard: 6000, bpDamp: 0.3, bpEchoes: 3, bpRefl: 0.6 }, pl = planBlaster(q);
    buf = new Float32Array(Math.ceil((pl.tEnd + 0.06) * FS) + 64);
    pl.echoes.forEach(function (e) { chirpInto(buf, pl, q, e.m, e.g); });
    toPeak(buf, 1);
    return { m: buf };
  }
  if (b === 'spring') {
    /* the last pass is 15 lengths long; at 60 Hz it arrives after 15 L / (2 sqrt(2 pi kappa 60)) */
    buf = new Float32Array(Math.ceil((15 * p.rcLength / (2 * Math.sqrt(TAU * 0.15 * 60)) + 0.05) * FS) + 64);
    for (k = 0; k < 8; k++) bendChirp(buf, 0, p.rcLength * (2 * k + 1), 0.15, Math.pow(0.8, k), 9000, 60, 0.01, 5000, rnd());
    toPeak(buf, 1);
    return { m: buf };
  }
  if (b === 'ir') { var a = getIR(p.rcIr); return a ? { L: a.L, R: a.R } : null; }
  return null;
}
/* the plan stays light (the body's impulse response is built at render time): what the diagram and readouts need */
function planRecording(q) {
  var a = getAsset(q.rcAsset), fly = q.rcMode === 'flyby', hs = q.rcHeight, hl = 1.7, b = q.rcBody, k, t0;
  var out = { src: a, name: a ? a.name : '', len: a ? a.L.length / FS : 0, fly: fly, body: b, curves: [] };
  if (b === 'ir') { var ia = getAsset(q.rcIr), ii = getIR(q.rcIr); out.irName = ia ? ia.name : ''; out.irLen = ii ? ii.L.length / FS : 0; }
  if (fly) {
    out.v = Math.max(q.rcSpeed, 0.5); out.dur = q.rcPass; out.missD = Math.hypot(q.miss, hs - hl); out.missR = Math.hypot(q.miss, hs + hl);
    var xf = function (t) { return q.D + out.v * (t - out.dur / 2); };
    out.trD = trajKin(out.dur, q.D, out.missD, xf); out.trR = trajKin(out.dur, q.D, out.missR, xf);
    out.semis = 12 * Math.log2((C + out.v) / (C - Math.min(out.v, C * 0.95)));
    var dp = out.missR - out.missD; out.notch = dp > 1e-6 ? C / (2 * dp) : 0;
  } else {
    out.r = Math.max(0.3, q.rcDist);
    /* placed: the ground bounce of postLayer (source 1.5 m, ear 1.7 m) */
    out.notch = C / (2 * (Math.hypot(out.r, 3.2) - Math.hypot(out.r, 0.2)));
  }
  /* sweep curves of a dispersive body, from the start of the recording */
  t0 = fly ? 0 : out.r / C;
  if (PLATES[b]) {
    var pp = planPlate(b, q.rcThick / 1000, q.rcSize); out.kap = pp.kap; out.cb1k = pp.cb1k; out.f11 = pp.f11;
    pp.paths.slice().sort(function (u, v) { return u.d - v.d; }).slice(0, 8).forEach(function (q2, j) { out.curves.push({ pts: sweepCurve(t0, q2.d, pp.kap, 16000, pp.fLo), w: Math.max(0.3, 1 - j * 0.1), c: j ? 'shock' : 'tracer' }); });
  } else if (b === 'rail') {
    var rp = planRail(q.rcLength); out.f1 = rp.f1;
    rp.paths.slice().sort(function (u, v) { return u.d - v.d; }).slice(0, 6).forEach(function (q2, j) { out.curves.push({ pts: sweepCurve(t0, q2.d, rp.kap, 16000, 30), w: Math.max(0.3, 1 - j * 0.12), c: j ? 'shock' : 'ink' }); });
  } else if (b === 'line') {
    var bp = planBlaster({ bpLength: q.rcLength, bpStiff: 0.6, bpTension: 0, bpEchoes: 3, bpRefl: 0.6 }); out.tSweep = bp.tSweep;
    bp.echoes.forEach(function (e, j) { var pts = []; for (k = 0; k < bp.K; k += 2) pts.push([t0 + e.m * bp.tau[k], bp.f[k]]); out.curves.push({ pts: pts, w: j ? Math.max(0.3, e.g) : 1, c: j ? 'shock' : 'tracer' }); });
  } else if (b === 'spring') {
    for (k = 0; k < 8; k++) out.curves.push({ pts: sweepCurve(t0, q.rcLength * (2 * k + 1), 0.15, 9000, 60), w: Math.max(0.3, Math.pow(0.8, k)), c: k ? 'shock' : 'tracer' });
  }
  return out;
}
/* a signal at least n long: looped, with a short crossfade at each seam */
function loopTo(x, n) {
  if (x.length >= n) return x.subarray(0, n);
  var y = new Float32Array(n), xf = Math.min(1440, x.length >> 2), step = x.length - xf, o = 0, i;
  while (o < n) {
    for (i = 0; i < x.length && o + i < n; i++) {
      var w = o > 0 && i < xf ? i / xf : 1;
      y[o + i] = y[o + i] * (1 - w) + x[i] * w;
    }
    o += step;
  }
  return y;
}
function rms(L, R) { var e = 0, i; for (i = 0; i < L.length; i++) e += L[i] * L[i] + R[i] * R[i]; return Math.sqrt(e / (2 * L.length || 1)); }
function recordingLayers(pl, p, o, rnd, layers, ev, lab) {
  if (!pl.src) return;
  var dry = { L: pl.src.L, R: pl.src.R }, body = null, i, ir = p.rcBody !== 'none' ? recBodyIR(p, rnd) : null;
  if (ir) {
    body = ir.m ? fftConvolve(dry.L, dry.R, ir.m, null) : fftConvolve(dry.L, dry.R, ir.L, ir.R);
    /* a recording has no known level: the body is set to the loudness of the recording */
    var s = rms(dry.L, dry.R) / (rms(body.L, body.R) || 1);
    scale(body.L, s); scale(body.R, s);
  }
  if (pl.fly) {
    /* a moving point source: the recording as mono, retimed for every position, with the ground bounce as a second path */
    var ns = Math.floor((pl.trD.n - 1) / TRAJ_HZ * FS);
    function fly(sig, g) {
      var mono = new Float32Array(sig.L.length);
      for (i = 0; i < mono.length; i++) mono[i] = (sig.L[i] + sig.R[i]) * 0.5;
      mono = loopTo(mono, ns);
      var d = movingSource(pl.trD, p.D, pl.missD, function (k) { return mono[k]; }, null);
      if (d) layers.push({ L: d.L, R: d.R, t: o.t0 + d.t, g: g });
      if (p.ground > 0) {
        var refl = Float32Array.from(mono); onePoleLP(refl, 5000);
        var r = movingSource(pl.trR, p.D, pl.missR, function (k) { return refl[k] * p.ground; }, null);
        if (r) layers.push({ L: r.L, R: r.R, t: o.t0 + r.t, g: g });
      }
    }
    fly(dry, o.g1);
    if (body) fly(body, o.g2);
    ev.push({ k: 'pass', t: o.t0 + pl.dur / 2 + pl.missD / C, label: lab ? 'pass' : '' });
    return;
  }
  function place(sig, g) {
    var L = Float32Array.from(sig.L), R = Float32Array.from(sig.R);
    scale(L, 1 / pl.r); scale(R, 1 / pl.r); postLayer(L, pl.r, p.ground); postLayer(R, pl.r, p.ground);
    layers.push({ L: L, R: R, t: o.t0 + pl.r / C, g: g });
  }
  place(dry, o.g1);
  if (body) place(body, o.g2);
  ev.push({ k: 'launch', t: o.t0 + pl.r / C, label: lab ? 'start' : '' });
}

/* ---------- your sounds, read for other jobs ----------
   Every loaded or recorded sound is one asset. The engine reads it as a job needs: as an impulse response, as hits to
   trigger events from, as the modes of a knocked object, as grains for debris, or as a reference to compare with.
   Each reading is cached by asset id; an id is never reused for other content. */
var READ = {};
function readAsset(kind, id, extra, fn) {
  var key = kind + '|' + id + '|' + (extra == null ? '' : extra);
  if (!(key in READ)) { var a = getAsset(id); READ[key] = a ? fn(a) : null; }
  return READ[key];
}
function getIR(id) { return readAsset('ir', id, null, function (a) { return prepareIR(a.L, a.R); }); }
function monoOf(a) {
  var n = a.L.length, m = new Float32Array(n), i;
  for (i = 0; i < n; i++) m[i] = 0.5 * (a.L[i] + a.R[i]);
  return m;
}

/* Hits: a rise of the short-term level (2.5 ms frames) by more than a threshold within 20 ms, above a floor below
   the loudest frame. Sensitivity lowers both. Strength is each hit's peak against the strongest hit. */
function detectHits(x, sens) {
  var hop = 120, nf = Math.floor(x.length / hop), db = new Float32Array(nf), i, j, top = -240, out = [];
  sens = clamp(sens == null ? 0.5 : sens, 0, 1);
  for (i = 0; i < nf; i++) {
    var e = 0;
    for (j = 0; j < hop; j++) { var v = x[i * hop + j]; e += v * v; }
    db[i] = 10 * Math.log10(e / hop + 1e-14);
    if (db[i] > top) top = db[i];
  }
  var rise = 18 - 12 * sens, floor = top - (24 + 24 * sens), gap = Math.round(0.07 * FS / hop), last = -1e9;
  for (i = 1; i < nf; i++) {
    if (db[i] < floor || i - last < gap) continue;
    var lo = Infinity;
    for (j = Math.max(0, i - 8); j < i; j++) if (db[j] < lo) lo = db[j];
    if (db[i] - lo < rise) continue;
    var s0 = (i - 1) * hop, s1 = Math.min(x.length, s0 + Math.round(0.03 * FS)), lp = 0, k;
    for (k = s0; k < s1; k++) if (Math.abs(x[k]) > lp) lp = Math.abs(x[k]);
    for (k = s0; k < s1 && Math.abs(x[k]) < 0.3 * lp; k++);
    out.push({ t: Math.max(0, k - Math.round(0.0005 * FS)) / FS, a: lp });
    last = i;
  }
  var amax = 0;
  out.forEach(function (h) { if (h.a > amax) amax = h.a; });
  return out.map(function (h) { return { t: h.t, s: h.a / (amax || 1) }; });
}
function getHits(id, sens) { return readAsset('hits', id, (+sens).toFixed(2), function (a) { return detectHits(monoOf(a), sens); }); }

/* A trigger strength sets the size of the event where the source has one (energy follows the square of the hit's
   strength, scaled by Hit strength sets size); elsewhere it sets the level. */
var STRENGTH = {
  explosion: { keys: [['exW', 1]] }, implosion: { keys: [['imR0', 1 / 3]] }, destruction: { keys: [['dsMass', 1]] },
  discharge: { keys: [['dcEnergy', 1]] }, blaster: { keys: [['tgEnergy', 1], ['lnEnergy', 1], ['bvChannel', 1], ['bpEnergy', 1]] },
  field: { keys: [['ffHitE', 1]], gain: true }
};
var MAX_TRIGGERS = 32;

/* Modes of a knocked object. The spectrum of the ring (from 4 ms after the knock, as long as it rings) gives the mode
   frequencies; each mode's level is then tracked frame by frame at its own frequency. A windowed DFT of a decaying
   sinusoid decays at exactly the sinusoid's rate, so the slope of that track is the mode's decay, unbiased by the
   window. The track's start, extrapolated to the knock, gives the mode's level. */
function measureModes(x) {
  var N = x.length, pk = 0, i, j, k;
  for (i = 0; i < N; i++) if (Math.abs(x[i]) > pk) pk = Math.abs(x[i]);
  if (!pk) return null;
  var i0 = 0;
  while (i0 < N && Math.abs(x[i0]) < 0.1 * pk) i0++;
  var a0 = Math.min(N - 1, i0 + Math.round(0.004 * FS)), ehop = 240, env = [], emax = 0;
  for (i = a0; i + ehop <= N; i += ehop) {
    var e = 0;
    for (k = 0; k < ehop; k++) e += x[i + k] * x[i + k];
    env.push(e); if (e > emax) emax = e;
  }
  var ne = env.length;
  while (ne > 1 && env[ne - 1] < emax * 1e-5) ne--;
  var NF = 65536, Nw = clamp(ne * ehop, Math.round(0.08 * FS), NF) | 0, re = new Float64Array(NF), im = new Float64Array(NF);
  for (i = 0; i < Nw && a0 + i < N; i++) re[i] = x[a0 + i] * (0.5 - 0.5 * Math.cos(TAU * (i + 0.5) / Nw));
  fft(re, im);
  var half = NF >> 1, mag = new Float64Array(half), mmax = -Infinity;
  for (k = 0; k < half; k++) { mag[k] = 10 * Math.log10(re[k] * re[k] + im[k] * im[k] + 1e-24); if (mag[k] > mmax) mmax = mag[k]; }
  var df = FS / NF, lobe = Math.max(2, Math.round(2 * NF / Nw)), cands = [];
  for (k = Math.max(lobe + 1, Math.ceil(40 / df)); k < Math.min(half - lobe - 1, 16000 / df); k++) {
    if (mag[k] < mmax - 75) continue;
    var isMax = true;
    for (j = 1; j <= lobe && isMax; j++) if (mag[k - j] > mag[k] || mag[k + j] >= mag[k]) isMax = false;
    if (!isMax) continue;
    var w = Math.max(2 * lobe, Math.round(0.06 * k)), mL = Infinity, mR = Infinity;
    for (j = 1; j <= w && k - j >= 0; j++) if (mag[k - j] < mL) mL = mag[k - j];
    for (j = 1; j <= w && k + j < half; j++) if (mag[k + j] < mR) mR = mag[k + j];
    if (mag[k] - Math.max(mL, mR) < 6) continue;
    /* and well above the spectrum around it (its median over +-10 %), so that noise does not pass as a mode */
    var span = Math.max(8 * lobe, Math.round(0.1 * k)), around = [];
    for (j = Math.max(1, k - span); j < Math.min(half, k + span); j += Math.max(1, span >> 6)) around.push(mag[j]);
    around.sort(function (u, v) { return u - v; });
    if (mag[k] - around[around.length >> 1] < 15) continue;
    var y1 = mag[k - 1], y2 = mag[k], y3 = mag[k + 1], dn = y1 - 2 * y2 + y3, dl = dn ? 0.5 * (y1 - y3) / dn : 0;
    cands.push({ f: (k + clamp(dl, -0.5, 0.5)) * df, db: y2 });
  }
  cands.sort(function (a, b) { return b.db - a.db; });
  var modes = [];
  cands.forEach(function (c) {
    if (modes.length < 16 && modes.every(function (m) { return Math.abs(m.f - c.f) > 0.025 * Math.min(m.f, c.f) + 3 * df; })) modes.push({ f: c.f });
  });
  if (!modes.length) return null;
  /* decay and level of each mode from its track */
  var W = 2048, win = new Float32Array(W), wsum = 0, hp = clamp(Math.round(ne * ehop / 200), 120, 1200);
  for (i = 0; i < W; i++) { win[i] = 0.5 - 0.5 * Math.cos(TAU * (i + 0.5) / W); wsum += win[i]; }
  var nfr = Math.max(1, Math.floor((Math.min(N, a0 + ne * ehop + FS) - a0 - W) / hp));
  modes.forEach(function (m) {
    var w0 = TAU * m.f / FS, cs = new Float32Array(W), sn = new Float32Array(W), tr = new Float64Array(nfr), f, top = -Infinity, ft = 0;
    for (i = 0; i < W; i++) { cs[i] = Math.cos(w0 * i) * win[i]; sn[i] = Math.sin(w0 * i) * win[i]; }
    for (f = 0; f < nfr; f++) {
      var s0 = a0 + f * hp, ar = 0, ai = 0;
      for (i = 0; i < W && s0 + i < N; i++) { var v = x[s0 + i]; ar += v * cs[i]; ai += v * sn[i]; }
      tr[f] = 10 * Math.log10(ar * ar + ai * ai + 1e-24);
      if (tr[f] > top) { top = tr[f]; ft = f; }
    }
    var tail = Array.prototype.slice.call(tr, Math.floor(nfr * 0.8)).sort(function (a, b) { return a - b; });
    var noise = tail.length ? tail[tail.length >> 1] : -240, stop = Math.max(top - 45, noise + 10), f1 = ft;
    while (f1 + 1 < nfr && tr[f1 + 1] > stop) f1++;
    var n = f1 - ft + 1, sx = 0, sy = 0, sxx = 0, sxy = 0, slope, icpt;
    for (f = ft; f <= f1; f++) { var t = (f * hp + W / 2) / FS; sx += t; sy += tr[f]; sxx += t * t; sxy += t * tr[f]; }
    if (n >= 3) { slope = (n * sxy - sx * sy) / (n * sxx - sx * sx); icpt = (sy - slope * sx) / n; }
    else { slope = n === 2 ? (tr[f1] - tr[ft]) / ((f1 - ft) * hp / FS) : -60 / (0.5 * W / FS); icpt = top - slope * (ft * hp + W / 2) / FS; }
    m.t60 = slope < 0 ? clamp(-60 / slope, 0.005, 20) : 20;
    m.a = 2 * Math.pow(10, icpt / 20) / wsum;
  });
  var amax = 0;
  modes.forEach(function (m) { if (m.a > amax) amax = m.a; });
  modes = modes.filter(function (m) { m.a /= amax || 1; return m.a > 0.01; }).sort(function (a, b) { return a.f - b.f; }).slice(0, 12);
  var ring = 0;
  modes.forEach(function (m) { if (m.t60 > ring) ring = m.t60; });
  return { modes: modes, f1: modes[0].f, ring: ring };
}
function getModes(id) { return readAsset('modes', id, null, function (a) { return measureModes(monoOf(a)); }); }
/* A measured object as a material for modalHit. The knock is of the whole object (mass M): a piece of mass m rings
   (M / m)^(1/3) higher, as geometrically similar bodies do, and shorter, as a constant loss factor makes it. */
function measuredMaterial(mm, M) {
  return { f0: mm.f1 * Math.cbrt(M / 0.2), f1: mm.f1, ratios: mm.modes.map(function (m) { return m.f / mm.f1; }),
    t60s: mm.modes.map(function (m) { return m.t60; }), gains: mm.modes.map(function (m) { return m.a; }), t60: mm.ring,
    slope: 0, contact: 0.00006, eff: 0.8, noise: { dur: 0.003, hp: 1500, lp: 15000, gain: 0.3 }, grains: null };
}
function dsMaterial(p) {
  if (p.dsMat !== 'measured') return p.dsMat;
  var mm = getModes(p.dsKnock);
  return mm ? measuredMaterial(mm, p.dsMass) : p.dsLike;
}
function matSpec(mat) { return typeof mat === 'string' ? MATERIALS[mat] : mat; }

/* Grains for debris: the hits of a recording, each cut until the next hit (at most 350 ms), ordered from dark to
   bright. A piece takes a grain by its size (small pieces brighter), re-pitched by its size, at the level its
   landing energy gives. A recording without clear hits is cut into 150 ms slices. */
function cutGrains(a) {
  var x = monoOf(a), hits = detectHits(x, 0.7), g = [], i, j, t;
  if (hits.length < 3) { hits = []; for (t = 0; t + 0.05 < x.length / FS; t += 0.15) hits.push({ t: t, s: 1 }); }
  for (i = 0; i < hits.length; i++) {
    var s0 = Math.round(hits[i].t * FS), s1 = Math.min(x.length, s0 + Math.round(0.35 * FS), i + 1 < hits.length ? Math.round(hits[i + 1].t * FS) - 48 : x.length);
    if (s1 - s0 < 0.012 * FS) continue;
    var b = x.slice(s0, s1), pk = peakOf(b);
    if (!pk) continue;
    var fo = Math.min(b.length >> 1, Math.round(0.006 * FS));
    for (j = 0; j < fo; j++) b[b.length - 1 - j] *= j / fo;
    scale(b, 1 / pk);
    var zc = 0, m = Math.min(b.length, Math.round(0.04 * FS));
    for (j = 1; j < m; j++) if ((b[j] >= 0) !== (b[j - 1] >= 0)) zc++;
    g.push({ b: b, c: zc * FS / (2 * m), s: hits[i].s });
  }
  g.sort(function (u, v) { return v.s - u.s; });
  g = g.slice(0, 64).sort(function (u, v) { return u.c - v.c; });
  return g.length ? { grains: g } : null;
}
function getGrains(id) { return readAsset('grains', id, null, cutGrains); }
function grainHit(bank, E, sc, scRef, rnd) {
  var n = bank.grains.length, u = clamp(0.5 + 0.3 * Math.log2(sc / scRef) + 0.3 * (rnd() - 0.5), 0, 1), gr = bank.grains[Math.round(u * (n - 1))];
  var pr = clamp(Math.pow(sc / scRef, 0.35), 0.6, 1.7) * (0.94 + 0.12 * rnd()), len = Math.max(1, Math.floor((gr.b.length - 1) / pr));
  var out = new Float32Array(len + 64), amp = 3.4 * Math.sqrt(Math.max(E, 1e-6)), i;
  for (i = 0; i < len; i++) { var q = i * pr, j = q | 0, f = q - j; out[i] = amp * (gr.b[j] + (gr.b[j + 1] - gr.b[j]) * f); }
  return out;
}

/* ---------- comparing with a reference ----------
   A few measures of a sound that physics sets and that ears notice: the balance across octave bands, the brightness
   (spectral centroid), how long it decays (from the energy decay curve after the loudest moment) and how fast it
   rises. Levels are left out: a recording's level is not known. */
var BAND_HZ = [31.25, 62.5, 125, 250, 500, 1000, 2000, 4000, 8000, 16000];
function features(L, R) {
  var N = L.length, x = new Float32Array(N), i, k;
  for (i = 0; i < N; i++) x[i] = 0.5 * (L[i] + (R || L)[i]);
  var hop = 480, nf = Math.max(1, Math.floor(N / hop)), env = new Float64Array(nf), emax = 0, fmax = 0, fr = hop / FS;
  for (k = 0; k < nf; k++) {
    var e = 0;
    for (i = k * hop; i < (k + 1) * hop && i < N; i++) e += x[i] * x[i];
    env[k] = e; if (e > emax) { emax = e; fmax = k; }
  }
  var a = 0, b = nf - 1, thr = emax * 1e-4;
  while (a < nf - 1 && env[a] < thr) a++;
  while (b > a && env[b] < thr) b--;
  var edc = new Float64Array(nf + 1), t5 = -1, t15 = -1, t25 = -1;
  for (k = nf - 1; k >= 0; k--) edc[k] = edc[k + 1] + env[k];
  for (k = fmax; k < nf; k++) {
    var d = 10 * Math.log10(edc[k] / (edc[fmax] || 1) + 1e-30);
    if (t5 < 0 && d <= -5) t5 = k;
    if (t15 < 0 && d <= -15) t15 = k;
    if (d <= -25) { t25 = k; break; }
  }
  if (t5 < 0) t5 = fmax;
  var decay = Math.max(fr, t25 > 0 ? 3 * (t25 - t5) * fr : t15 > 0 ? 6 * (t15 - t5) * fr : 2 * (b - fmax + 1) * fr);
  /* rise of the loudest event: 10 % to 90 % of a peak envelope with a 5 ms release, at sample resolution */
  var pe = 0, rel = Math.exp(-1 / (0.005 * FS)), emx = 0, ipk = 0, en = new Float32Array(N), i10, i90;
  for (i = 0; i < N; i++) { var ax = Math.abs(x[i]); pe = ax > pe ? ax : pe * rel; en[i] = pe; if (pe > emx) { emx = pe; ipk = i; } }
  i10 = ipk;
  while (i10 > 0 && en[i10 - 1] >= 0.1 * emx) i10--;
  i90 = i10;
  while (i90 < ipk && en[i90] < 0.9 * emx) i90++;
  /* averaged spectrum of the active part */
  var W = 4096, S = new Float64Array(W / 2), re = new Float64Array(W), im = new Float64Array(W), win = new Float64Array(W);
  for (i = 0; i < W; i++) win[i] = 0.5 - 0.5 * Math.cos(TAU * (i + 0.5) / W);
  var s0 = a * hop, s1 = Math.min(N, (b + 1) * hop), segs = Math.max(1, Math.floor((s1 - s0 - W) / (W / 2)) + 1), step = segs > 120 ? (segs - 1) / 119 : 1, cnt = Math.min(segs, 120);
  for (k = 0; k < cnt; k++) {
    var st = s0 + Math.round(k * step) * (W / 2);
    re.fill(0); im.fill(0);
    for (i = 0; i < W && st + i < N; i++) re[i] = x[st + i] * win[i];
    fft(re, im);
    for (i = 1; i < W / 2; i++) S[i] += re[i] * re[i] + im[i] * im[i];
  }
  var tot = 0, cs = 0, bands = BAND_HZ.map(function () { return 0; });
  for (i = 1; i < W / 2; i++) {
    var f = i * FS / W;
    if (f < 20 || f > 20000) continue;
    tot += S[i]; cs += S[i] * f;
    for (k = 0; k < BAND_HZ.length; k++) if (f >= BAND_HZ[k] / Math.SQRT2 && f < BAND_HZ[k] * Math.SQRT2) { bands[k] += S[i]; break; }
  }
  return { bands: bands.map(function (v) { return 10 * Math.log10(v / (tot || 1) + 1e-12); }), cent: tot ? cs / tot : 1000,
    decay: decay, attack: (i90 - i10) / FS, len: (b - a + 1) * fr };
}
/* how far apart two sounds are, in rough dB-like units: 0 is a match */
function distance(f, r) {
  var s = 0, n = 0, k;
  for (k = 0; k < f.bands.length; k++) {
    if (f.bands[k] < -45 && r.bands[k] < -45) continue;
    s += Math.min(30, Math.abs(Math.max(f.bands[k], -60) - Math.max(r.bands[k], -60))); n++;
  }
  return (n ? s / n : 0) + 10 * Math.abs(Math.log2(f.decay / r.decay)) + 8 * Math.abs(Math.log2(f.cent / r.cent)) +
    3 * Math.abs(Math.log2((f.attack + 0.003) / (r.attack + 0.003)));
}
function matchScore(d) { return Math.round(100 * Math.exp(-d / 15)); }
/* slider position (0..1) to value, as the page's sliders map it */
function posToVal(s, u) {
  var v = s.scale === 'log' ? s.min * Math.pow(s.max / s.min, u) : s.scale === 'pow' ? s.max * u * u * u : s.min + u * (s.max - s.min);
  return s.round ? Math.round(v / s.round) * s.round : v;
}
/* Fit one parameter to the reference: a coarse sweep over the slider, then a golden-section search around the best.
   Every try renders the Physics version from the same seed. */
var FIT_TRIES = 24;
function fitParam(d, post) {
  var ref = getAsset(d.ref);
  if (!ref) return { id: d.id, kind: 'fit', error: 'no reference' };
  var rf = features(ref.L, ref.R), tried = [], best = null, G = 16, i;
  function ev(u) {
    u = clamp(u, 0, 1);
    var q = merge(d.p, {}), v = posToVal(d.spec, u), r, dd;
    q[d.key] = v; r = renderRaw(q, d.seed); dd = distance(features(r.L, r.R), rf);
    tried.push([u, dd]);
    if (!best || dd < best.d) best = { u: u, v: v, d: dd };
    if (post) post({ kind: 'fitProgress', id: d.id, n: tried.length, of: FIT_TRIES });
    return dd;
  }
  var r0 = renderRaw(d.p, d.seed), before = distance(features(r0.L, r0.R), rf), gd = [];
  for (i = 0; i <= G; i++) gd.push(ev(i / G));
  var bi = 0;
  for (i = 1; i <= G; i++) if (gd[i] < gd[bi]) bi = i;
  var lo = Math.max(0, (bi - 1) / G), hi = Math.min(1, (bi + 1) / G), gr = (Math.sqrt(5) - 1) / 2;
  var c = hi - gr * (hi - lo), e = lo + gr * (hi - lo), fc = ev(c), fe = ev(e);
  for (i = 0; i < FIT_TRIES - G - 3; i++) {
    if (fc < fe) { hi = e; e = c; fe = fc; c = hi - gr * (hi - lo); fc = ev(c); }
    else { lo = c; c = e; fc = fe; e = lo + gr * (hi - lo); fe = ev(e); }
  }
  if (before <= best.d) best = { u: null, v: d.p[d.key], d: before };
  return { id: d.id, kind: 'fit', key: d.key, value: best.v, dist: best.d, before: before, tried: tried.sort(function (a, b) { return a[0] - b[0]; }) };
}

/* ---------- impulse responses to save ---------- */
function bodyIR(p, seed) {
  var ir = recBodyIR(p, rng(seed || 1));
  if (!ir) return null;
  var L = ir.m || ir.L, R = ir.m || ir.R, out = prepareIR(Float32Array.from(L), Float32Array.from(R));
  return out;
}
/* the room alone: an impulse through the environment's reverb, without the direct sound */
function roomIR(p) {
  var env = ENVS[p.env] || ENVS.none;
  if (!env.rt60) return null;
  var n = Math.ceil((env.rt60 * 1.5 + 0.5) * FS) + Math.round(((env.taps || []).reduce(function (m, t) { return Math.max(m, t.ms); }, 0)) * FS / 1000);
  var imp = new Float32Array(n); imp[0] = 1;
  var wet = fdn(imp, imp, env);
  return prepareIR(wet.L, wet.R);
}

/* ---------- seamless loops: hover, static burn, field hum ---------- */
function isLoop(p) { return (p.kind === 'rocket' && p.rkMode === 'static') || (p.kind === 'rotor' && p.rtMode === 'hover') || (p.kind === 'field' && p.ffMode === 'hum'); }
/* The four layer groups (the Layer levels sliders). For a stem, every other group that is on gets a vanishing gain
   instead of zero: the code then takes exactly the same branches and random draws as the full mix, so the stems add
   up to the mix sample for sample. Every gain enters the mix linearly, which is what makes this hold. */
var STEM_EPS = 1e-20;
function triggered(p) { return p.seqFrom === 'rec' && !isLoop(p); }
function sceneGains(p, only) {
  var g = [trimGain(p.trimCrack), trimGain(p.trimLaunch), trimGain(p.trimWake), trimGain(p.trimImpact), triggered(p) ? trimGain(p.seqGuide) : 0];
  if (only != null) g = g.map(function (v, k) { return k === only || v === 0 ? v : STEM_EPS; });
  return { g1: g[0], g2: g[1], g3: g[2], g4: g[3], g5: g[4] };
}
function renderLoop(p, seed, only, ext) {
  var pl = planRep(p, seed, 0), rnd = rng(seed + 5), Np = LOOP_S * FS, i, sig, r;
  var o = sceneGains(p, only);
  if (pl.kind === 'rotor') { sig = rotorSignal(pl.rt, p, o, rnd, Np, true); r = pl.rt.r; }
  else if (pl.kind === 'field') { sig = fieldSignal(pl.ff, p, o, rnd, Np, true); r = pl.ff.r; }
  else { sig = rocketStatic(pl, p, o, rnd, Np); r = pl.r; }
  var L = new Float32Array(Np), R = new Float32Array(Np);
  for (i = 0; i < Np; i++) { L[i] = (sig.mid[i] + sig.side[i]) / r; R[i] = (sig.mid[i] - sig.side[i]) / r; }
  L = periodicApply(L, function (b) { postLayer(b, r, p.ground); }); R = periodicApply(R, function (b) { postLayer(b, r, p.ground); });
  var peakPa = peakOf(L, R), env = ENVS[p.env] || ENVS.none, irA = env.ir ? getIR(p.irAsset) : null, tL, tR, wet, wg;
  if (irA) {
    /* an imported room: three periods through it, the last one kept, so the reverb wraps round the seam */
    tL = tile3(L); tR = tile3(R); wet = fftConvolve(tL, tR, irA.L, irA.R); wg = dbToLin(p.irWet);
    for (i = 0; i < Np; i++) { L[i] += wet.L[2 * Np + i] * wg; R[i] += wet.R[2 * Np + i] * wg; }
  } else if (env.rt60) {
    tL = tile3(L); tR = tile3(R); wet = fdn(tL, tR, env); wg = dbToLin(env.wet);
    for (i = 0; i < Np; i++) { L[i] += wet.L[2 * Np + i] * wg; R[i] += wet.R[2 * Np + i] * wg; }
  }
  if (ext) return { L: L, R: R };
  var pk = peakOf(L, R) || 1;
  scale(L, 1 / pk); scale(R, 1 / pk);
  return { L: L, R: R, events: [], tStart: 0, peakPa: peakPa, spl: peakPa > 0 ? 20 * Math.log10(peakPa / 2e-5) : 0, layers: 1, loop: true };
}

/* ---------- scene assembly: one plan per repetition, then a common mix ---------- */
function planRep(p, seed, k, s) {
  var grnd = rng(seed * 31 + k * 7919 + 17), q = p, j = p.seqJitter || 0, pan = 0, kind = p.kind || 'projectile', out, gf = 1;
  if ((k > 0 && j > 0) || s != null) q = merge(p, {});
  if (s != null) {
    /* triggered from a recording: the hit's strength sets the size of the event, or its level */
    var sd = clamp(p.seqDyn, 0, 1), ss = Math.max(s, 0.05), fE = Math.pow(ss, 2 * sd), sk = STRENGTH[kind];
    if (sk) sk.keys.forEach(function (kv) { q[kv[0]] = q[kv[0]] * Math.pow(fE, kv[1]); });
    if (!sk || sk.gain) gf = Math.pow(ss, sd);
  }
  if (k > 0 && j > 0) {
    var a = 1 + j * 0.7 * (grnd() - 0.5);
    if (kind === 'explosion') q.exDist = p.exDist * a; else if (kind === 'destruction') q.dsDist = p.dsDist * a;
    else if (kind === 'implosion') q.imDist = p.imDist * a; else if (kind === 'discharge') q.dcDist = p.dcDist * a;
    else if (kind === 'blaster') { q.miss = p.miss * a; q.bpStiff = p.bpStiff * (1 + j * 0.3 * (grnd() - 0.5)); q.bvSpeed = p.bvSpeed * (1 + j * 0.1 * (grnd() - 0.5)); }
    else if (kind === 'field') q.ffDist = p.ffDist * a; else if (kind === 'recording') { q.miss = p.miss * a; q.rcDist = p.rcDist * a; } else q.miss = p.miss * a;
    if (kind !== 'projectile') pan = j * 1.4 * (grnd() - 0.5);
  }
  if (kind === 'explosion') out = { ex: planExplosion(q.exW, q.exDist, Math.round(q.exFrags), Math.round(q.exDebris), grnd) };
  else if (kind === 'implosion') out = { im: planImplosion(q) };
  else if (kind === 'destruction') out = { ds: planDestruction({ mat: q.dsMat === 'measured' ? q.dsLike : q.dsMat, mass: q.dsMass, height: q.dsHeight, pieces: q.dsPieces, dist: q.dsDist, spread: q.dsSpread }, grnd) };
  else if (kind === 'rocket') out = planRocket(q, grnd);
  else if (kind === 'rotor') out = { rt: planRotor(q, grnd) };
  else if (kind === 'discharge') out = { dc: planDischarge(q, grnd) };
  else if (kind === 'blaster') out = { wp: planWeapon(q, grnd) };
  else if (kind === 'field') out = { ff: planField(q, grnd) };
  else if (kind === 'recording') out = { rc: planRecording(q) };
  else {
    out = analyzeProj(q); out.pay = null;
    if (out.hit && q.payload >= 0.01) out.pay = planExplosion(q.payload, out.hit.r, Math.round(q.exFrags), Math.round(q.exDebris), grnd);
  }
  out.kind = kind; out.q = q; out.pan = pan; out.gf = gf;
  return out;
}
function analyze(p, seed) { return planRep(p, seed || 1, 0); }
function renderRaw(p, seed) {
  if (isLoop(p)) return renderLoop(p, seed);
  var sc = mixScene(p, seed, null), L = sc.L, R = sc.R, ev = sc.ev, tStart = sc.tStart, peakPa = sc.peakPa;
  var pk = peakOf(L, R) || 1;
  scale(L, 1 / pk); scale(R, 1 / pk);
  var tt = trimTail(L, R); L = tt[0]; R = tt[1];
  ev = ev.filter(function (e) { return e.t - tStart < L.length / FS; });
  ev.forEach(function (e) { e.t -= tStart; });
  ev.sort(function (a, b) { return a.t - b.t; });
  return { L: L, R: R, events: ev, tStart: tStart, peakPa: peakPa, spl: peakPa > 0 ? 20 * Math.log10(peakPa / 2e-5) : 0, layers: sc.layers };
}
/* Stems: the four layer groups of the Physics version, scaled and cut like the mix, so they add up to it exactly.
   Silent groups come back as null. */
function renderStems(p, seed) {
  var loop = isLoop(p), full = loop ? renderLoop(p, seed, null, true) : mixScene(p, seed, null), pk = peakOf(full.L, full.R) || 1, n = 0, out = [], k;
  if (!loop) { scale(full.L, 1 / pk); scale(full.R, 1 / pk); n = trimTail(full.L, full.R)[0].length; }
  var gs = sceneGains(p, null), on = [gs.g1, gs.g2, gs.g3, gs.g4, gs.g5];
  for (k = 0; k < 5; k++) {
    if (!on[k]) { out.push(null); continue; }
    var sc = loop ? renderLoop(p, seed, k, true) : mixScene(p, seed, k), L = sc.L, R = sc.R;
    scale(L, 1 / pk); scale(R, 1 / pk);
    if (!loop) { var c = cutFade(L, R, n); L = c[0]; R = c[1]; }
    out.push(peakOf(L, R) > 1e-6 ? { L: L, R: R } : null);
  }
  return out;
}
/* every layer of every repeat, mixed in place and through the room; not yet normalised */
function mixScene(p, seed, only) {
  var layers = [], ev = [], trig = triggered(p) ? (getHits(p.seqAsset, p.seqSens) || []).slice(0, MAX_TRIGGERS) : null;
  var count = trig ? trig.length : clamp(Math.round(p.seqCount || 1), 1, 16), tOff = 0, k, trnd = rng(seed ^ 0x51ed);
  for (k = 0; k < count; k++) {
    if (trig) tOff = trig[k].t;
    var pl = planRep(p, seed, k, trig ? trig[k].s : null), rnd = rng(seed + k * 104729), q = pl.q, lab = k === 0;
    var o = sceneGains(q, only); o.t0 = tOff; o.pan = pl.pan; o.ground = q.ground;
    o.g1 *= pl.gf; o.g2 *= pl.gf; o.g3 *= pl.gf; o.g4 *= pl.gf;
    if (pl.kind === 'explosion') explosionLayers(pl.ex, { W: q.exW, r: q.exDist, surface: q.exSurface, grains: q.exSurface === 'rec' ? getGrains(q.grAsset) : null, t0: tOff, pan: pl.pan, ground: q.ground,
      gBlast: o.g1, gRumble: o.g2, gFrag: o.g3, gDebris: o.g4 }, rnd, layers, ev, lab);
    else if (pl.kind === 'implosion') implosionLayers(pl.im, q, o, rnd, layers, ev, lab);
    else if (pl.kind === 'destruction') destructionLayers(pl.ds, q, o, rnd, layers, ev, lab);
    else if (pl.kind === 'rocket') rocketLayers(pl, q, o, rnd, layers, ev, lab);
    else if (pl.kind === 'rotor') rotorLayers(pl.rt, q, o, rnd, layers, ev, lab);
    else if (pl.kind === 'discharge') dischargeLayers(pl.dc, q, o, rnd, layers, ev, lab);
    else if (pl.kind === 'blaster') weaponLayers(pl.wp, q, o, rnd, layers, ev, lab);
    else if (pl.kind === 'field') fieldLayers(pl.ff, q, o, rnd, layers, ev, lab);
    else if (pl.kind === 'recording') recordingLayers(pl.rc, q, o, rnd, layers, ev, lab);
    else projLayers(pl, q, o, rnd, layers, ev, lab);
    if (!trig) tOff += (p.seqInterval || 0.1) * (1 + (p.seqJitter || 0) * (trnd() - 0.5));
  }
  /* the recording that triggers the events, at its own time, in its own group */
  var gG = sceneGains(p, only).g5, ga = trig && gG > 0 ? getAsset(p.seqAsset) : null;
  if (ga) { layers.push({ L: ga.L, R: ga.R, t: 0, g: gG }); ev.push({ k: 'pass', t: 0, label: 'trigger' }); }
  var tStart = Infinity, tEnd = 0;
  layers.forEach(function (l) { var n = (l.m || l.L).length; if (l.t < tStart) tStart = l.t; if (l.t + n / FS > tEnd) tEnd = l.t + n / FS; });
  if (!layers.length) { tStart = 0; tEnd = 0.2; }
  tStart -= 0.03;
  var env = ENVS[p.env] || ENVS.none, irA = env.ir ? getIR(p.irAsset) : null;
  var durS = Math.min(24, tEnd - tStart + (irA ? irA.L.length / FS + 0.05 : env.rt60 ? env.rt60 * 0.9 + 0.2 : 0.05));
  var N = Math.ceil(durS * FS), L = new Float32Array(N), R = new Float32Array(N);
  layers.forEach(function (l) {
    var s = Math.round((l.t - tStart) * FS), i, n, gl, gr;
    if (l.m) {
      gl = l.g * Math.cos((l.pan + 1) * Math.PI / 4); gr = l.g * Math.sin((l.pan + 1) * Math.PI / 4);
      for (i = 0, n = l.m.length; i < n && s + i < N; i++) { L[s + i] += l.m[i] * gl; R[s + i] += l.m[i] * gr; }
    } else {
      for (i = 0, n = l.L.length; i < n && s + i < N; i++) { L[s + i] += l.L[i] * l.g; R[s + i] += l.R[i] * l.g; }
    }
  });
  var peakPa = peakOf(L, R), wet, wg, i;
  if (irA) {
    wet = fftConvolve(L, R, irA.L, irA.R); wg = dbToLin(p.irWet);
    for (i = 0; i < N; i++) { L[i] += wet.L[i] * wg; R[i] += wet.R[i] * wg; }
  } else if (env.rt60) {
    wet = fdn(L, R, env); wg = dbToLin(env.wet);
    for (i = 0; i < N; i++) { L[i] += wet.L[i] * wg; R[i] += wet.R[i] * wg; }
  }
  return { L: L, R: R, ev: ev, tStart: tStart, peakPa: peakPa, layers: layers.length };
}

/* ---------- action filters ---------- */
function stretch(x, s) {
  var N = Math.floor(x.length * s), y = new Float32Array(N), M = x.length;
  for (var j = 0; j < N; j++) {
    var u = j / s, i = Math.floor(u), f = u - i;
    var a = x[i > 0 ? i - 1 : 0], b = x[i], c = x[i + 1 < M ? i + 1 : M - 1], d = x[i + 2 < M ? i + 2 : M - 1];
    var c1 = 0.5 * (c - a), c2 = a - 2.5 * b + 2 * c - 0.5 * d, c3 = 0.5 * (d - a) + 1.5 * (b - c);
    y[j] = ((c3 * f + c2) * f + c1) * f + b;
  }
  return y;
}
function padTo(x, front, back) { var y = new Float32Array(front + x.length + back); y.set(x, front); return y; }
function findOnsets(L, R) {
  var N = L.length, pk = peakOf(L, R), fast = 0, slow = 0, last = -1e9, out = [];
  var aF = Math.exp(-1 / (0.012 * FS)), aSa = Math.exp(-1 / (0.03 * FS)), aSr = Math.exp(-1 / (0.25 * FS)), win = Math.round(0.02 * FS);
  for (var n = 0; n < N; n++) {
    var x = Math.max(Math.abs(L[n]), Math.abs(R[n]));
    fast = x > fast ? x : x + (fast - x) * aF;
    slow = x > slow ? x + (slow - x) * aSa : x + (slow - x) * aSr;
    if (fast > 0.2 * pk && fast > 2.5 * slow && n - last > 0.14 * FS) {
      var lv = 0; for (var j = n; j < n + win && j < N; j++) lv = Math.max(lv, Math.abs(L[j]), Math.abs(R[j]));
      out.push({ n: n, level: lv }); last = n;
    }
  }
  out.sort(function (a, b) { return b.level - a.level; });
  out = out.slice(0, 5).sort(function (a, b) { return a.n - b.n; });
  return out;
}
function transient(L, R, amt) {
  var f = 0, s = 0, pk = peakOf(L, R), eps = 1e-3 * pk, pw = 0.9 * amt;
  var aFa = Math.exp(-1 / (0.0005 * FS)), aFr = Math.exp(-1 / (0.03 * FS)), aSa = Math.exp(-1 / (0.02 * FS)), aSr = Math.exp(-1 / (0.2 * FS));
  for (var n = 0; n < L.length; n++) {
    var x = Math.max(Math.abs(L[n]), Math.abs(R[n]));
    f = x > f ? x + (f - x) * aFa : x + (f - x) * aFr;
    s = x > s ? x + (s - x) * aSa : x + (s - x) * aSr;
    var g = clamp(Math.pow((f + eps) / (s + eps), pw), 0.6, 4);
    L[n] *= g; R[n] *= g;
  }
}
function trimTail(L, R) {
  var pk = peakOf(L, R), thr = pk * 3e-4, n = L.length - 1;
  while (n > 0 && Math.abs(L[n]) < thr && Math.abs(R[n]) < thr) n--;
  n = Math.min(L.length, n + Math.round(0.08 * FS));
  return cutFade(L, R, n);
}
/* keep the first n samples and fade the last 50 ms out */
function cutFade(L, R, n) {
  var fo = Math.min(n, Math.round(0.05 * FS)), a = L.slice(0, n), b = R.slice(0, n);
  for (var j = 0; j < fo; j++) { a[n - 1 - j] *= j / fo; b[n - 1 - j] *= j / fo; }
  return [a, b];
}
function normalize(L, R, target) { var pk = peakOf(L, R); if (pk > 0) { scale(L, target / pk); scale(R, target / pk); } }
function compress(L, R, amt) {
  var thr = dbToLin(-10 - 14 * amt), ratio = 1 + 5 * amt, env = 0, att = Math.exp(-1 / (0.003 * FS)), rel = Math.exp(-1 / (0.14 * FS)), ex = 1 / ratio - 1;
  for (var n = 0; n < L.length; n++) {
    var x = Math.max(Math.abs(L[n]), Math.abs(R[n]));
    env = x > env ? x + (env - x) * att : x + (env - x) * rel;
    if (env > thr) { var g = Math.pow(env / thr, ex); L[n] *= g; R[n] *= g; }
  }
}
function limiter(L, R, ceil) {
  var N = L.length, h = new Float32Array(N), n, att = 1 - Math.exp(-1 / (0.0015 * FS)), rel = 1 - Math.exp(-1 / (0.08 * FS)), nx = 1, y = 1;
  for (n = N - 1; n >= 0; n--) {
    var x = Math.max(Math.abs(L[n]), Math.abs(R[n])), gr = x > ceil ? ceil / x : 1;
    nx = Math.min(gr, nx + (1 - nx) * att); h[n] = nx;
  }
  for (n = 0; n < N; n++) { y = Math.min(h[n], y + (1 - y) * rel); L[n] *= y; R[n] *= y; }
}
var TAIL = { delays: [61, 89, 127, 173, 229, 283, 349, 419], damp: 2200, pre: 35 };
function actionize(raw, a) {
  var slow = clamp(a.slowmo || 1, 1, 4), L, R, pad = 0, i, n;
  if (!(peakOf(raw.L, raw.R) > 0)) return { L: raw.L.slice(), R: raw.R.slice(), slow: 1, pad: 0, events: [] };
  /* a loop is processed as three periods and the middle one kept, so every stage sees a steady state */
  var loop = !!raw.loop, sL = loop ? tile3(raw.L) : raw.L, sR = loop ? tile3(raw.R) : raw.R;
  if (slow > 1.01) { L = stretch(sL, slow); R = stretch(sR, slow); } else { slow = 1; L = sL.slice(); R = sR.slice(); }
  var maxN = 24 * FS;
  if (!loop && L.length > maxN) { L = L.slice(0, maxN); R = R.slice(0, maxN); }
  if (a.tail > 0 && !loop) { var extra = Math.min(maxN + 4 * FS - L.length, Math.round((1 + a.tail * 3) * FS)); L = padTo(L, 0, extra); R = padTo(R, 0, extra); }
  var N = L.length, on = findOnsets(L, R);
  /* level references come from the kept period of a loop, not from its warm-up */
  function norm(target) {
    var a0 = 0, b0 = L.length, pk = 0, q, v;
    if (loop) { a0 = Math.round(raw.L.length * slow); b0 = 2 * a0; }
    for (q = a0; q < b0; q++) { v = Math.abs(L[q]); if (v > pk) pk = v; v = Math.abs(R[q]); if (v > pk) pk = v; }
    if (pk > 0) { scale(L, target / pk); scale(R, target / pk); }
  }
  if (a.punch > 0) transient(L, R, a.punch);
  if (a.weight > 0) {
    biquad(L, 'ls', 110, 0.7, 8 * a.weight); biquad(R, 'ls', 110, 0.7, 8 * a.weight);
    on.forEach(function (o) {
      var ph = 0, lim = Math.min(N - o.n, Math.round(0.9 * FS));
      for (var j = 0; j < lim; j++) {
        var t = j / FS; ph += TAU * (36 + 80 * Math.exp(-t / 0.05)) / FS;
        var s = Math.sin(ph) * Math.exp(-t / 0.2) * (1 - Math.exp(-t / 0.003)) * o.level * 0.9 * a.weight;
        L[o.n + j] += s; R[o.n + j] += s;
      }
    });
  }
  norm(1);
  if (a.drive > 0) {
    var dg = 1 + 7 * a.drive, bias = 0.12 * a.drive, tb = Math.tanh(bias), tn = Math.tanh(dg);
    for (n = 0; n < N; n++) { L[n] = (Math.tanh(dg * L[n] + bias) - tb) / tn; R[n] = (Math.tanh(dg * R[n] + bias) - tb) / tn; }
  }
  if (a.bite > 0) {
    [L, R].forEach(function (b) { biquad(b, 'pk', 3200, 0.9, 9 * a.bite); biquad(b, 'hs', 8000, 0.7, 4 * a.bite); });
  }
  var sigPk = peakOf(L, R) || 1;
  if (a.tail > 0) {
    var tl = L.slice(), trr = R.slice();
    onePoleHP(tl, 140); onePoleHP(trr, 140); onePoleLP(tl, 6000); onePoleLP(trr, 6000);
    var wet = fdn(tl, trr, { delays: TAIL.delays, damp: TAIL.damp, pre: TAIL.pre, rt60: 1.2 + 4 * a.tail }), wg = 0.55 * a.tail;
    for (n = 0; n < N; n++) { L[n] += wet.L[n] * wg; R[n] += wet.R[n] * wg; }
  }
  if (a.swell > 0 && !loop) {
    var anchor = on.length ? on[0].n : 0;
    if (!on.length) { var pv = 0; for (n = 0; n < N; n++) { var av = Math.abs(L[n]) + Math.abs(R[n]); if (av > pv) { pv = av; anchor = n; } } }
    var Ls = Math.round((0.35 + 0.9 * a.swell) * FS), exN = Math.round(0.3 * FS), xl = new Float32Array(Ls), xr = new Float32Array(Ls);
    for (i = 0; i < exN && i < Ls && anchor + i < N; i++) { var fw = 1 - i / exN; xl[i] = L[anchor + i] * fw; xr[i] = R[anchor + i] * fw; }
    var sw = fdn(xl, xr, { delays: TAIL.delays.map(function (d) { return d * 0.6; }), damp: 3500, pre: 0, rt60: 2.2 });
    onePoleHP(sw.L, 160); onePoleHP(sw.R, 160);
    var sL = new Float32Array(Ls), sR = new Float32Array(Ls);
    for (i = 0; i < Ls; i++) { var e = Math.pow(i / Ls, 2.2); sL[i] = sw.L[Ls - 1 - i] * e; sR[i] = sw.R[Ls - 1 - i] * e; }
    var sp = peakOf(sL, sR) || 1, sg = 0.55 * a.swell * sigPk / sp, start = anchor - Math.round(0.003 * FS) - Ls;
    if (start < 0) { pad = -start; L = padTo(L, pad, 0); R = padTo(R, pad, 0); start = 0; N = L.length; }
    for (i = 0; i < Ls; i++) { L[start + i] += sL[i] * sg; R[start + i] += sR[i] * sg; }
  }
  if (a.width > 0) {
    var wd = 1 + 1.2 * a.width;
    for (n = 0; n < N; n++) { var m = (L[n] + R[n]) * 0.5, sd = (L[n] - R[n]) * 0.5 * wd; L[n] = m + sd; R[n] = m - sd; }
  }
  norm(1);
  if (a.loud > 0) { compress(L, R, a.loud); norm(dbToLin(7 * a.loud)); }
  limiter(L, R, 0.89);
  if (loop) { var Pn = Math.round(raw.L.length * slow); return { L: L.slice(Pn, 2 * Pn), R: R.slice(Pn, 2 * Pn), slow: slow, pad: 0, events: [], loop: true }; }
  var tt = trimTail(L, R); L = tt[0]; R = tt[1];
  return { L: L, R: R, slow: slow, pad: pad / FS,
           events: raw.events.map(function (e) { return { k: e.k, label: e.label, t: e.t * slow + pad / FS }; }) };
}

/* ---------- analysis + export ---------- */
function fft(re, im) {
  var n = re.length, i, j = 0, k, t;
  for (i = 1; i < n; i++) {
    var bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
  }
  for (var len = 2; len <= n; len <<= 1) {
    var ang = -TAU / len, wr = Math.cos(ang), wi = Math.sin(ang);
    for (i = 0; i < n; i += len) {
      var cr = 1, ci = 0;
      for (k = 0; k < len / 2; k++) {
        var ur = re[i + k], ui = im[i + k], vr = re[i + k + len / 2] * cr - im[i + k + len / 2] * ci, vi = re[i + k + len / 2] * ci + im[i + k + len / 2] * cr;
        re[i + k] = ur + vr; im[i + k] = ui + vi; re[i + k + len / 2] = ur - vr; im[i + k + len / 2] = ui - vi;
        t = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = t;
      }
    }
  }
}
/* ---------- saved WAV files and what they carry ----------
   A saved sound says where and when it was made, so that sound libraries and asset managers (Kurator, Soundminer,
   REAPER, Lightroom-style catalogues) can sort it without anyone typing it in again:
     bext  Broadcast WAV: description, originator, origination date and time, time reference
     iXML  project, scene, take, note, tracks, and the recording device in USER
     _PMX  XMP (also written as a .xmp sidecar): keywords as Lightroom (lr:hierarchicalSubject), digiKam (TagsList)
           and Kurator read them, Kurator's groups as roots (Projects|..., Status|..., Source|...); dates; creator,
           source and rights
   meta = { title, note, project, scene, take, tags: ['Nature/Birds'], status, source, creator, rights,
            date: '2026-11-15T17:59:03+01:00' (local time with its offset), user: [[label, value], ...],
            location: { lat, lon, alt, acc } only when the recordist turned it on } */
var ORIGINATOR = 'Ballistic Foley Lab', XMP_ROOT = { project: 'Projects', status: 'Status', source: 'Source' };
function utf8(s) {
  var u = unescape(encodeURIComponent(String(s))), b = new Uint8Array(u.length), i;
  for (i = 0; i < u.length; i++) b[i] = u.charCodeAt(i);
  return b;
}
/* bext is ASCII: accents dropped, anything else becomes '?' */
function asciiOf(s) { return String(s == null ? '' : s).normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^\x20-\x7e]/g, '?'); }
function xmlEsc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function tagPath(t) { return String(t).replace(/\\/g, '/').split('/').map(function (p) { return p.replace(/\s+/g, ' ').trim(); }).filter(Boolean).join('/'); }
/* every keyword as a path: the subjects as given, then the project, status and source under their group's root */
function keywordPaths(meta) {
  var out = [];
  (meta.tags || []).forEach(function (t) { var p = tagPath(t); if (p) out.push(p); });
  ['project', 'status', 'source'].forEach(function (k) { var p = tagPath(meta[k] || ''); if (p) out.push(XMP_ROOT[k] + '/' + p); });
  return out.filter(function (v, i) { return out.indexOf(v) === i; });
}
function dateParts(iso) {
  var m = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(iso || '');
  return m ? { date: m[1], time: m[2] + ':' + m[3] + ':' + m[4], secs: +m[2] * 3600 + +m[3] * 60 + +m[4] } : null;
}
function bextBytes(meta, float, nch) {
  var hist = utf8(asciiOf('A=' + (float ? 'PCM_FLOAT' : 'PCM') + ',F=' + FS + ',W=' + (float ? 32 : 24) + ',M=' + (nch === 1 ? 'mono' : 'stereo') + ',T=' + ORIGINATOR) + '\r\n');
  var b = new Uint8Array(602 + hist.length), dv = new DataView(b.buffer), d = dateParts(meta.date);
  function put(off, len, s) { var a = asciiOf(s), i; for (i = 0; i < a.length && i < len; i++) b[off + i] = a.charCodeAt(i); }
  put(0, 256, meta.title + (meta.note ? '. ' + meta.note : ''));
  put(256, 32, ORIGINATOR);
  put(288, 32, meta.reference || '');
  if (d) {
    put(320, 10, d.date); put(330, 8, d.time);
    var ref = d.secs * FS;
    dv.setUint32(338, ref % 4294967296, true); dv.setUint32(342, Math.floor(ref / 4294967296), true);
  }
  dv.setUint16(346, 1, true);
  b.set(hist, 602);
  return b;
}
function ixmlText(meta, nch) {
  var d = dateParts(meta.date), ref = d ? d.secs * FS : 0, user = (meta.user || []).filter(function (u) { return u[1] != null && u[1] !== ''; });
  function el(tag, v) { return v == null || v === '' ? '' : ' <' + tag + '>' + xmlEsc(v) + '</' + tag + '>\n'; }
  return '<?xml version="1.0" encoding="UTF-8"?>\n<BWFXML>\n' + el('IXML_VERSION', '2.10') + el('PROJECT', meta.project) +
    el('SCENE', meta.scene || meta.title) + el('TAKE', meta.take) + el('NOTE', meta.note) +
    ' <SPEED>\n  <FILE_SAMPLE_RATE>' + FS + '</FILE_SAMPLE_RATE>\n  <TIMESTAMP_SAMPLE_RATE>' + FS + '</TIMESTAMP_SAMPLE_RATE>\n' +
    '  <TIMESTAMP_SAMPLES_SINCE_MIDNIGHT_HI>' + Math.floor(ref / 4294967296) + '</TIMESTAMP_SAMPLES_SINCE_MIDNIGHT_HI>\n' +
    '  <TIMESTAMP_SAMPLES_SINCE_MIDNIGHT_LO>' + ref % 4294967296 + '</TIMESTAMP_SAMPLES_SINCE_MIDNIGHT_LO>\n </SPEED>\n' +
    (nch === 1 ? ' <TRACK_LIST>\n  <TRACK_COUNT>1</TRACK_COUNT>\n' +
    '  <TRACK><CHANNEL_INDEX>1</CHANNEL_INDEX><INTERLEAVE_INDEX>1</INTERLEAVE_INDEX><NAME>Mono</NAME></TRACK>\n </TRACK_LIST>\n' :
    ' <TRACK_LIST>\n  <TRACK_COUNT>2</TRACK_COUNT>\n' +
    '  <TRACK><CHANNEL_INDEX>1</CHANNEL_INDEX><INTERLEAVE_INDEX>1</INTERLEAVE_INDEX><NAME>L</NAME></TRACK>\n' +
    '  <TRACK><CHANNEL_INDEX>2</CHANNEL_INDEX><INTERLEAVE_INDEX>2</INTERLEAVE_INDEX><NAME>R</NAME></TRACK>\n </TRACK_LIST>\n') +
    (meta.location ? ' <LOCATION>\n  <LOCATION_GPS>' + meta.location.lat.toFixed(6) + ', ' + meta.location.lon.toFixed(6) + '</LOCATION_GPS>\n' +
      (meta.location.alt != null ? '  <LOCATION_ALTITUDE>' + Math.round(meta.location.alt) + '</LOCATION_ALTITUDE>\n' : '') + ' </LOCATION>\n' : '') +
    el('USER', user.map(function (u) { return u[0] + ': ' + u[1]; }).join('\n')) + '</BWFXML>\n';
}
/* XMP's GPS form: degrees, decimal minutes and the hemisphere, "50,5.1234N" */
function gpsCoord(v, pos, neg) { var a = Math.abs(v), d = Math.floor(a); return d + ',' + ((a - d) * 60).toFixed(4) + (v >= 0 ? pos : neg); }
function gpsAttrs(l) {
  return '\n    exif:GPSVersionID="2.2.0.0"\n    exif:GPSLatitude="' + gpsCoord(l.lat, 'N', 'S') + '"\n    exif:GPSLongitude="' + gpsCoord(l.lon, 'E', 'W') + '"' +
    (l.alt != null ? '\n    exif:GPSAltitudeRef="' + (l.alt < 0 ? 1 : 0) + '"\n    exif:GPSAltitude="' + Math.round(Math.abs(l.alt) * 10) + '/10"' : '');
}
function xmpText(meta) {
  var paths = keywordPaths(meta), flat = [], d = meta.date, s;
  paths.forEach(function (p) {
    var parts = p.split('/');
    if (parts.length > 1 && /^(Projects|Status|Source)$/.test(parts[0])) parts = parts.slice(1);
    parts.forEach(function (w) { if (flat.indexOf(w) < 0) flat.push(w); });
  });
  function bag(tag, kind, items) {
    return items.length ? '\n   <' + tag + '>\n    <rdf:' + kind + '>' + items.map(function (i) { return '\n     <rdf:li>' + xmlEsc(i) + '</rdf:li>'; }).join('') + '\n    </rdf:' + kind + '>\n   </' + tag + '>' : '';
  }
  function alt(tag, v) { return v ? '\n   <' + tag + '>\n    <rdf:Alt>\n     <rdf:li xml:lang="x-default">' + xmlEsc(v) + '</rdf:li>\n    </rdf:Alt>\n   </' + tag + '>' : ''; }
  s = '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="' + ORIGINATOR + '">\n' +
    ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n  <rdf:Description rdf:about=""\n' +
    '    xmlns:dc="http://purl.org/dc/elements/1.1/"\n    xmlns:lr="http://ns.adobe.com/lightroom/1.0/"\n' +
    '    xmlns:digiKam="http://www.digikam.org/ns/1.0/"\n    xmlns:xmp="http://ns.adobe.com/xap/1.0/"\n' +
    '    xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/"' + (meta.location ? '\n    xmlns:exif="http://ns.adobe.com/exif/1.0/"' + gpsAttrs(meta.location) : '') +
    (d ? '\n    xmp:CreateDate="' + xmlEsc(d) + '"\n    photoshop:DateCreated="' + xmlEsc(d) + '"' : '') +
    '\n    xmp:CreatorTool="' + ORIGINATOR + '">' +
    alt('dc:title', meta.title) + alt('dc:description', meta.note) +
    bag('dc:subject', 'Bag', flat) + bag('lr:hierarchicalSubject', 'Bag', paths.map(function (p) { return p.replace(/\//g, '|'); })) +
    bag('digiKam:TagsList', 'Seq', paths) +
    (meta.creator ? bag('dc:creator', 'Seq', [meta.creator]) : '') +
    (meta.origin ? '\n   <dc:source>' + xmlEsc(meta.origin) + '</dc:source>' : '') + alt('dc:rights', meta.rights) +
    '\n  </rdf:Description>\n </rdf:RDF>\n</x:xmpmeta>\n<?xpacket end="w"?>\n';
  return s;
}
/* a WAV at 48 kHz, 24-bit PCM or 32-bit float, with the metadata chunks ahead of the audio when meta is given:
   stereo, or mono when R is null (a recording from a one-channel microphone stays one channel) */
function wavFile(L, R, float, meta) {
  var N = L.length, nch = R ? 2 : 1, bps = float ? 4 : 3, block = nch * bps, chunks = [], fmt = new Uint8Array(16), fv = new DataView(fmt.buffer), n, c;
  fv.setUint16(0, float ? 3 : 1, true); fv.setUint16(2, nch, true); fv.setUint32(4, FS, true); fv.setUint32(8, FS * block, true);
  fv.setUint16(12, block, true); fv.setUint16(14, bps * 8, true);
  chunks.push(['fmt ', fmt]);
  if (meta) { chunks.push(['bext', bextBytes(meta, float, nch)]); chunks.push(['iXML', utf8(ixmlText(meta, nch))]); chunks.push(['_PMX', utf8(xmpText(meta))]); }
  var dataLen = N * block, size = 4;
  chunks.forEach(function (ch) { size += 8 + ch[1].length + (ch[1].length & 1); });
  size += 8 + dataLen;
  var bytes = new Uint8Array(8 + size), dv = new DataView(bytes.buffer), o = 0;
  function id(s) { for (var i = 0; i < 4; i++) bytes[o + i] = s.charCodeAt(i); o += 4; }
  id('RIFF'); dv.setUint32(o, size, true); o += 4; id('WAVE');
  chunks.forEach(function (ch) { id(ch[0]); dv.setUint32(o, ch[1].length, true); o += 4; bytes.set(ch[1], o); o += ch[1].length + (ch[1].length & 1); });
  id('data'); dv.setUint32(o, dataLen, true); o += 4;
  if (float) for (n = 0; n < N; n++) { dv.setFloat32(o, L[n], true); o += 4; if (R) { dv.setFloat32(o, R[n], true); o += 4; } }
  else for (n = 0; n < N; n++) for (c = 0; c < nch; c++) {
    var v = Math.round(clamp(c ? R[n] : L[n], -1, 1) * 8388607);
    bytes[o++] = v & 255; bytes[o++] = (v >> 8) & 255; bytes[o++] = (v >> 16) & 255;
  }
  return bytes;
}
function encodeWav(L, R, meta) { return wavFile(L, R, false, meta); }
/* 32-bit float WAV: keeps the sound exactly, for handing on to SFX Workbench */
function encodeWavFloat(L, R, meta) { return wavFile(L, R, true, meta); }
/* ---------- QR codes, for plan links a phone can scan ----------
   Byte mode, error correction M (L when M does not fit), versions 1 to 40; the mask with the lowest penalty. After
   Project Nayuki's QR Code generator (MIT): the same tables and steps, written small. */
var QR_ECC = { L: [1, [-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
    [-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25]],
  M: [0, [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28],
    [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49]] };
function qrRawModules(v) {
  var r = (16 * v + 128) * v + 64;
  if (v >= 2) { var na = Math.floor(v / 7) + 2; r -= (25 * na - 10) * na - 55; if (v >= 7) r -= 36; }
  return r;
}
function qrDataCodewords(v, e) { return Math.floor(qrRawModules(v) / 8) - QR_ECC[e][1][v] * QR_ECC[e][2][v]; }
function rsMul(x, y) { var z = 0, i; for (i = 7; i >= 0; i--) { z = (z << 1) ^ ((z >>> 7) * 0x11D); z ^= ((y >>> i) & 1) * x; } return z; }
function rsDivisor(deg) {
  var r = [], root = 1, i, j;
  for (i = 0; i < deg - 1; i++) r.push(0);
  r.push(1);
  for (i = 0; i < deg; i++) {
    for (j = 0; j < r.length; j++) { r[j] = rsMul(r[j], root); if (j + 1 < r.length) r[j] ^= r[j + 1]; }
    root = rsMul(root, 2);
  }
  return r;
}
function rsRemainder(data, div) {
  var r = div.map(function () { return 0; });
  data.forEach(function (b) { var f = b ^ r.shift(); r.push(0); div.forEach(function (c, i) { r[i] ^= rsMul(c, f); }); });
  return r;
}
/* the QR code of a text (UTF-8): { size, dark(x, y) }, or null when it is too long for version 40 */
function qrCode(text) {
  var bytes = Array.prototype.slice.call(utf8(text)), ecl = null, ver = 0, e, v;
  for (e = 0; e < 2 && !ecl; e++) {
    var lv = e ? 'L' : 'M';
    for (v = 1; v <= 40; v++) if (4 + (v < 10 ? 8 : 16) + 8 * bytes.length <= qrDataCodewords(v, lv) * 8) { ecl = lv; ver = v; break; }
  }
  if (!ecl) return null;
  var cap = qrDataCodewords(ver, ecl) * 8, bits = [], i, j;
  function put(val, n) { for (var k = n - 1; k >= 0; k--) bits.push((val >>> k) & 1); }
  put(4, 4); put(bytes.length, ver < 10 ? 8 : 16);
  bytes.forEach(function (b) { put(b, 8); });
  put(0, Math.min(4, cap - bits.length));
  put(0, (8 - bits.length % 8) % 8);
  for (var pad = 0xEC; bits.length < cap; pad ^= 0xEC ^ 0x11) put(pad, 8);
  var data = [];
  for (i = 0; i < bits.length; i += 8) { var by = 0; for (j = 0; j < 8; j++) by = (by << 1) | bits[i + j]; data.push(by); }
  /* blocks with their error correction, interleaved */
  var nb = QR_ECC[ecl][2][ver], el = QR_ECC[ecl][1][ver], raw = Math.floor(qrRawModules(ver) / 8), nShort = nb - raw % nb, shortLen = Math.floor(raw / nb);
  var blocks = [], div = rsDivisor(el), k = 0, all = [];
  for (i = 0; i < nb; i++) {
    var dat = data.slice(k, k + shortLen - el + (i < nShort ? 0 : 1));
    k += dat.length;
    var ecc = rsRemainder(dat, div);
    if (i < nShort) dat.push(0);
    blocks.push(dat.concat(ecc));
  }
  for (i = 0; i < blocks[0].length; i++) blocks.forEach(function (b, bj) { if (i !== shortLen - el || bj >= nShort) all.push(b[i]); });
  /* function patterns */
  var size = ver * 4 + 17, mod = [], fn = [];
  for (i = 0; i < size; i++) { mod.push(new Array(size).fill(false)); fn.push(new Array(size).fill(false)); }
  function setF(x, y, d) { mod[y][x] = d; fn[y][x] = true; }
  for (i = 0; i < size; i++) { setF(6, i, i % 2 === 0); setF(i, 6, i % 2 === 0); }
  [[3, 3], [size - 4, 3], [3, size - 4]].forEach(function (c) {
    for (var dy = -4; dy <= 4; dy++) for (var dx = -4; dx <= 4; dx++) {
      var d = Math.max(Math.abs(dx), Math.abs(dy)), xx = c[0] + dx, yy = c[1] + dy;
      if (xx >= 0 && xx < size && yy >= 0 && yy < size) setF(xx, yy, d !== 2 && d !== 4);
    }
  });
  var al = [];
  if (ver > 1) {
    var na = Math.floor(ver / 7) + 2, step = Math.floor((ver * 8 + na * 3 + 5) / (na * 4 - 4)) * 2;
    for (var pos = size - 7; al.length < na - 1; pos -= step) al.unshift(pos);
    al.unshift(6);
  }
  al.forEach(function (ax, ai) {
    al.forEach(function (ay, aj) {
      if ((ai === 0 && aj === 0) || (ai === 0 && aj === al.length - 1) || (ai === al.length - 1 && aj === 0)) return;
      for (var dy = -2; dy <= 2; dy++) for (var dx = -2; dx <= 2; dx++) setF(ax + dx, ay + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
    });
  });
  function format(mask) {
    var d = QR_ECC[ecl][0] << 3 | mask, r = d, q;
    for (q = 0; q < 10; q++) r = (r << 1) ^ ((r >>> 9) * 0x537);
    var b = (d << 10 | r) ^ 0x5412;
    function g(n) { return ((b >>> n) & 1) !== 0; }
    for (q = 0; q <= 5; q++) setF(8, q, g(q));
    setF(8, 7, g(6)); setF(8, 8, g(7)); setF(7, 8, g(8));
    for (q = 9; q < 15; q++) setF(14 - q, 8, g(q));
    for (q = 0; q < 8; q++) setF(size - 1 - q, 8, g(q));
    for (q = 8; q < 15; q++) setF(8, size - 15 + q, g(q));
    setF(8, size - 8, true);
  }
  format(0);
  if (ver >= 7) {
    var r = ver, q;
    for (q = 0; q < 12; q++) r = (r << 1) ^ ((r >>> 11) * 0x1F25);
    var vb = ver << 12 | r;
    for (q = 0; q < 18; q++) { var c = ((vb >>> q) & 1) !== 0, a = size - 11 + q % 3, bq = Math.floor(q / 3); setF(a, bq, c); setF(bq, a, c); }
  }
  /* the codewords, zigzag from the bottom right */
  var bi = 0;
  for (var right = size - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (var vert = 0; vert < size; vert++) for (j = 0; j < 2; j++) {
      var x = right - j, up = ((right + 1) & 2) === 0, y = up ? size - 1 - vert : vert;
      if (!fn[y][x] && bi < all.length * 8) { mod[y][x] = ((all[bi >>> 3] >>> (7 - (bi & 7))) & 1) !== 0; bi++; }
    }
  }
  function maskOn(m, x, y) {
    switch (m) {
      case 0: return (x + y) % 2 === 0;
      case 1: return y % 2 === 0;
      case 2: return x % 3 === 0;
      case 3: return (x + y) % 3 === 0;
      case 4: return (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0;
      case 5: return x * y % 2 + x * y % 3 === 0;
      case 6: return (x * y % 2 + x * y % 3) % 2 === 0;
      default: return ((x + y) % 2 + x * y % 3) % 2 === 0;
    }
  }
  function applyMask(m) { for (var yy = 0; yy < size; yy++) for (var xx = 0; xx < size; xx++) if (!fn[yy][xx] && maskOn(m, xx, yy)) mod[yy][xx] = !mod[yy][xx]; }
  /* penalty: runs of five or more, 2x2 blocks, finder-like patterns, imbalance of dark and light */
  function penalty() {
    var p = 0, dark = 0, x2, y2, line, run, prev, n;
    for (var pass = 0; pass < 2; pass++) for (var a2 = 0; a2 < size; a2++) {
      line = [];
      for (var b2 = 0; b2 < size; b2++) line.push(pass ? mod[b2][a2] : mod[a2][b2]);
      run = 1; prev = line[0];
      for (n = 1; n <= size; n++) {
        if (n < size && line[n] === prev) run++;
        else { if (run >= 5) p += run - 2; run = 1; prev = line[n]; }
      }
      var s = line.map(function (d) { return d ? '1' : '0'; }).join('');
      for (n = s.indexOf('1011101'); n >= 0; n = s.indexOf('1011101', n + 1)) {
        if (s.substr(n - 4, 4) === '0000' || s.substr(n + 7, 4) === '0000' || n < 4 || n + 11 > size) p += 40;
      }
    }
    for (y2 = 0; y2 < size; y2++) for (x2 = 0; x2 < size; x2++) {
      if (mod[y2][x2]) dark++;
      if (x2 < size - 1 && y2 < size - 1) { var c0 = mod[y2][x2]; if (c0 === mod[y2][x2 + 1] && c0 === mod[y2 + 1][x2] && c0 === mod[y2 + 1][x2 + 1]) p += 3; }
    }
    return p + Math.floor(Math.abs(dark * 20 - size * size * 10) / (size * size)) * 10;
  }
  var best = 0, bestP = Infinity, m;
  for (m = 0; m < 8; m++) { applyMask(m); format(m); var pp = penalty(); if (pp < bestP) { bestP = pp; best = m; } applyMask(m); }
  applyMask(best); format(best);
  return { size: size, version: ver, ecl: ecl, dark: function (x, y) { return x >= 0 && y >= 0 && x < size && y < size && mod[y][x]; } };
}
/* the code as an SVG path, a quiet zone of 4 modules round it */
function qrSvg(text, color) {
  var q = qrCode(text);
  if (!q) return null;
  var d = '', n = q.size + 8, x, y;
  for (y = 0; y < q.size; y++) for (x = 0; x < q.size; x++) if (q.dark(x, y)) d += 'M' + (x + 4) + ',' + (y + 4) + 'h1v1h-1z';
  return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + n + ' ' + n + '" shape-rendering="crispEdges"><rect width="' + n + '" height="' + n + '" fill="#fff"/><path d="' + d + '" fill="' + (color || '#000') + '"/></svg>';
}

/* ---------- recording plans in a link ----------
   A plan travels in the part of the address after #plan=, which browsers never send to the web server: base64url of
   its JSON with short keys, so that a long plan still fits a QR code. Kurator writes the same. */
function b64url(bytes) {
  var s = '', i;
  for (i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function unb64url(s) {
  var t = atob(String(s).replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4)), b = new Uint8Array(t.length), i;
  for (i = 0; i < t.length; i++) b[i] = t.charCodeAt(i);
  return b;
}
function packPlan(pl) {
  var o = { v: 1, i: pl.id, n: pl.name };
  if (pl.project) o.p = pl.project;
  if (pl.chips && pl.chips.length) o.c = pl.chips;
  o.s = (pl.shots || []).map(function (s) {
    var x = { i: s.id, n: s.name };
    if (s.tags && s.tags.length) x.t = s.tags;
    if (s.takes > 1) x.k = s.takes;
    if (s.ucs) x.u = s.ucs;
    if (s.notes) x.o = s.notes;
    return x;
  });
  return b64url(utf8(JSON.stringify(o)));
}
/* a plan from a link, checked: null when it is not one */
function unpackPlan(s) {
  var o;
  try { o = JSON.parse(decodeURIComponent(escape(String.fromCharCode.apply(null, unb64url(s))))); } catch (e) { return null; }
  if (!o || o.v !== 1 || typeof o.n !== 'string' || !Array.isArray(o.s)) return null;
  function str(v, n) { return typeof v === 'string' ? v.slice(0, n) : ''; }
  function list(v) { return Array.isArray(v) ? v.filter(function (t) { return typeof t === 'string' && t.trim(); }).map(function (t) { return t.slice(0, 100); }).slice(0, 20) : []; }
  return { id: str(o.i, 40) || 'plan-' + Date.now().toString(36), name: str(o.n, 100) || 'Plan', project: str(o.p, 100), chips: list(o.c),
    shots: o.s.slice(0, 100).filter(function (s) { return s && typeof s.n === 'string'; }).map(function (s, k) {
      return { id: str(s.i, 40) || 's' + (k + 1), name: str(s.n, 100), tags: list(s.t), takes: Math.max(1, Math.min(99, Math.round(+s.k) || 1)), ucs: str(s.u, 40), notes: str(s.o, 300) };
    }) };
}
var crcTable = null;
function crc32(b) {
  if (!crcTable) { crcTable = new Uint32Array(256); for (var n = 0; n < 256; n++) { var c = n; for (var k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; crcTable[n] = c; } }
  var crc = -1;
  for (var i = 0; i < b.length; i++) crc = crcTable[(crc ^ b[i]) & 255] ^ (crc >>> 8);
  return (crc ^ -1) >>> 0;
}
/* uncompressed zip of [{ name, data }] (the viewer inside Claude saves zips, not bare wav files) */
function zipFiles(list) {
  var parts = [], central = [], off = 0, total = 0;
  list.forEach(function (f) {
    var nb = new Uint8Array(f.name.length), i;
    for (i = 0; i < f.name.length; i++) nb[i] = f.name.charCodeAt(i) & 127;
    var crc = crc32(f.data), lh = new Uint8Array(30 + nb.length), dv = new DataView(lh.buffer);
    dv.setUint32(0, 0x04034b50, true); dv.setUint16(4, 20, true); dv.setUint16(12, 0x21, true);
    dv.setUint32(14, crc, true); dv.setUint32(18, f.data.length, true); dv.setUint32(22, f.data.length, true); dv.setUint16(26, nb.length, true);
    lh.set(nb, 30);
    var ch = new Uint8Array(46 + nb.length), cv = new DataView(ch.buffer);
    cv.setUint32(0, 0x02014b50, true); cv.setUint16(4, 20, true); cv.setUint16(6, 20, true); cv.setUint16(14, 0x21, true);
    cv.setUint32(16, crc, true); cv.setUint32(20, f.data.length, true); cv.setUint32(24, f.data.length, true); cv.setUint16(28, nb.length, true);
    cv.setUint32(42, off, true); ch.set(nb, 46);
    parts.push(lh, f.data); central.push(ch); off += lh.length + f.data.length;
  });
  var csz = 0; central.forEach(function (c) { csz += c.length; });
  var end = new Uint8Array(22), ev = new DataView(end.buffer);
  ev.setUint32(0, 0x06054b50, true); ev.setUint16(8, list.length, true); ev.setUint16(10, list.length, true);
  ev.setUint32(12, csz, true); ev.setUint32(16, off, true);
  parts = parts.concat(central, [end]);
  parts.forEach(function (q) { total += q.length; });
  var out = new Uint8Array(total), o = 0;
  parts.forEach(function (q) { out.set(q, o); o += q.length; });
  return out;
}
function zipStore(name, data) { return zipFiles([{ name: name, data: data }]); }

/* ---------- presets ---------- */
var DEFAULTS = { kind: 'projectile',
  v0: 850, cal: 7.82, mass: 0.0095, lenRatio: 3.6, cdScale: 1, tumble: 0, tumbleHz: 200, swing: false, pathLen: 0, payload: 0,
  D: 300, miss: 4, launch: 'blast', target: 'none', targetDist: 400,
  exW: 2, exDist: 40, exFrags: 5, exDebris: 40, exSurface: 'dirt',
  imR0: 0.15, imDp: 1, imGas: 0.03, imMedium: 'air', imShell: 'glass', imGroan: 0.6, imDist: 3,
  dsMat: 'glass', dsMass: 4, dsHeight: 1.5, dsPieces: 40, dsGroan: 0, dsDist: 3, dsSpread: 1.5,
  rkMode: 'launch', rkPath: 'horizontal', rkThrust: 1200, rkUe: 1800, rkNozzle: 0.05, rkMass: 2.6, rkBurn: 0.6, rkV0: 200, rkCrackle: 0.5, rkChug: 0.1, rkWhine: 0, rkWhineHz: 3000,
  rtMode: 'hover', rtMass: 1.2, rtCount: 4, rtDia: 0.24, rtBlades: 2, rtSpeed: 15, rtWander: 0.5, rtSlap: 0, rtWhine: 0.3,
  dcEnergy: 2, dcLength: 0.02, dcDist: 1, dcOrient: 'horizontal', dcTort: 0.5, dcBranches: 0, dcStrokes: 1, dcSustain: 0, dcRate: 120, dcCharge: 0, dcChargeHz: 8000, dcKick: 0, dcRingHz: 520,
  bpLength: 25, bpStiff: 0.6, bpTension: 0, bpHard: 6000, bpDamp: 0.3, bpEchoes: 0, bpRefl: 0.7, bpBody: 'can', bpEnergy: 5,
  lnType: 'line', lnLength: 4, lnStages: 8, lnCharge: 0, lnChargeHz: 7000, lnRingHz: 180, lnEnergy: 20000, lnChamber: 30, lnSpring: 0.6,
  bvType: 'none', bvSpeed: 300, bvChannel: 40, bvPulses: 1, bvRate: 40, bvSizzle: 0.6, bvTone: 900, bvCal: 20,
  tgMat: 'none', tgEnergy: 2000, tgThick: 5, tgSize: 1.5, tgHeat: 0.5,
  rcAsset: 'ex:engine', rcMode: 'place', rcDist: 5, rcSpeed: 25, rcPass: 8, rcHeight: 0.6, rcBody: 'none', rcThick: 1, rcSize: 2, rcLength: 4, rcIr: 'ex:knock',
  irAsset: 'ex:stair', irWet: -6,
  ffMode: 'hum', ffBase: 62, ffType: 'membrane', ffBeat: 1.5, ffShimmer: 0.5, ffCorona: 0.4, ffHitE: 2000, ffGlide: 0.6, ffDist: 3,
  ffB: 1, ffDens: 1e19, ffBeta: 0.3, ffAngle: 30, ffSaw: 0.4, ffSawT: 1.33, ffChorus: 0.4, ffSurface: 0.4, ffSoliton: 0.4,
  seqCount: 1, seqInterval: 0.12, seqJitter: 0.2, seqFrom: 'interval', seqAsset: 'ex:door', seqSens: 0.5, seqDyn: 0.7, seqGuide: -40,
  dsKnock: 'ex:knock', dsLike: 'glass', dsDebris: 'model', grAsset: 'ex:gravel',
  env: 'field', ground: 0.5, trimCrack: 0, trimLaunch: 0, trimWake: 0, trimImpact: 0 };
var PRESETS = [
  { id: 'rifle', name: 'Rifle, downrange', p: { trimLaunch: 12 } },
  { id: 'ear', name: 'Rifle, at the shooter', p: { D: 0, miss: 0.6, env: 'forest', ground: 0.3 } },
  { id: 'burst', name: 'Rifle burst', p: { D: 150, miss: 3, env: 'urban', trimLaunch: 10, seqCount: 3, seqInterval: 0.095, seqJitter: 0.1 } },
  { id: 'pistol', name: '.45 near miss', p: { v0: 255, cal: 11.43, mass: 0.0149, lenRatio: 1.5, D: 40, miss: 0.8, target: 'wood', targetDist: 52, env: 'urban', trimWake: 10, trimImpact: 10 } },
  { id: 'sniper', name: '.50 on steel', p: { v0: 890, cal: 12.95, mass: 0.042, lenRatio: 4.5, D: 600, miss: 12, target: 'steel', targetDist: 640, env: 'valley', trimLaunch: 14, trimImpact: 12 } },
  { id: 'tank', name: 'Tank gun, sabot', p: { v0: 1650, cal: 27, mass: 4.6, lenRatio: 20, D: 900, miss: 40, target: 'dirt', targetDist: 1400, env: 'field', trimLaunch: 6, trimImpact: 12 } },
  { id: 'mortar', name: 'Incoming mortar', p: { v0: 240, cal: 81, mass: 4.2, lenRatio: 5, D: 600, miss: 20, target: 'dirt', targetDist: 625, payload: 1, exFrags: 4, exDebris: 50, env: 'field', trimLaunch: 22, trimWake: 24, trimImpact: -12 } },
  { id: 'arrow', name: 'Arrow', p: { v0: 68, cal: 8, mass: 0.028, lenRatio: 90, cdScale: 2, tumble: 0.25, tumbleHz: 45, D: 25, miss: 0.5, launch: 'string', target: 'wood', targetDist: 32, env: 'forest', ground: 0.3, trimWake: 8, trimLaunch: 4, trimImpact: -4 } },
  { id: 'ricochet', name: 'Ricochet', p: { v0: 330, cal: 9, mass: 0.008, lenRatio: 2, tumble: 0.9, tumbleHz: 650, D: 4, miss: 8, launch: 'ricSteel', env: 'urban' } },
  { id: 'swing', name: 'Blade swing', p: { v0: 28, cal: 6, mass: 1.2, lenRatio: 100, swing: true, pathLen: 2.6, D: 1.2, miss: 0.5, launch: 'none', env: 'indoor', ground: 0 } },
  { id: 'flyover', name: 'Supersonic flyover', p: { v0: 520, cal: 1800, mass: 14000, lenRatio: 8, D: 1500, miss: 350, launch: 'none', env: 'valley', trimWake: -6 } },

  { id: 'charge', name: 'Charge, close', p: { kind: 'explosion', exW: 0.5, exDist: 25, exFrags: 6, exDebris: 45, exSurface: 'concrete', env: 'urban' } },
  { id: 'fragstorm', name: 'Fragment storm', p: { kind: 'explosion', exW: 1.5, exDist: 18, exFrags: 14, exDebris: 70, exSurface: 'steel', env: 'urban', trimWake: 4 } },
  { id: 'bigblast', name: 'Large blast, far', p: { kind: 'explosion', exW: 400, exDist: 900, exFrags: 0, exDebris: 0, env: 'valley', trimLaunch: 6 } },
  { id: 'gravelblast', name: 'Charge, gravel debris', p: { kind: 'explosion', exW: 0.5, exDist: 25, exFrags: 3, exDebris: 60, exSurface: 'rec', grAsset: 'ex:gravel', env: 'field' } },
  { id: 'barrage', name: 'Barrage', p: { kind: 'explosion', exW: 8, exDist: 350, exFrags: 0, exDebris: 12, exSurface: 'dirt', env: 'field', seqCount: 6, seqInterval: 0.45, seqJitter: 0.9 } },

  { id: 'tube', name: 'Vacuum tube', p: { kind: 'implosion', imR0: 0.12, imDp: 1, imGas: 0.03, imMedium: 'air', imShell: 'glass', imGroan: 0.5, imDist: 2, env: 'indoor' } },
  { id: 'vactank', name: 'Vacuum tank', p: { kind: 'implosion', imR0: 1.4, imDp: 1, imGas: 0.1, imMedium: 'air', imShell: 'steel', imGroan: 1.6, imDist: 15, env: 'field' } },
  { id: 'bubble', name: 'Cavitation bubble', p: { kind: 'implosion', imR0: 0.4, imDp: 3, imGas: 0.08, imMedium: 'water', imShell: 'none', imGroan: 0, imDist: 10, env: 'water', ground: 0 } },
  { id: 'hull', name: 'Deep hull', p: { kind: 'implosion', imR0: 1.2, imDp: 250, imGas: 0.004, imMedium: 'water', imShell: 'steel', imGroan: 2.5, imDist: 400, env: 'water', ground: 0 } },

  { id: 'window', name: 'Window pane', p: { kind: 'destruction', dsMat: 'glass', dsMass: 6, dsHeight: 1.6, dsPieces: 70, dsGroan: 0.4, dsDist: 2.5, dsSpread: 1.2, env: 'indoor', trimWake: 8 } },
  { id: 'crate', name: 'Wooden crate', p: { kind: 'destruction', dsMat: 'wood', dsMass: 25, dsHeight: 1.2, dsPieces: 18, dsGroan: 0.5, dsDist: 3, dsSpread: 1, env: 'indoor' } },
  { id: 'wall', name: 'Concrete wall', p: { kind: 'destruction', dsMat: 'concrete', dsMass: 3000, dsHeight: 3, dsPieces: 90, dsGroan: 1.2, dsDist: 12, dsSpread: 5, env: 'urban' } },
  { id: 'potshatter', name: 'Measured pot, shattered', p: { kind: 'destruction', dsMat: 'measured', dsKnock: 'ex:knock', dsLike: 'glass', dsMass: 3, dsHeight: 1.2, dsPieces: 30, dsDist: 2.5, dsSpread: 1, env: 'indoor', trimWake: 6 } },
  { id: 'potdrop', name: 'Measured pot, dropped', p: { kind: 'destruction', dsMat: 'measured', dsKnock: 'ex:knock', dsLike: 'steel', dsMass: 3, dsHeight: 1.2, dsPieces: 3, dsDist: 2.5, dsSpread: 0.6, env: 'indoor' } },
  { id: 'knockglass', name: 'Knocks shatter glass', p: { kind: 'destruction', dsMat: 'glass', dsMass: 1.5, dsHeight: 1.2, dsPieces: 25, dsDist: 3, dsSpread: 1, seqFrom: 'rec', seqAsset: 'ex:door', seqDyn: 0.9, seqGuide: -6, env: 'indoor' } },
  { id: 'wallgravel', name: 'Wall onto gravel', p: { kind: 'destruction', dsMat: 'concrete', dsMass: 3000, dsHeight: 3, dsPieces: 90, dsGroan: 1.2, dsDist: 12, dsSpread: 5, dsDebris: 'rec', grAsset: 'ex:gravel', env: 'urban' } },
  { id: 'gantry', name: 'Steel gantry', p: { kind: 'destruction', dsMat: 'steel', dsMass: 1500, dsHeight: 8, dsPieces: 24, dsGroan: 2.5, dsDist: 20, dsSpread: 6, env: 'urban' } },

  { id: 'launcher', name: 'Launcher, at the shooter', p: { kind: 'rocket', rkMode: 'launch', D: 0, miss: 1.5, target: 'concrete', targetDist: 180, payload: 0.7, exFrags: 0, exDebris: 30, env: 'field' } },
  { id: 'incoming', name: 'Rocket, incoming', p: { kind: 'rocket', rkMode: 'launch', rkThrust: 600, rkBurn: 1.5, D: 170, miss: 15, target: 'concrete', targetDist: 180, payload: 0.7, exFrags: 4, exDebris: 40, env: 'urban', trimCrack: 16, trimLaunch: 16, trimImpact: -14 } },
  { id: 'salvo', name: 'Rocket salvo', p: { kind: 'rocket', rkMode: 'launch', rkThrust: 25000, rkUe: 2200, rkNozzle: 0.1, rkMass: 66, rkBurn: 1.8, rkCrackle: 0.7, D: 0, miss: 60, env: 'field', seqCount: 6, seqInterval: 0.5, seqJitter: 0.25 } },
  { id: 'booster', name: 'Heavy launch', p: { kind: 'rocket', rkMode: 'launch', rkPath: 'vertical', rkThrust: 7600000, rkUe: 2900, rkNozzle: 3.6, rkMass: 550000, rkBurn: 11, rkCrackle: 0.8, rkChug: 0.15, D: 0, miss: 1500, env: 'field' } },
  { id: 'rlanding', name: 'Booster landing', p: { kind: 'rocket', rkMode: 'landing', rkPath: 'vertical', rkThrust: 850000, rkUe: 2900, rkNozzle: 0.95, rkMass: 25000, rkV0: 240, rkCrackle: 0.8, D: 1600, miss: 400, target: 'concrete', env: 'field', trimImpact: 20 } },
  { id: 'jet', name: 'Jet fly-by', p: { kind: 'rocket', rkMode: 'flyby', rkThrust: 80000, rkUe: 600, rkNozzle: 0.8, rkMass: 12000, rkV0: 180, rkCrackle: 0.5, rkChug: 0, rkWhine: 0.6, rkWhineHz: 3200, D: 600, miss: 80, env: 'valley', trimWake: 6 } },
  { id: 'thruster', name: 'Thruster burn, loop', p: { kind: 'rocket', rkMode: 'static', rkThrust: 400, rkUe: 2200, rkNozzle: 0.06, rkMass: 50, rkCrackle: 0.4, rkChug: 0.3, miss: 4, env: 'indoor' } },

  { id: 'quad', name: 'Quadcopter hover, loop', p: { kind: 'rotor', rtMode: 'hover', miss: 3, rtWander: 0.6, rtWhine: 0.4, env: 'field' } },
  { id: 'quadpass', name: 'Quadcopter fly-by', p: { kind: 'rotor', rtMode: 'flyby', rtSpeed: 18, D: 60, miss: 4, env: 'field' } },
  { id: 'swarm', name: 'Drone swarm', p: { kind: 'rotor', rtMode: 'flyby', rtMass: 0.35, rtDia: 0.13, rtBlades: 3, rtSpeed: 28, D: 80, miss: 6, env: 'urban', seqCount: 5, seqInterval: 0.4, seqJitter: 0.9 } },
  { id: 'heavylift', name: 'Heavy-lift take-off', p: { kind: 'rotor', rtMode: 'takeoff', rtMass: 25, rtCount: 8, rtDia: 0.75, rtSpeed: 8, D: 0, miss: 6, env: 'field' } },
  { id: 'quadland', name: 'Quadcopter landing', p: { kind: 'rotor', rtMode: 'landing', rtSpeed: 10, D: 25, miss: 3, env: 'field' } },
  { id: 'heli', name: 'Helicopter fly-by', p: { kind: 'rotor', rtMode: 'flyby', rtMass: 2200, rtCount: 1, rtDia: 10.7, rtBlades: 3, rtSpeed: 55, rtSlap: 0.7, rtWhine: 0.5, rtWander: 0.2, D: 500, miss: 120, env: 'valley' } },
  { id: 'helihover', name: 'Helicopter hover, loop', p: { kind: 'rotor', rtMode: 'hover', rtMass: 2200, rtCount: 1, rtDia: 10.7, rtBlades: 3, rtSlap: 0.3, rtWhine: 0.5, rtWander: 0.2, miss: 60, env: 'field' } },

  { id: 'arcgun', name: 'Arc weapon', p: { kind: 'discharge', dcEnergy: 5000, dcLength: 12, dcDist: 6, dcBranches: 4, dcStrokes: 2, dcSustain: 0.4, dcRate: 220, dcCharge: 1.1, dcChargeHz: 9000, dcKick: 0.8, dcRingHz: 520, env: 'urban' } },
  { id: 'coilgun', name: 'Coil gun discharge', p: { kind: 'discharge', dcEnergy: 200000, dcLength: 0.3, dcDist: 5, dcCharge: 1.6, dcChargeHz: 6500, dcKick: 1, dcRingHz: 280, env: 'indoor' } },
  { id: 'tesla', name: 'Coil arc', p: { kind: 'discharge', dcEnergy: 40, dcLength: 1.5, dcDist: 4, dcBranches: 3, dcSustain: 1.5, dcRate: 120, dcTort: 0.7, env: 'indoor' } },
  { id: 'stun', name: 'Stun arc', p: { kind: 'discharge', dcEnergy: 0.3, dcLength: 0.03, dcDist: 0.8, dcSustain: 1.2, dcRate: 28, dcTort: 0.8, env: 'indoor' } },
  { id: 'spark', name: 'Lab spark', p: { kind: 'discharge', env: 'indoor' } },
  { id: 'lightning', name: 'Lightning, 1 km', p: { kind: 'discharge', dcEnergy: 1e9, dcLength: 3000, dcDist: 1000, dcOrient: 'vertical', dcBranches: 5, dcStrokes: 3, env: 'valley' } },
  { id: 'closestrike', name: 'Lightning, close', p: { kind: 'discharge', dcEnergy: 5e8, dcLength: 2500, dcDist: 120, dcOrient: 'vertical', dcBranches: 6, dcStrokes: 2, env: 'field' } },

  { id: 'pew', name: 'Blaster', p: { kind: 'blaster', D: 0, miss: 3, env: 'indoor' } },
  { id: 'pewecho', name: 'Blaster, echoing', p: { kind: 'blaster', D: 0, miss: 3, bpEchoes: 3, bpRefl: 0.7, env: 'urban' } },
  { id: 'pulse', name: 'Pulse rifle', p: { kind: 'blaster', D: 0, miss: 3, bpLength: 12, bpStiff: 0.4, bpHard: 9000, bpEnergy: 3, env: 'urban', seqCount: 4, seqInterval: 0.11, seqJitter: 0.15 } },
  { id: 'cannon', name: 'Heavy cannon', p: { kind: 'blaster', D: 0, miss: 6, bpLength: 60, bpStiff: 2, bpTension: 150, bpHard: 2500, bpEchoes: 1, bpBody: 'tube', bpEnergy: 200, env: 'valley' } },
  { id: 'wire', name: 'Struck guy-wire', p: { kind: 'blaster', D: 0, miss: 8, bpLength: 120, bpStiff: 0.05, bpTension: 180, bpHard: 9000, bpEchoes: 4, bpRefl: 0.85, bpBody: 'none', bpEnergy: 20, env: 'field' } },
  { id: 'plasmabolt', name: 'Plasma bolt fly-by', p: { kind: 'blaster', lnType: 'none', bvType: 'bolt', bvSpeed: 160, bvChannel: 60, bvSizzle: 0.8, bvTone: 700, D: 40, miss: 2, tgMat: 'concrete', targetDist: 70, tgEnergy: 3000, tgHeat: 0.5, env: 'urban' } },
  { id: 'plasmarifle', name: 'Plasma rifle on steel', p: { kind: 'blaster', lnType: 'line', bvType: 'bolt', bvSpeed: 420, bvChannel: 40, D: 0, miss: 1, tgMat: 'steel', tgThick: 4, tgSize: 1.4, targetDist: 30, tgEnergy: 4000, tgHeat: 0.6, env: 'urban', trimWake: 8 } },
  { id: 'laser', name: 'Laser shot', p: { kind: 'blaster', lnType: 'none', bvType: 'beam', bvChannel: 120, D: 25, miss: 1.5, tgMat: 'steel', tgThick: 3, tgSize: 1.2, targetDist: 50, tgEnergy: 5000, tgHeat: 0.7, env: 'urban', trimWake: 8 } },
  { id: 'pulselaser', name: 'Pulsed laser', p: { kind: 'blaster', lnType: 'none', bvType: 'beam', bvChannel: 25, bvPulses: 24, bvRate: 45, D: 10, miss: 2, tgMat: 'concrete', targetDist: 40, tgEnergy: 8000, tgHeat: 0.6, env: 'urban', trimWake: 6 } },
  { id: 'railgun', name: 'Railgun', p: { kind: 'blaster', lnType: 'rail', lnLength: 6, lnCharge: 1.6, lnChargeHz: 6000, lnRingHz: 90, lnEnergy: 2e6, bvType: 'slug', bvSpeed: 2600, bvCal: 25, D: 0, miss: 3, tgMat: 'steel', tgThick: 40, tgSize: 2, targetDist: 400, tgHeat: 0.8, env: 'valley', trimWake: 18, trimImpact: 12 } },
  { id: 'raildown', name: 'Railgun, downrange', p: { kind: 'blaster', lnType: 'rail', lnLength: 6, lnCharge: 1.6, lnChargeHz: 6000, lnRingHz: 90, lnEnergy: 2e6, bvType: 'slug', bvSpeed: 2600, bvCal: 25, D: 300, miss: 12, tgMat: 'steel', tgThick: 40, tgSize: 2, targetDist: 400, tgHeat: 0.8, env: 'valley' } },
  { id: 'coilslug', name: 'Coilgun', p: { kind: 'blaster', lnType: 'coil', lnLength: 1.2, lnStages: 8, lnCharge: 1, lnChargeHz: 8500, lnRingHz: 240, lnEnergy: 20000, bvType: 'slug', bvSpeed: 280, bvCal: 12, D: 0, miss: 1.5, tgMat: 'wood', tgThick: 40, tgSize: 0.6, targetDist: 20, tgHeat: 0.1, env: 'indoor', trimWake: 8 } },
  { id: 'nailgun', name: 'Nail gun', p: { kind: 'blaster', lnType: 'gas', lnLength: 0.12, lnChamber: 40, lnSpring: 0.6, lnEnergy: 120, bvType: 'slug', bvSpeed: 40, bvCal: 3, D: 0, miss: 0.6, tgMat: 'wood', tgThick: 20, tgSize: 0.5, targetDist: 0.1, tgHeat: 0, env: 'indoor' } },
  { id: 'thundersheet', name: 'Thunder sheet', p: { kind: 'blaster', lnType: 'none', D: 0, miss: 2, tgMat: 'steel', tgThick: 0.8, tgSize: 2, targetDist: 0, tgEnergy: 30, tgHeat: 0, env: 'indoor' } },
  { id: 'icesheet', name: 'Ice sheet strike', p: { kind: 'blaster', lnType: 'none', D: 0, miss: 6, tgMat: 'ice', tgThick: 60, tgSize: 60, targetDist: 0, tgEnergy: 400, tgHeat: 0.6, env: 'valley' } },
  { id: 'knockfire', name: 'Knocks fire the blaster', p: { kind: 'blaster', D: 0, miss: 3, seqFrom: 'rec', seqAsset: 'ex:door', seqDyn: 0.8, env: 'indoor' } },
  { id: 'boltwater', name: 'Bolt into water', p: { kind: 'blaster', lnType: 'line', bvType: 'bolt', bvSpeed: 250, bvChannel: 50, D: 0, miss: 1, tgMat: 'water', targetDist: 20, tgEnergy: 6000, tgHeat: 0.7, env: 'field' } },

  { id: 'shield', name: 'Shield hum, loop', p: { kind: 'field', env: 'indoor' } },
  { id: 'shieldhit', name: 'Shield impact', p: { kind: 'field', ffMode: 'impact', env: 'indoor' } },
  { id: 'shieldup', name: 'Shield power-up', p: { kind: 'field', ffMode: 'powerup', env: 'indoor' } },
  { id: 'shielddown', name: 'Shield collapse', p: { kind: 'field', ffMode: 'powerdown', env: 'indoor' } },
  { id: 'reactor', name: 'Reactor core, loop', p: { kind: 'field', ffBase: 38, ffType: 'harmonic', ffBeat: 0.6, ffShimmer: 0.8, ffCorona: 0.15, env: 'indoor' } },
  { id: 'barrier', name: 'Energy barrier, loop', p: { kind: 'field', ffBase: 140, ffType: 'plate', ffBeat: 4, ffShimmer: 0.3, ffCorona: 0.8, env: 'urban' } },
  { id: 'plasma', name: 'Plasma shield, loop', p: { kind: 'field', ffType: 'plasma', ffBase: 70, ffBeat: 0.8, ffCorona: 0.3, env: 'indoor' } },
  { id: 'plasmahit', name: 'Plasma shield impact', p: { kind: 'field', ffType: 'plasma', ffMode: 'impact', ffBase: 70, ffBeat: 0.8, ffCorona: 0.3, ffHitE: 5000, env: 'indoor' } },
  { id: 'kink', name: 'Plasma disruption', p: { kind: 'field', ffType: 'plasma', ffMode: 'powerdown', ffBase: 70, ffBeat: 0.8, ffCorona: 0.3, env: 'indoor' } },
  { id: 'tokamak', name: 'Tokamak sawteeth, loop', p: { kind: 'field', ffType: 'plasma', ffBase: 110, ffB: 2.2, ffDens: 3e19, ffBeta: 0.1, ffAngle: 15, ffSaw: 1, ffSawT: 0.5, ffChorus: 0, ffSurface: 0.1, ffSoliton: 0, ffCorona: 0.2, ffBeat: 0.3, env: 'indoor' } },
  { id: 'chorus', name: 'Magnetosphere, loop', p: { kind: 'field', ffType: 'plasma', ffBase: 90, ffB: 0.6, ffBeta: 0.8, ffAngle: 55, ffSaw: 0.15, ffSawT: 2, ffChorus: 1, ffSurface: 0.2, ffSoliton: 0.2, ffCorona: 0.1, ffBeat: 0.4, ffShimmer: 0.8, env: 'valley' } },

  { id: 'carpass', name: 'Car pass-by', p: { kind: 'recording', rcAsset: 'ex:engine', rcMode: 'flyby', rcSpeed: 25, rcPass: 8, rcHeight: 0.5, D: 0, miss: 6, ground: 0.6, env: 'field' } },
  { id: 'lowflyover', name: 'Low flyover, ground flanging', p: { kind: 'recording', rcAsset: 'ex:engine', rcMode: 'flyby', rcSpeed: 70, rcPass: 10, rcHeight: 60, D: 0, miss: 0, ground: 0.8, env: 'valley' } },
  { id: 'tinroof', name: 'Rain on a tin roof', p: { kind: 'recording', rcAsset: 'ex:rain', rcBody: 'steel', rcThick: 0.6, rcSize: 3, rcDist: 3, env: 'indoor', trimCrack: -14 } },
  { id: 'lakeice', name: 'Rain on lake ice', p: { kind: 'recording', rcAsset: 'ex:rain', rcBody: 'ice', rcThick: 40, rcSize: 40, rcDist: 6, env: 'valley', trimCrack: -18 } },
  { id: 'laservoice', name: 'Voice through a dispersive line', p: { kind: 'recording', rcAsset: 'ex:voice', rcBody: 'line', rcLength: 25, rcDist: 2, env: 'indoor', trimCrack: -40 } },
  { id: 'springvoice', name: 'Voice in a spring', p: { kind: 'recording', rcAsset: 'ex:voice', rcBody: 'spring', rcLength: 0.6, rcDist: 2, env: 'none', trimCrack: -10 } }
];
var ACTION_DEFAULTS = { slowmo: 1, punch: 0, weight: 0, drive: 0, bite: 0, tail: 0, swell: 0, width: 0, loud: 0 };
var ACTION_PRESETS = [
  { id: 'none', name: 'Physics only', a: {} },
  { id: 'game', name: 'Game punch', a: { punch: 0.7, weight: 0.35, drive: 0.3, bite: 0.4, tail: 0.1, width: 0.3, loud: 0.6 } },
  { id: 'block', name: 'Blockbuster', a: { punch: 0.6, weight: 0.8, drive: 0.5, bite: 0.5, tail: 0.45, swell: 0.5, width: 0.6, loud: 0.8 } },
  { id: 'slow', name: 'Slow motion', a: { slowmo: 2.5, punch: 0.4, weight: 0.9, drive: 0.35, bite: 0.2, tail: 0.7, swell: 0.7, width: 0.7, loud: 0.6 } },
  { id: 'far', name: 'Distant battle', a: { punch: 0.1, weight: 0.5, drive: 0.15, tail: 0.6, width: 0.5, loud: 0.4 } }
];
var jobCache = { key: '', raw: null };
function job(d, post) {
  if (d.asset) { if (d.remove) removeAsset(d.id); else setAsset(d.id, d); return null; }
  if (d.fit) return fitParam(d, post);
  var t = Date.now(), k = JSON.stringify(d.p) + '|' + d.seed;
  if (d.stems) return { id: d.id, kind: 'stems', stems: renderStems(d.p, d.seed), ms: Date.now() - t };
  if (jobCache.key !== k) { jobCache.raw = renderRaw(d.p, d.seed); jobCache.key = k; }
  var fx = actionize(jobCache.raw, d.a);
  return { id: d.id, play: d.play, ms: Date.now() - t, raw: jobCache.raw, fx: fx };
}
function merge(base, over) { var o = {}, k; for (k in base) o[k] = base[k]; for (k in over) o[k] = over[k]; return o; }

root.BFX = { qrCode: qrCode, qrSvg: qrSvg, packPlan: packPlan, unpackPlan: unpackPlan, setAsset: setAsset, getAsset: getAsset, removeAsset: removeAsset, xmpText: xmpText, ixmlText: ixmlText, keywordPaths: keywordPaths, getIR: getIR, detectHits: detectHits, getHits: getHits, measureModes: measureModes, getModes: getModes,
  getGrains: getGrains, features: features, distance: distance, matchScore: matchScore, posToVal: posToVal, monoOf: monoOf, BAND_HZ: BAND_HZ, MAX_TRIGGERS: MAX_TRIGGERS, FIT_TRIES: FIT_TRIES, triggered: triggered, prepareIR: prepareIR, fftConvolve: fftConvolve, bodyIR: bodyIR, roomIR: roomIR,
  EXAMPLES: EXAMPLES, REC_MAX_S: REC_MAX_S, IR_MAX_S: IR_MAX_S, renderStems: renderStems, zipFiles: zipFiles, encodeWavFloat: encodeWavFloat, PLATES: PLATES, FF_RATIOS: FF_RATIOS, isLoop: isLoop, LOOP_S: LOOP_S, FRAG_BOOST_DB: FRAG_BOOST_DB, DEBRIS_BOOST_DB: DEBRIS_BOOST_DB, job: job, FS: FS, C: C, TRAJ_HZ: TRAJ_HZ, analyze: analyze, analyzeProj: analyzeProj, posAt: posAt, DS: DS, renderRaw: renderRaw, actionize: actionize, fft: fft,
  encodeWav: encodeWav, zipStore: zipStore, peakOf: peakOf, ENVS: ENVS, MATERIALS: MATERIALS, DEFAULTS: DEFAULTS, PRESETS: PRESETS,
  ACTION_DEFAULTS: ACTION_DEFAULTS, ACTION_PRESETS: ACTION_PRESETS, merge: merge, _wake: wakeLayer, _modal: modalHit, rng: rng };
})(typeof self !== 'undefined' ? self : globalThis);
