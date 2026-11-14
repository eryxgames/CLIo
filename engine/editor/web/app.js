// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 Daniel Sandner
// CLIo editor. The page knows nothing about games: the server sends the files, a description of
// their fields (engine/schema.py) and the problems the engine finds; forms are built from that.
"use strict";

const KEY = new URLSearchParams(location.search).get("key") || "";
const $ = (id) => document.getElementById(id);
const state = { game: null, kind: null, id: null, dirty: new Set(), problems: [], filter: "", checking: 0, found: [], searching: 0 };

function el(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v === true) node.setAttribute(k, "");
    else if (v !== false && v !== null && v !== undefined) node.setAttribute(k, v);
  }
  node.append(...children.filter((c) => c !== null && c !== undefined && c !== false));
  return node;
}

async function api(path, body) {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: Object.assign({ "X-CLIo-Token": KEY }, body ? { "Content-Type": "application/json" } : {}),
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({ error: "The editor did not answer properly." }));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function status(text, bad) {
  $("status").textContent = text;
  $("status").classList.toggle("bad", !!bad);
}

// ---------------------------------------------------------------------- the data
const kindOf = (key) => state.game.schema.find((k) => k.key === key);
const fileOf = (kind) => state.game.files[kind.file];

function things(kind) {
  const file = fileOf(kind);
  if (!file) return [];
  if (kind.shape === "object") return [{ id: kind.one, thing: file.data }];
  if (kind.shape === "list") return file.data.map((thing, i) => ({ id: String(thing.id !== undefined ? thing.id : "#" + (i + 1)), thing }));
  return Object.entries(file.data).map(([id, thing]) => ({ id, thing }));
}

const find = (kind, id) => things(kind).find((t) => t.id === id);
const idsOf = (key) => { const k = kindOf(key); return k ? things(k).map((t) => t.id) : []; };
const titleOf = (kind, t) => (kind.title && t.thing && typeof t.thing[kind.title] === "string" && t.thing[kind.title]) || t.id;

function touched(kind) {
  state.dirty.add(kind.file);
  renderBar();
  renderKinds();
  clearTimeout(state.checking);
  state.checking = setTimeout(check, 500);
}

// the changed files as they are now in the page, for anything the server should look at before saving
function pending() {
  const out = {};
  for (const key of state.dirty) out[key] = state.game.files[key].data;
  return out;
}

async function check() {
  try {
    state.problems = (await api("/api/check", { pending: pending() })).problems;
    renderProblems();
    renderKinds();
    renderList();
  } catch (err) {
    status("Could not check the game: " + err.message, true);
  }
}

async function saveAll() {
  const saved = [];
  $("save").disabled = true;
  try {
    for (const key of [...state.dirty]) {
      const out = await api("/api/save", { file: key, data: state.game.files[key].data });
      state.game.files[key].exists = true;
      state.dirty.delete(key);
      state.problems = out.problems;
      saved.push(out.saved);
    }
    status("Saved " + saved.join(", ") + ".");
  } catch (err) {
    status("Could not save: " + err.message, true);
  }
  renderAll();
}

// Every place in the game where a string is exactly this id. Prose (names, descriptions) is not searched:
// an item called "lamp" may well be named "lamp" too, and that is not a reference.
function uses(id) {
  const found = [];
  const walk = (value, path, set) => {
    if (typeof value === "string") { if (value === id) found.push({ path, set }); return; }
    if (Array.isArray(value)) value.forEach((v, i) => walk(v, path, (nv) => { value[i] = nv; }));
    else if (value && typeof value === "object") {
      for (const [k, v] of Object.entries(value)) walk(v, path.concat(k), (nv) => { value[k] = nv; });
    }
  };
  for (const kind of state.game.schema) {
    const prose = new Set(kind.fields.filter((f) => f.type === "text" || f.type === "long").map((f) => f.key));
    for (const t of things(kind)) {
      for (const [k, v] of Object.entries(t.thing || {})) {
        if ((kind.shape === "list" && k === "id") || prose.has(k)) continue;
        walk(v, [kind, t.id, k], (nv) => { t.thing[k] = nv; });
      }
    }
  }
  return found;
}

// ---------------------------------------------------------------------- drawing
function renderAll() { renderBar(); renderKinds(); renderList(); renderForm(); renderProblems(); }

function renderBar() {
  const n = state.dirty.size;
  $("save").disabled = n === 0;
  $("save").textContent = n === 0 ? "Saved" : n === 1 ? "Save 1 file" : `Save ${n} files`;
  document.title = (n ? "* " : "") + state.game.title + " - CLIo editor";
}

function renderProblems() {
  const n = state.problems.length;
  const toggle = $("problems-toggle");
  toggle.hidden = n === 0;
  toggle.textContent = n === 1 ? "1 problem" : `${n} problems`;
  if (n === 0) $("problems").hidden = true;
  $("problem-list").replaceChildren(...state.problems.map((p) => el("li", {},
    el("button", { type: "button", onclick: () => { if (p.kind) select(p.kind, p.id || (kindOf(p.kind).shape === "object" ? kindOf(p.kind).one : null)); } }, p.text))));
}

function renderKinds() {
  $("kinds").replaceChildren(...state.game.schema.filter((k) => state.game.files[k.file]).map((kind) => {
    const count = kind.shape === "object" ? "" : String(things(kind).length);
    const bad = state.problems.some((p) => p.kind === kind.key);
    return el("button", { type: "button", "aria-current": state.kind === kind.key ? "true" : null,
      class: count === "0" ? "none" : "", onclick: () => select(kind.key, kind.shape === "object" ? kind.one : null) },
      el("span", {}, kind.label, state.dirty.has(kind.file) ? el("span", { class: "dot", title: "Changed, not saved" }, " •") : null,
        bad ? el("span", { class: "flag", title: "Has problems" }, " !") : null),
      el("span", { class: "count" }, count));
  }));
}

function renderList() {
  const kind = state.kind && kindOf(state.kind);
  const single = !kind || kind.shape === "object";
  $("filter").hidden = single;
  $("add").hidden = single;
  $("workshop").hidden = !kind || kind.key !== "characters";
  if (!kind) { $("things").replaceChildren(); return; }
  if (!single) $("add-id").placeholder = `id for a new ${kind.one}`;
  const q = state.filter.trim().toLowerCase();
  const rows = things(kind).filter((t) => !q || t.id.toLowerCase().includes(q) || titleOf(kind, t).toLowerCase().includes(q));
  $("things").replaceChildren(...rows.map((t) => {
    const bad = state.problems.some((p) => p.kind === kind.key && p.id === t.id);
    const title = titleOf(kind, t);
    return el("li", {}, el("button", { type: "button", "aria-current": state.id === t.id ? "true" : null, onclick: () => select(kind.key, t.id) },
      el("span", { class: "name" }, title, bad ? el("span", { class: "flag", title: "Has a problem" }, " !") : null),
      title !== t.id ? el("span", { class: "id" }, t.id) : null));
  }));
}

function select(kindKey, id) {
  state.kind = kindKey;
  state.id = id;
  state.workshop = null;
  if (kindOf(kindKey).shape !== "object" && id === null) state.filter = $("filter").value = "";
  renderKinds(); renderList(); renderForm();
}

function field(label, control, note) {
  const id = "f-" + Math.random().toString(36).slice(2, 9);
  if (control.tagName === "INPUT" || control.tagName === "SELECT" || control.tagName === "TEXTAREA") control.id = id;
  return el("div", { class: "field" }, el("label", { for: control.id || null }, label), control, note || null);
}

// A form control is only offered for a value of the kind it expects; anything else stays in the JSON below.
function fits(f, value) {
  if (value === undefined) return true;
  if (f.type === "number") return typeof value === "number";
  if (f.type === "bool") return typeof value === "boolean";
  if (f.type === "tags" || f.type === "refs") return Array.isArray(value) && value.every((v) => typeof v === "string");
  if (f.type === "sprite") return typeof value === "string";
  return typeof value === "string";
}

function put(thing, key, value) {
  if (value === "" || value === null || value === undefined || (Array.isArray(value) && value.length === 0)) delete thing[key];
  else thing[key] = value;
}

function control(kind, f, thing) {
  const change = (value) => { put(thing, f.key, value); touched(kind); renderList(); };
  const value = thing[f.key];
  if (f.type === "bool") {
    return el("input", { type: "checkbox", checked: value === true, onchange: (e) => {
      if (e.target.checked) thing[f.key] = true; else if (f.key in thing) thing[f.key] = false;
      touched(kind);
    } });
  }
  if (f.type === "number") {
    return el("input", { type: "number", step: "any", value: typeof value === "number" ? String(value) : "",
      oninput: (e) => change(e.target.value === "" ? "" : Number(e.target.value)) });
  }
  if (f.type === "long") {
    const area = el("textarea", { rows: "4", oninput: (e) => change(e.target.value) });
    area.value = typeof value === "string" ? value : "";
    return area;
  }
  if (f.type === "tags") {
    return el("input", { type: "text", class: "code", value: Array.isArray(value) ? value.join(", ") : "", placeholder: "words, separated by commas",
      oninput: (e) => change(e.target.value.split(",").map((s) => s.trim()).filter(Boolean)) });
  }
  if (f.type === "choice" || f.type === "ref") {
    const options = f.type === "choice" ? f.options : idsOf(f.of);
    const known = value === undefined || value === "" || options.includes(value);
    return el("select", { onchange: (e) => change(e.target.value) },
      el("option", { value: "", selected: value === undefined || value === "" }, "-"),
      ...options.map((o) => el("option", { value: o, selected: o === value }, o)),
      known ? null : el("option", { value: String(value), selected: true }, `${value} (not found)`));
  }
  if (f.type === "sprite") return spriteField(kind, f, thing, change);
  if (f.type === "refs") {
    const list = Array.isArray(value) ? value : [];
    const all = idsOf(f.of);
    const box = el("div", { class: "chips" });
    list.forEach((id, i) => box.append(el("span", { class: "chip" + (all.includes(id) ? "" : " missing"), title: all.includes(id) ? "" : "Not found" }, String(id),
      el("button", { type: "button", "aria-label": `Remove ${id}`, onclick: () => { const next = list.slice(); next.splice(i, 1); change(next); renderForm(); } }, "×"))));
    box.append(el("select", { "aria-label": `Add to ${f.label}`, onchange: (e) => { if (e.target.value) { change(list.concat(e.target.value)); renderForm(); } } },
      el("option", { value: "" }, "add…"), ...all.filter((o) => !list.includes(o)).map((o) => el("option", { value: o }, o))));
    return box;
  }
  return el("input", { type: "text", value: typeof value === "string" ? value : "",
    oninput: (e) => change(e.target.value) });
}

function renderForm() {
  const host = $("form");
  if (state.workshop) return renderWorkshop(host);
  const kind = state.kind && kindOf(state.kind);
  const hit = kind && state.id !== null ? find(kind, state.id) : null;
  if (!hit) {
    host.replaceChildren(el("p", { class: "empty" }, !kind ? "Choose something on the left to edit it."
      : things(kind).length ? `Choose a ${kind.one} in the list, or add a new one below it.`
        : `This game has no ${kind.label.toLowerCase()} yet. Type an id below the list and press Add.`));
    return;
  }
  const { thing } = hit;
  const single = kind.shape === "object";
  const fields = kind.fields.filter((f) => fits(f, thing[f.key]));
  const drawn = kind.editor === "sprite" && (thing.pixels === undefined || (Array.isArray(thing.pixels) && thing.pixels.every((r) => typeof r === "string")))
    && (thing.palette === undefined || (thing.palette && typeof thing.palette === "object" && !Array.isArray(thing.palette)));
  const known = new Set(fields.map((f) => f.key).concat(kind.shape === "list" ? ["id"] : [], drawn ? ["palette", "pixels"] : []));
  const parts = [];

  const head = el("div", { class: "head" }, el("h2", {}, single ? kind.label : titleOf(kind, hit)));
  if (!single) {
    head.append(
      el("button", { type: "button", class: "quiet", onclick: () => duplicate(kind, hit) }, "Duplicate"),
      el("button", { type: "button", class: "quiet warn", onclick: () => remove(kind, hit) }, "Delete"));
  }
  parts.push(head);
  if (kind.key === "characters" && thing.stats && typeof thing.stats === "object") {
    head.insertBefore(el("button", { type: "button", class: "quiet", onclick: (e) => {
      e.target.disabled = true;
      head.after(fightSheet(() => ({ enemies: [hit.id] }), `How a fight with ${titleOf(kind, hit)} goes`));
    } }, "Try in a fight"), head.children[1]);
  }

  if (!single) {
    const note = el("p", { class: "note" }, "The name the game's files use for this. Changing it does not change what refers to it; see the list at the bottom.");
    const input = el("input", { type: "text", class: "code", value: hit.id, spellcheck: "false", onchange: (e) => {
      const problem = rename(kind, hit, e.target.value.trim());
      if (problem) { note.textContent = problem; note.classList.add("bad"); e.target.value = hit.id; }
    } });
    parts.push(field("Id", input, note));
  }
  for (const f of fields) parts.push(field(f.label, control(kind, f, thing)));
  if (drawn) parts.push(spriteEditor(kind, thing));

  // everything the schema does not describe is still here, as JSON
  const rest = {};
  for (const [k, v] of Object.entries(thing)) if (!known.has(k)) rest[k] = v;
  const note = el("p", { class: "note" }, kind.fields.length || drawn ? "Fields without a form of their own yet, as JSON. They are kept exactly as written."
    : "This kind has no form yet: edit it as JSON.");
  const area = el("textarea", { class: "code", spellcheck: "false", rows: String(Math.min(28, Math.max(6, JSON.stringify(rest, null, 2).split("\n").length + 1))),
    oninput: (e) => {
      let parsed;
      try { parsed = JSON.parse(e.target.value || "{}"); } catch (err) { note.textContent = "Not valid JSON yet: " + err.message; note.classList.add("bad"); return; }
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) { note.textContent = "This must be a JSON object: { … }"; note.classList.add("bad"); return; }
      const clash = Object.keys(parsed).find((k) => known.has(k));
      if (clash) { note.textContent = `"${clash}" has its own field above.`; note.classList.add("bad"); return; }
      note.textContent = "Fields without a form of their own yet, as JSON."; note.classList.remove("bad");
      for (const k of Object.keys(thing)) if (!known.has(k) && !(k in parsed)) delete thing[k];      // keep the order the file had
      for (const [k, v] of Object.entries(parsed)) thing[k] = v;
      touched(kind);
    } });
  area.value = JSON.stringify(rest, null, 2);
  parts.push(field(kind.fields.length || drawn ? "Everything else" : "Content", area, note));

  if (!single) {
    const places = uses(hit.id);
    const box = el("div", { class: "used" }, el("h3", {}, places.length ? `Used in ${places.length} place${places.length === 1 ? "" : "s"}` : "Not used anywhere"));
    if (places.length) {
      box.append(el("ul", {}, ...places.slice(0, 40).map((p) => el("li", {},
        el("button", { type: "button", class: "link", onclick: () => select(p.path[0].key, p.path[1]) }, `${p.path[0].label} › ${p.path[1]}`),
        " › " + p.path.slice(2).join(" › ")))));
      if (places.length > 40) box.append(el("p", { class: "note" }, `…and ${places.length - 40} more.`));
    }
    parts.push(box);
  }
  host.replaceChildren(...parts);
}

// ---------------------------------------------------------------------- pixel sprites
const LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
const CLEAR = ".";

// Colours of a palette as #rrggbb. Hex is read here; names and numbers are the engine's to translate.
async function coloursOf(palette) {
  const out = {};
  const ask = {};
  for (const [k, v] of Object.entries(palette || {})) {
    if (typeof v === "string" && /^#[0-9a-f]{6}$/i.test(v.trim())) out[k] = v.trim().toLowerCase();
    else ask[k] = v;
  }
  if (Object.keys(ask).length) {
    try { Object.assign(out, (await api("/api/sprite", { palette: ask })).colours); } catch (err) { /* drawn without those colours */ }
  }
  return out;
}

function paintSprite(canvas, pixels, colours, cell, screen) {
  const h = pixels.length, w = Math.max(1, ...pixels.map((r) => r.length));
  canvas.width = w * cell;
  canvas.height = h * cell;
  const c = canvas.getContext("2d");
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const colour = colours[pixels[y][x]];
      if (colour) c.fillStyle = colour;
      else if (screen) c.fillStyle = screen;
      else c.fillStyle = (x + y) % 2 ? "#c9ced6" : "#e7eaee";                  // nothing there: a checkerboard
      c.fillRect(x * cell, y * cell, cell, cell);
    }
  }
}

// The sprite a character will be drawn with: its own from sprites.json, or the one the game grows from its name.
function spriteField(kind, f, thing, change) {
  const input = el("input", { type: "text", class: "code", value: thing[f.key] || "", placeholder: "auto, none, or the name of a sprite",
    oninput: (e) => { change(e.target.value.trim()); show(); } });
  const canvas = el("canvas", { class: "sprite-small", "aria-hidden": "true" });
  const buttons = el("span", { class: "row" });
  const note = el("p", { class: "note" });
  const sprites = kindOf("sprites");
  const me = () => (state.id !== null ? state.id : "");
  const seed = () => thing.sprite_seed || thing.template || thing.name || me();

  async function show() {
    const ref = thing[f.key];
    const own = ref && sprites && fileOf(sprites) && fileOf(sprites).data[ref];
    buttons.replaceChildren();
    canvas.hidden = false;
    if (!ref || ref === "none") {
      canvas.hidden = true;
      note.textContent = ref === "none" ? "No picture in a fight." : "No sprite named: the game shows none unless this says auto.";
      buttons.append(el("button", { type: "button", class: "quiet", onclick: () => { input.value = "auto"; change("auto"); show(); } }, "Grow one"));
      return;
    }
    if (own && Array.isArray(own.pixels)) {
      paintSprite(canvas, own.pixels, await coloursOf(own.palette), 5, "#0f1724");
      note.textContent = "Drawn by hand, in the game's sprites.";
      buttons.append(el("button", { type: "button", class: "quiet", onclick: () => select("sprites", ref) }, "Edit the drawing"));
      return;
    }
    let grown;
    try { grown = await api("/api/sprite", { seed: seed(), size: thing.sprite_size || 12 }); } catch (err) { note.textContent = err.message; return; }
    paintSprite(canvas, grown.pixels, grown.palette, 5, "#0f1724");
    note.textContent = ref === "auto" ? `Grown by the game from "${seed()}". The same words always grow the same creature.`
      : `There is no sprite called "${ref}", so the game grows one from "${seed()}".`;
    buttons.append(
      el("button", { type: "button", class: "quiet", title: "Grow a different creature", onclick: () => {
        thing.sprite_seed = `${thing.name || me()} ${Math.random().toString(36).slice(2, 6)}`;
        touched(kind);
        renderForm();
      } }, "Another one"),
      el("button", { type: "button", class: "quiet", title: "Keep this creature as a drawing you can change", onclick: () => {
        let id = me() || "sprite", n = 2;
        while (fileOf(sprites).data[id]) { id = `${me()}_${n}`; n += 1; }
        fileOf(sprites).data[id] = grown;
        thing[f.key] = id;
        delete thing.sprite_seed;
        touched(sprites);
        touched(kind);
        select("sprites", id);
        status(`The creature is now the drawing "${id}", and ${thing.name || "the character"} uses it. Nothing is written until you save.`);
      } }, "Draw over it"));
  }
  show();
  return el("div", {}, input, el("div", { class: "sprite-row" }, canvas, el("div", {}, note, buttons)));
}

// Drawing a sprite: a grid of palette letters, painted with the mouse (or the arrow keys and Space).
function spriteEditor(kind, thing) {
  if (!Array.isArray(thing.pixels)) thing.pixels = Array(12).fill(CLEAR.repeat(12));
  if (!thing.palette || typeof thing.palette !== "object") thing.palette = {};
  let colours = {};
  let pen = Object.keys(thing.palette)[0] || CLEAR;
  let mirror = true, cursor = [0, 0], painting = false;
  const cell = () => Math.max(8, Math.min(26, Math.floor(416 / Math.max(width(), thing.pixels.length))));
  const width = () => Math.max(1, ...thing.pixels.map((r) => r.length));
  const grid = el("canvas", { class: "sprite-grid", tabindex: "0", role: "img", "aria-label": "The sprite. Arrow keys move, Space paints." });
  const small = el("canvas", { class: "sprite-small", "aria-hidden": "true" });
  const swatches = el("div", { class: "swatches" });
  const picker = el("input", { type: "color", "aria-label": "Colour of the chosen paint" });
  const size = el("span", { class: "row" });

  function even() {                                          // every row the same length
    const w = width();
    thing.pixels = thing.pixels.map((r) => r.padEnd(w, CLEAR));
  }
  function draw() {
    paintSprite(grid, thing.pixels, colours, cell());
    const c = grid.getContext("2d");
    c.strokeStyle = "rgba(0,0,0,0.12)";
    for (let x = 0; x <= width(); x++) { c.beginPath(); c.moveTo(x * cell() + 0.5, 0); c.lineTo(x * cell() + 0.5, grid.height); c.stroke(); }
    for (let y = 0; y <= thing.pixels.length; y++) { c.beginPath(); c.moveTo(0, y * cell() + 0.5); c.lineTo(grid.width, y * cell() + 0.5); c.stroke(); }
    if (document.activeElement === grid) { c.strokeStyle = "#2447d6"; c.lineWidth = 2; c.strokeRect(cursor[0] * cell() + 1, cursor[1] * cell() + 1, cell() - 2, cell() - 2); c.lineWidth = 1; }
    paintSprite(small, thing.pixels, colours, 4, "#0f1724");
  }
  function set(x, y, letter) {
    const put = (cx) => { if (cx >= 0 && cx < width() && y >= 0 && y < thing.pixels.length) thing.pixels[y] = thing.pixels[y].slice(0, cx) + letter + thing.pixels[y].slice(cx + 1); };
    put(x);
    if (mirror) put(width() - 1 - x);
    touched(kind);
    palette();                                              // which colours are in use may have changed
    draw();
  }
  function palette() {
    const used = new Set(thing.pixels.join(""));
    swatches.replaceChildren(
      el("button", { type: "button", class: "swatch clear" + (pen === CLEAR ? " on" : ""), title: "Nothing (rub out)", "aria-label": "Rub out", onclick: () => { pen = CLEAR; palette(); } }),
      ...Object.keys(thing.palette).map((k) => el("button", { type: "button", class: "swatch" + (pen === k ? " on" : ""), style: `background:${colours[k] || "transparent"}`,
        title: `Paint "${k}"${used.has(k) ? "" : " (not used)"}`, "aria-label": `Paint ${k}`, onclick: () => { pen = k; palette(); } })),
      el("button", { type: "button", class: "quiet", onclick: () => {
        const k = [...LETTERS].find((l) => !(l in thing.palette));
        if (!k) return;
        thing.palette[k] = colours[k] = "#8a96a8";
        pen = k;
        touched(kind); palette(); draw();
      } }, "Add a colour"));
    const mine = pen !== CLEAR;
    picker.hidden = !mine;
    if (mine) picker.value = colours[pen] || "#000000";
    if (mine && !used.has(pen)) swatches.append(el("button", { type: "button", class: "quiet", onclick: () => { delete thing.palette[pen]; delete colours[pen]; pen = CLEAR; touched(kind); palette(); } }, "Remove this colour"));
  }
  function resize(w, h) {
    w = Math.max(4, Math.min(32, w)); h = Math.max(4, Math.min(32, h));
    const now = width(), left = Math.floor((w - now) / 2);        // grow and shrink evenly on both sides, so it stays centred
    thing.pixels = thing.pixels.map((r) => (left >= 0 ? CLEAR.repeat(left) + r : r.slice(-left)).padEnd(w, CLEAR).slice(0, w));
    while (thing.pixels.length < h) thing.pixels.push(CLEAR.repeat(w));
    thing.pixels.length = h;
    touched(kind); sizes(); draw();
  }
  function sizes() {
    size.replaceChildren("Width", el("input", { type: "number", min: "4", max: "32", value: String(width()), onchange: (e) => resize(Number(e.target.value) || width(), thing.pixels.length) }),
      "Height", el("input", { type: "number", min: "4", max: "32", value: String(thing.pixels.length), onchange: (e) => resize(width(), Number(e.target.value) || thing.pixels.length) }));
  }
  const at = (e) => { const box = grid.getBoundingClientRect(); return [Math.floor((e.clientX - box.left) / (box.width / width())), Math.floor((e.clientY - box.top) / (box.height / thing.pixels.length))]; };
  grid.addEventListener("pointerdown", (e) => { painting = true; grid.setPointerCapture(e.pointerId); cursor = at(e); set(cursor[0], cursor[1], e.button === 2 ? CLEAR : pen); });
  grid.addEventListener("pointermove", (e) => { if (painting) { cursor = at(e); set(cursor[0], cursor[1], e.buttons === 2 ? CLEAR : pen); } });
  grid.addEventListener("pointerup", () => { painting = false; });
  grid.addEventListener("contextmenu", (e) => e.preventDefault());
  grid.addEventListener("focus", draw);
  grid.addEventListener("blur", draw);
  grid.addEventListener("keydown", (e) => {
    const step = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (step) { cursor = [Math.max(0, Math.min(width() - 1, cursor[0] + step[0])), Math.max(0, Math.min(thing.pixels.length - 1, cursor[1] + step[1]))]; draw(); e.preventDefault(); }
    else if (e.key === " " || e.key === "Enter") { set(cursor[0], cursor[1], pen); e.preventDefault(); }
    else if (e.key === "Backspace" || e.key === "Delete") { set(cursor[0], cursor[1], CLEAR); e.preventDefault(); }
  });
  picker.addEventListener("input", () => { if (pen !== CLEAR) { thing.palette[pen] = colours[pen] = picker.value; touched(kind); palette(); draw(); } });

  const seed = el("input", { type: "text", placeholder: "any words", value: state.id || "", "aria-label": "Words to grow a creature from" });
  const grow = el("button", { type: "button", class: "quiet", onclick: async () => {
    if (thing.pixels.join("").replace(/\./g, "") && !confirm("Replace this drawing with a grown one?")) return;
    try {
      const made = await api("/api/sprite", { seed: seed.value || "nobody", size: thing.pixels.length });
      thing.palette = made.palette; thing.pixels = made.pixels; colours = Object.assign({}, made.palette);
      pen = Object.keys(thing.palette)[0] || CLEAR;
      touched(kind); sizes(); palette(); draw();
    } catch (err) { status("Could not grow a sprite: " + err.message, true); }
  } }, "Grow");
  const tick = el("input", { type: "checkbox", checked: true, onchange: (e) => { mirror = e.target.checked; } });

  even();
  coloursOf(thing.palette).then((c) => { colours = c; palette(); draw(); });
  sizes();
  return el("div", { class: "sheet sprite" },
    el("div", { class: "sprite-row" }, grid, el("div", {},
      el("h3", {}, "Paint"), swatches, el("div", { class: "row" }, picker, el("label", { class: "tick" }, tick, " Mirror left and right")),
      el("h3", {}, "Size"), size,
      el("h3", {}, "In the game"), small,
      el("h3", {}, "Grow one from words"), el("div", { class: "row" }, seed, grow))),
    el("p", { class: "note" }, "Click or drag to paint, right button to rub out. With the keyboard: arrow keys move, Space paints, Delete rubs out. " +
      "The game draws two pixel rows in one line of text, so pixels come out about square."));
}

// ---------------------------------------------------------------------- enemies: make one, try one
const pct = (x) => Math.round(100 * x) + "%";

// A box that runs fights on the server (the engine's own battle code) and shows how they went.
function fightSheet(what, title) {
  const level = el("input", { type: "number", min: "1", max: "60", value: "1", "aria-label": "Player level" });
  const count = el("select", { "aria-label": "How many of them" },
    el("option", { value: "1" }, "one of them"), el("option", { value: "2" }, "two of them"), el("option", { value: "3" }, "three of them"));
  const out = el("div", {});
  const go = el("button", { type: "button", class: "quiet", onclick: async () => {
    const ask = what();
    if (!ask) return;
    go.disabled = true;
    out.replaceChildren(el("p", { class: "note" }, "Fighting…"));
    try {
      const enemies = Array(Number(count.value)).fill(ask.enemies[0]);
      const res = await api("/api/odds", { pending: pending(), enemies, extra: ask.extra, level: Number(level.value) || 1, fights: 40 });
      out.replaceChildren(el("table", {},
        el("thead", {}, el("tr", {}, el("th", {}, "Player"), el("th", {}, "Wins"), el("th", {}, "Health left after a win"), el("th", {}, "Turns"))),
        el("tbody", {}, ...res.rows.map((r) => el("tr", {}, el("td", {}, r.name), el("td", {}, pct(r.wins)),
          el("td", {}, r.health_left === null ? "-" : pct(r.health_left)), el("td", {}, String(r.turns)))))),
      el("p", { class: "note" }, `${res.fights} fights each at level ${res.level}, with the equipment a new character starts with, by a player who fights sensibly ` +
        "and without flair. Good for comparing enemies; a person will do better or worse." +
        (res.rows.some((r) => r.undecided) ? " Some fights did not end and count as not won." : "")));
    } catch (err) {
      out.replaceChildren(el("p", { class: "note bad" }, err.message));
    }
    go.disabled = false;
  } }, "Fight");
  return el("div", { class: "sheet" }, el("h3", {}, title),
    el("div", { class: "row" }, "A player at level", level, "against", count, go), out);
}

function renderWorkshop(host) {
  const w = state.workshop;
  const preview = el("div", { class: "sheet" }, el("p", { class: "note" }, "Working it out…"));
  const like = el("select", {}), floor = el("select", {}), rank = el("select", {});
  const lean = el("input", { type: "range", min: "-1", max: "1", step: "0.25", value: String(w.lean) });
  const name = el("input", { type: "text", value: w.name, placeholder: "a name for it" });
  const addButton = el("button", { type: "button", class: "go", disabled: true, onclick: () => {
    if (!w.result) return;
    const made = w.result;
    add(kindOf("characters"), made.id, made.enemy);
    status(`${made.enemy.name} was added to the characters as ${made.id}. Nothing is written until you save.`);
  } }, "Add to the characters");
  let timer = 0, filled = false;

  async function work() {
    try {
      const res = await api("/api/enemy", { pending: pending(), like: w.like, floor: w.floor, rank: w.rank, lean: w.lean, name: w.name });
      if (state.workshop !== w) return;
      w.result = res;
      if (!filled) {                                        // the choices come from the game itself, once
        filled = true;
        like.replaceChildren(el("option", { value: "" }, "a plain enemy"), ...res.like.map((c) => el("option", { value: c.id, selected: c.id === w.like }, `${c.name} (${c.id})`)));
        floor.replaceChildren(...res.floors.map((f) => el("option", { value: String(f.n), selected: f.n === res.floor.n },
          f.n ? `floor ${f.n}, ${f.name} (strength ${f.power})` : `${f.name} (strength ${f.power})`)));
        rank.replaceChildren(...res.ranks.map((r) => el("option", { value: r, selected: r === w.rank }, r)));
      }
      const st = res.enemy.stats;
      const gold = Array.isArray(res.enemy.gold) ? res.enemy.gold.join(" to ") : String(res.enemy.gold);
      preview.replaceChildren(el("h3", {}, `${res.enemy.name} `, el("span", { class: "id" }, res.id)),
        el("dl", {}, ...[["Health", st.max_health], ["Attack", st.attack], ["Defence", st.defense], ["Experience", res.enemy.xp], ["Gold", gold],
          ["Strength", `${res.power} (aimed at ${res.target})`]].flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, String(v))])),
        el("p", { class: "note" }, "Its moves" + (w.like ? ", looks and tags are those of the one it started from" : " are a blow and a heavy blow with a warning") +
          ". Everything can be changed once it is added."));
      addButton.disabled = false;
    } catch (err) {
      preview.replaceChildren(el("p", { class: "note bad" }, err.message));
      addButton.disabled = true;
    }
  }
  const again = () => { clearTimeout(timer); timer = setTimeout(work, 150); };
  like.addEventListener("change", () => { w.like = like.value; again(); });
  floor.addEventListener("change", () => { w.floor = Number(floor.value); again(); });
  rank.addEventListener("change", () => { w.rank = rank.value; again(); });
  lean.addEventListener("input", () => { w.lean = Number(lean.value); again(); });
  name.addEventListener("input", () => { w.name = name.value; again(); });

  host.replaceChildren(
    el("div", { class: "head" }, el("h2", {}, "Make an enemy")),
    el("p", { class: "lead" }, "A new enemy of a strength you choose, on the same curve as the ones the game spawns: strength is health times hitting power, " +
      "the measure the dungeon generator uses. Nothing is added until you say so."),
    field("Start from", like), field("As strong as", floor), field("Rank", rank, el("p", { class: "note" }, "Against that floor's average monster: a minion is 0.6 of it, an elite 2.2, a boss 4.")),
    field("Build", el("div", {}, lean, el("div", { class: "ends" }, el("span", {}, "tough"), el("span", {}, "sharp"))),
      el("p", { class: "note" }, "The same strength as more health and softer hits, or less health and harder ones.")),
    field("Name", name), preview,
    fightSheet(() => (w.result ? { enemies: [w.result.id], extra: { [w.result.id]: w.result.enemy } } : null), "Try it before adding it"),
    addButton);
  work();
}

// ---------------------------------------------------------------------- changing the set of things
const validId = (id) => /^[A-Za-z0-9_.-]+$/.test(id);

function rename(kind, hit, next) {
  if (next === hit.id) return "";
  if (!validId(next)) return "An id is letters, digits, _ . and - without spaces.";
  if (find(kind, next)) return `There is already a ${kind.one} called ${next}.`;
  const old = hit.id;
  const file = fileOf(kind);
  if (kind.shape === "list") hit.thing.id = next;
  else file.data = Object.fromEntries(Object.entries(file.data).map(([k, v]) => [k === old ? next : k, v]));
  const places = uses(old);
  if (places.length && confirm(`${places.length} place${places.length === 1 ? " still says" : "s still say"} "${old}". Change ${places.length === 1 ? "it" : "them"} to "${next}" too?`)) {
    const changed = new Set();
    for (const p of places) { p.set(next); changed.add(p.path[0]); }
    for (const k of changed) state.dirty.add(k.file);
  }
  state.id = next;
  touched(kind);
  renderList(); renderForm();
  return "";
}

function add(kind, id, thing) {
  const file = fileOf(kind);
  if (kind.shape === "list") file.data.push(Object.assign({ id }, thing));
  else file.data[id] = thing;
  touched(kind);
  select(kind.key, id);
}

function duplicate(kind, hit) {
  let n = 2;
  while (find(kind, `${hit.id}_${n}`)) n += 1;
  const copy = JSON.parse(JSON.stringify(hit.thing));
  delete copy.id;
  add(kind, `${hit.id}_${n}`, copy);
}

function remove(kind, hit) {
  const places = uses(hit.id).length;
  if (!confirm(`Delete the ${kind.one} "${hit.id}"?` + (places ? ` It is still used in ${places} place${places === 1 ? "" : "s"}; the engine will report those.` : ""))) return;
  const file = fileOf(kind);
  if (kind.shape === "list") file.data.splice(file.data.indexOf(hit.thing), 1);
  else delete file.data[hit.id];
  touched(kind);
  select(kind.key, null);
}

// ---------------------------------------------------------------------- all the text at once
function download(name, blob) {
  const link = el("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 5000);
}

// Texts that came back changed (from a file, or from replacing): take them into the page, unsaved.
function adopt(result) {
  for (const [key, data] of Object.entries(result.files)) {
    state.game.files[key].data = data;
    state.dirty.add(key);
  }
  renderAll();
  clearTimeout(state.checking);
  state.checking = setTimeout(check, 100);
}

const escaped = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const needle = () => new RegExp(escaped($("find").value), $("match-case").checked ? "g" : "gi");
const place = (row) => { const kind = kindOf(row.kind); return [kind.label, row.id].filter(Boolean).join(" › ") + " › " + row.where.split("/").slice(row.id ? 2 : 1).join(" › "); };

async function search() {
  const query = $("find").value;
  if (!query) { state.found = []; $("found").hidden = true; $("replace-all").disabled = true; return; }
  let rows;
  try { rows = (await api("/api/texts", { pending: pending() })).rows; } catch (err) { return status("Could not search: " + err.message, true); }
  if (query !== $("find").value) return;                   // typed on since
  const find = needle();
  state.found = rows.filter((r) => { find.lastIndex = 0; return find.test(r.text); });
  const times = state.found.reduce((n, r) => n + (r.text.match(needle()) || []).length, 0);
  $("found").hidden = false;
  $("replace-all").disabled = state.found.length === 0;
  $("found-count").textContent = state.found.length === 0 ? `Nothing the player reads contains "${query}".`
    : `"${query}" appears ${times === 1 ? "once" : times + " times"} in ${state.found.length} text${state.found.length === 1 ? "" : "s"}.` +
      (state.found.length > 200 ? " The first 200 are listed." : "");
  $("found-list").replaceChildren(...state.found.slice(0, 200).map((r) => {
    find.lastIndex = 0;
    const at = find.exec(r.text);
    const from = Math.max(0, at.index - 40);
    const snippet = el("span", { class: "snippet" }, (from ? "…" : "") + r.text.slice(from, at.index),
      el("mark", {}, at[0]), r.text.slice(at.index + at[0].length, at.index + at[0].length + 90));
    return el("li", {}, el("button", { type: "button", onclick: () => select(r.kind, r.id || kindOf(r.kind).one) },
      el("span", { class: "id" }, place(r)), snippet));
  }));
}

async function replaceAll() {
  const query = $("find").value, by = $("replace").value;
  if (!query || !state.found.length) return;
  const rows = state.found.map((r) => ({ where: r.where, text: r.text.replace(needle(), () => by) }));
  try {
    const result = await api("/api/texts/apply", { pending: pending(), rows });
    adopt(result);
    status(`Replaced in ${result.report.changed} text${result.report.changed === 1 ? "" : "s"}. Nothing is written until you save.`);
    search();
  } catch (err) {
    status("Could not replace: " + err.message, true);
  }
}

async function exportText() {
  try {
    const out = await api("/api/texts", { pending: pending(), csv: true });
    download(state.game.id + "-texts.csv", new Blob(["\ufeff" + out.csv], { type: "text/csv;charset=utf-8" }));
    status(`${out.count} texts exported. Edit the second column; keep the first as it is.`);
  } catch (err) {
    status("Could not export: " + err.message, true);
  }
}

async function importText(file) {
  try {
    const result = await api("/api/texts/apply", { pending: pending(), csv: await file.text() });
    const r = result.report;
    adopt(result);
    status(`${r.changed} text${r.changed === 1 ? "" : "s"} changed in ${r.files.length} file${r.files.length === 1 ? "" : "s"}, ${r.same} the same` +
      (r.missing.length ? `, ${r.missing.length} row${r.missing.length === 1 ? "" : "s"} matched nothing (listed below)` : "") + ". Nothing is written until you save.",
    r.missing.length > 0);
    $("found").hidden = r.missing.length === 0;
    if (r.missing.length) {
      $("found-count").textContent = "These places in the file are not in the game (any more), so their texts were left out:";
      $("found-list").replaceChildren(...r.missing.slice(0, 200).map((w) => el("li", {}, el("span", { class: "id" }, w))));
    }
  } catch (err) {
    status("Could not import: " + err.message, true);
  }
}

async function downloadGame() {
  if (state.dirty.size) return status("Save first, so that the archive has your changes.", true);
  try {
    const res = await fetch("/api/archive", { method: "POST", headers: { "X-CLIo-Token": KEY, "Content-Type": "application/json" }, body: "{}" });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
    download(state.game.id + ".zip", await res.blob());
    status("The game folder was downloaded as " + state.game.id + ".zip.");
  } catch (err) {
    status("Could not download: " + err.message, true);
  }
}

const THEMES = { system: "Theme: as the system", light: "Theme: light", dark: "Theme: dark" };
function theme(next) {
  let now = "system";
  try { now = next || localStorage.getItem("clio-editor-theme") || "system"; } catch (e) { now = next || "system"; }
  if (!(now in THEMES)) now = "system";
  if (now === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", now);
  $("theme").textContent = THEMES[now];
  $("theme").dataset.now = now;
  if (next) { try { localStorage.setItem("clio-editor-theme", now); } catch (e) { /* private window: for this visit only */ } }
}

// ---------------------------------------------------------------------- start
$("workshop").addEventListener("click", () => {
  state.id = null;
  state.workshop = { like: "", floor: null, rank: "regular", lean: 0, name: "", result: null };
  renderList(); renderForm();
});
$("find").addEventListener("input", () => { clearTimeout(state.searching); state.searching = setTimeout(search, 250); });
$("match-case").addEventListener("change", search);
$("replace-all").addEventListener("click", replaceAll);
$("export-text").addEventListener("click", exportText);
$("import-text").addEventListener("click", () => $("import-file").click());
$("import-file").addEventListener("change", (e) => { if (e.target.files[0]) importText(e.target.files[0]); e.target.value = ""; });
$("download").addEventListener("click", downloadGame);
$("theme").addEventListener("click", () => { const order = Object.keys(THEMES); theme(order[(order.indexOf($("theme").dataset.now) + 1) % order.length]); });
theme();
$("filter").addEventListener("input", (e) => { state.filter = e.target.value; renderList(); });
$("save").addEventListener("click", saveAll);
$("problems-toggle").addEventListener("click", () => { $("problems").hidden = !$("problems").hidden; });
$("add").addEventListener("submit", (e) => {
  e.preventDefault();
  const kind = kindOf(state.kind);
  const id = $("add-id").value.trim();
  if (!validId(id)) return status("An id is letters, digits, _ . and - without spaces.", true);
  if (find(kind, id)) return status(`There is already a ${kind.one} called ${id}.`, true);
  $("add-id").value = "";
  status("");
  add(kind, id, kind.title ? { [kind.title]: id.replace(/[_.-]+/g, " ").replace(/^./, (c) => c.toUpperCase()) } : {});
});
window.addEventListener("beforeunload", (e) => { if (state.dirty.size) { e.preventDefault(); e.returnValue = ""; } });
window.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); if (state.dirty.size) saveAll(); }
});

(async function start() {
  try {
    state.game = await api("/api/game");
  } catch (err) {
    return status("Could not open the game: " + err.message, true);
  }
  state.problems = state.game.problems;
  $("title").textContent = state.game.title;
  $("folder").textContent = state.game.folder;
  status(state.problems.length ? "" : "The engine finds no problems.");
  renderAll();
  select("game", "game");
})();
