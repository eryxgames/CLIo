// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Daniel Sandner
/* CLIo's bridge to the sound engine of Ballistic Foley Lab (engine.js, a copy: see README.md).

   One Node process serves a whole game. A request per line on stdin, an answer per line on stdout:

     {"id": 1, "cmd": "info"}
       -> {"id": 1, "ok": true, "node": "v22.1.0", "rate": 48000, "presets": [...], "keys": [...],
         "actions": [...], "action_keys": [...]}
     {"id": 2, "cmd": "render", "preset": "pistol", "p": {"D": 0}, "action": "game", "seed": 3,
      "out": "/cache/x.wav", "gain": 0.6, "length": 2.5, "channels": 2}
       -> {"id": 2, "ok": true, "seconds": 0.82, "ms": 11.4}

   A render is a 16-bit WAV at 48 kHz: the preset's parameters, then "p" over them; then, if asked, Ballistic's
   own finishing for action ("action": one of its action presets, or an object of action parameters: punch,
   weight, loudness...); peak at "gain", cut to "length" seconds with a short fade, one or two channels.
   It is written whole beside "out" and renamed into place, so a player never meets half a file.

   An error answers {"id": n, "ok": false, "error": "..."} and the process goes on. The process ends when its
   input closes. */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const readline = require('readline');

const ENGINE = path.join(__dirname, 'engine.js');
vm.runInThisContext(fs.readFileSync(ENGINE, 'utf8'), { filename: ENGINE });
const B = globalThis.BFX;
const FS = B.FS;

function params(req) {
  let base = {};
  if (req.preset != null && req.preset !== '') {
    const pr = B.PRESETS.find((x) => x.id === req.preset);
    if (!pr) throw new Error('Ballistic has no preset called "' + req.preset + '"');
    base = pr.p;
  }
  const over = req.p && typeof req.p === 'object' ? req.p : {};
  const bad = Object.keys(over).filter((k) => !Object.prototype.hasOwnProperty.call(B.DEFAULTS, k));
  if (bad.length) throw new Error('Ballistic has no parameter' + (bad.length > 1 ? 's ' : ' ') + bad.join(', '));
  return B.merge(B.merge(B.DEFAULTS, base), over);
}

function action(req) {
  const a = req.action;
  if (a == null || a === '' || a === 'none' || a === false) return null;
  let base = {}, over = {};
  if (typeof a === 'string') {
    const pr = B.ACTION_PRESETS.find((x) => x.id === a);
    if (!pr) throw new Error('Ballistic has no action preset called "' + a + '"');
    base = pr.a;
  } else if (typeof a === 'object') {
    over = a;
    const bad = Object.keys(over).filter((k) => !Object.prototype.hasOwnProperty.call(B.ACTION_DEFAULTS, k));
    if (bad.length) throw new Error('Ballistic has no action parameter' + (bad.length > 1 ? 's ' : ' ') + bad.join(', '));
  }
  return Object.assign({}, B.ACTION_DEFAULTS, base, over);
}

function wav16(chs) {
  const n = chs[0].length, nc = chs.length, data = n * nc * 2, buf = Buffer.alloc(44 + data);
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + data, 4); buf.write('WAVE', 8);
  buf.write('fmt ', 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(nc, 22);
  buf.writeUInt32LE(FS, 24); buf.writeUInt32LE(FS * nc * 2, 28); buf.writeUInt16LE(nc * 2, 32); buf.writeUInt16LE(16, 34);
  buf.write('data', 36); buf.writeUInt32LE(data, 40);
  let o = 44;
  for (let i = 0; i < n; i++) for (let c = 0; c < nc; c++) {
    const v = chs[c][i];
    buf.writeInt16LE(Math.round((v > 1 ? 1 : v < -1 ? -1 : v) * 32767), o); o += 2;
  }
  return buf;
}

function render(req) {
  const t0 = process.hrtime.bigint();
  const a = action(req);
  let r = B.renderRaw(params(req), Math.max(1, Math.floor(+req.seed || 1)));
  if (a) r = B.actionize(r, a);
  let L = r.L, R = r.R;
  const want = Math.max(0.05, Math.min(30, +req.length || 3)), n = Math.min(L.length, Math.round(want * FS));
  if (n < L.length) {                                   // cut, with a fade over the last 40 ms
    L = L.slice(0, n); R = R.slice(0, n);
    const f = Math.min(n, Math.round(0.04 * FS));
    for (let i = 0; i < f; i++) { const g = i / f; L[n - 1 - i] *= g; R[n - 1 - i] *= g; }
  }
  let chs = [L, R];
  if (+req.channels === 1) {
    const m = new Float32Array(n);
    for (let i = 0; i < n; i++) m[i] = 0.5 * (L[i] + R[i]);
    chs = [m];
  }
  let pk = 0;
  for (const c of chs) {
    for (let i = 0; i < c.length; i++) {
      const a = Math.abs(c[i]);
      if (a !== a) throw new Error('the sound came out broken (NaN); check its parameters');
      if (a > pk) pk = a;
    }
  }
  const gain = Math.max(0, Math.min(1, req.gain == null ? 1 : +req.gain)) / (pk || 1);
  for (const c of chs) for (let i = 0; i < c.length; i++) c[i] *= gain;
  const out = String(req.out || '');
  if (!out) throw new Error('no file to write');
  const tmp = out + '.' + process.pid + '.tmp';
  fs.writeFileSync(tmp, wav16(chs));
  fs.renameSync(tmp, out);
  return { seconds: Math.round(n / FS * 1000) / 1000, ms: Math.round(Number(process.hrtime.bigint() - t0) / 1e4) / 100 };
}

function answer(req) {
  if (req.cmd === 'info') {
    return { ok: true, node: process.version, rate: FS, presets: B.PRESETS.map((p) => p.id), keys: Object.keys(B.DEFAULTS),
      actions: B.ACTION_PRESETS.map((p) => p.id), action_keys: Object.keys(B.ACTION_DEFAULTS) };
  }
  if (req.cmd === 'render') return Object.assign({ ok: true }, render(req));
  throw new Error('unknown request "' + req.cmd + '"');
}

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
rl.on('line', (line) => {
  if (!line.trim()) return;
  let req = {};
  let out;
  try { req = JSON.parse(line); out = answer(req); } catch (e) { out = { ok: false, error: String((e && e.message) || e) }; }
  out.id = req && req.id;
  process.stdout.write(JSON.stringify(out) + '\n');
});
rl.on('close', () => process.exit(0));
