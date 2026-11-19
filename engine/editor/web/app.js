// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 Daniel Sandner
// CLIo editor. The page knows nothing about games: the server sends the files, a description of
// their fields (engine/schema.py) and the problems the engine finds; forms are built from that.
"use strict";

const PARAMS = new URLSearchParams(location.search);
const KEY = PARAMS.get("key") || "";
// Started with `clio.py --edit`, the page talks to that program. Opened from a web address there is nobody to talk
// to: the page then runs the engine itself (see "the editor without a server", below). ?hosted asks for that anywhere.
let HOSTED = !KEY && (PARAMS.has("hosted") || !["127.0.0.1", "localhost", "[::1]"].includes(location.hostname));
const $ = (id) => document.getElementById(id);
const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const state = { open: new Set(), shown: new Set(), game: null, kind: null, id: null, dirty: new Set(), problems: [], filter: "", checking: 0, found: [], searching: 0 };

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
  if (HOSTED) return hostedApi(path, body);
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
    status("Saved " + saved.join(", ") + "." + (HOSTED ? await kept() : ""));
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
  $("sheet").hidden = !kind || !["sprites", "tiles", "monsters"].includes(kind.key);
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
  state.sheet = null;
  state.finish = false;
  if (kindOf(kindKey).shape !== "object" && id === null) state.filter = $("filter").value = "";
  renderKinds(); renderList(); renderForm();
}

function field(label, control, note) {
  const id = "f-" + Math.random().toString(36).slice(2, 9);
  if (control.tagName === "INPUT" || control.tagName === "SELECT" || control.tagName === "TEXTAREA") control.id = id;
  return el("div", { class: control.classList.contains("effects") ? "field wide" : "field" }, el("label", { for: control.id || null }, label), control, note || null);
}

// A form control is only offered for a value of the kind it expects; anything else stays in the JSON below.
function fits(f, value) {
  if (value === undefined) return true;
  if (f.type === "number") return typeof value === "number";
  if (f.type === "bool") return typeof value === "boolean";
  if (f.type === "tags" || f.type === "refs" || f.type === "lines") return Array.isArray(value) && value.every((v) => typeof v === "string");
  if (f.type === "sprite") return typeof value === "string";
  if (f.type === "range") return Array.isArray(value) && value.length === 2 && value.every((v) => typeof v === "number");
  if (f.type === "effects") return Array.isArray(value) || isObject(value);
  if (f.type === "condition") return typeof value === "string" || Array.isArray(value) || isObject(value);
  if (f.type === "group" || f.type === "banner" || f.type === "endscreen") return isObject(value);
  if (f.type === "map") return isObject(value) && Object.values(value).every(isObject);
  if (f.type === "rows") return Array.isArray(value) && value.every(isObject);
  return typeof value === "string";
}

function put(thing, key, value) {
  if (value === "" || value === null || value === undefined || (Array.isArray(value) && value.length === 0)) delete thing[key];
  else thing[key] = value;
}

// ---------------------------------------------------------------------- what happens, and when: effects and conditions
// Both are built from the engine's own vocabularies (engine/schema.py). Whatever is richer than a form can say stays
// as it was written, and is edited as JSON: nothing is reshaped by being shown.
const wordOf = (list, key) => list.find((v) => v.key === key);

function fitsArg(arg, value) {
  if (arg === "json") return true;
  if (arg === "none") return value === true;
  if (arg === "number") return typeof value === "number";
  if (typeof arg === "string" || arg.ref || arg.choice || arg.words) return typeof value === "string";
  if (arg.pair) return Array.isArray(value) && value.length === 2 && fitsArg(arg.pair[0], value[0]) && fitsArg(arg.pair[1], value[1]);
  if (arg.way) return typeof value === "string" || (Array.isArray(value) && value.length === 2 && value.every((v) => typeof v === "string"));
  if (arg.measure) {
    const n = arg.measure.length;
    return Array.isArray(value) && value.length === n + 2 && (n === 0 || typeof value[0] === "string") &&
      arg.ops.includes(value[n]) && typeof value[n + 1] === "number";
  }
  return false;
}

function blank(arg) {
  if (arg === "number") return 0;
  if (arg === "none") return true;
  if (arg === "json") return null;
  if (arg.pair) return arg.pair.map(blank);
  if (arg.measure) return [...arg.measure.map(blank), arg.ops[0], 0];
  return "";
}

function jsonInput(value, set) {
  return el("input", { type: "text", class: "code", value: value === undefined ? "" : JSON.stringify(value), spellcheck: "false", title: "As written in the file (JSON)",
    oninput: (e) => {
      try { set(e.target.value.trim() === "" ? undefined : JSON.parse(e.target.value)); e.target.classList.remove("wrong"); } catch (err) { e.target.classList.add("wrong"); }
    } });
}

let listCount = 0;

function argControl(arg, value, set) {
  if (arg === "none") return null;
  if (arg === "json") return jsonInput(value, set);
  if (arg === "number") return el("input", { type: "number", step: "any", value: typeof value === "number" ? String(value) : "", oninput: (e) => set(e.target.value === "" ? 0 : Number(e.target.value)) });
  if (arg === "long") { const area = el("textarea", { rows: "2", oninput: (e) => set(e.target.value) }); area.value = value || ""; return area; }
  if (arg.ref || arg.choice) {
    const options = arg.choice || idsOf(arg.ref);
    return el("select", { onchange: (e) => set(e.target.value) }, el("option", { value: "", selected: !value }, arg.none || "-"),
      ...options.map((o) => el("option", { value: o, selected: o === value }, o)),
      !value || options.includes(value) ? null : el("option", { value, selected: true }, arg.choice ? value : `${value} (not found)`));
  }
  if (arg.words) {
    const id = `words-${listCount += 1}`;
    return el("span", { class: "pair" }, el("input", { type: "text", class: "short", list: id, value: value || "", oninput: (e) => set(e.target.value) }),
      el("datalist", { id }, ...arg.words.map((w) => el("option", { value: w }))));
  }
  if (arg.pair) {
    const both = Array.isArray(value) ? value.slice() : arg.pair.map(blank);
    return el("span", { class: "pair" }, ...arg.pair.map((part, i) => argControl(part, both[i], (v) => { both[i] = v; set(both.slice()); })));
  }
  if (arg.way) {                                                       // "to", or ["from", "to"]; from this room when no room is named
    let from = Array.isArray(value) ? value[0] : "", to = Array.isArray(value) ? value[1] : value || "";
    const write = () => set(from ? [from, to] : to);
    return el("span", { class: "pair" }, "from", argControl({ ref: "scenes", none: "this room" }, from, (v) => { from = v; write(); }),
      "to", argControl({ ref: "scenes" }, to, (v) => { to = v; write(); }));
  }
  if (arg.measure) {
    const parts = Array.isArray(value) ? value.slice() : blank(arg);
    const n = arg.measure.length;
    const write = () => set(parts.slice());
    return el("span", { class: "pair" },
      n ? argControl(arg.measure[0], parts[0], (v) => { parts[0] = v; write(); }) : null,
      el("select", { class: "op", "aria-label": "How", onchange: (e) => { parts[n] = e.target.value; write(); } }, ...arg.ops.map((o) => el("option", { value: o, selected: o === parts[n] }, o))),
      argControl("number", parts[n + 1], (v) => { parts[n + 1] = v; write(); }));
  }
  return el("input", { type: "text", class: arg === "flag" ? "code" : "", value: value || "", placeholder: arg === "flag" ? "a flag's name" : "", oninput: (e) => set(e.target.value) });
}

function effectsControl(kind, f, thing) {
  const words = state.game.effects;
  const raw = thing[f.key];
  const list = Array.isArray(raw) ? raw : isObject(raw) ? [raw] : [];
  const commit = () => { if (list.length) thing[f.key] = list; else delete thing[f.key]; touched(kind); };
  const again = () => { commit(); renderForm(); };
  const tool = (label, title, act, off) => el("button", { type: "button", class: "quiet small", title, disabled: !!off, onclick: () => { act(); again(); } }, label);
  const rows = list.map((eff, i) => {
    const tools = el("span", { class: "entry-tools" },
      tool("↑", "Earlier", () => { list.splice(i - 1, 0, list.splice(i, 1)[0]); }, i === 0),
      tool("↓", "Later", () => { list.splice(i + 1, 0, list.splice(i, 1)[0]); }, i === list.length - 1),
      tool("Remove", "Remove this effect", () => { list.splice(i, 1); }));
    const verbs = isObject(eff) ? Object.keys(eff).filter((k) => wordOf(words, k)) : [];
    const spec = verbs.length === 1 && !("then" in eff) && !("else" in eff) ? wordOf(words, verbs[0]) : null;
    if (!spec || !fitsArg(spec.arg, eff[spec.key])) {                // several things at once, or richer than a form: as written
      return el("div", { class: "effect written" }, jsonInput(eff, (v) => { if (v !== undefined) { list[i] = v; commit(); } }), tools);
    }
    const others = Object.keys(eff).filter((k) => k !== spec.key);
    const pick = el("select", { "aria-label": "What happens", onchange: (e) => {
      const next = wordOf(words, e.target.value);
      const rest = Object.fromEntries(others.map((k) => [k, eff[k]]));
      list[i] = Object.assign({ [next.key]: blank(next.arg) }, rest);
      again();
    } }, ...words.map((w) => el("option", { value: w.key, selected: w.key === spec.key }, w.label)));
    const extra = others.length ? jsonInput(Object.fromEntries(others.map((k) => [k, eff[k]])), (v) => {
      if (!isObject(v)) return;
      for (const k of others) delete eff[k];
      Object.assign(eff, v);
      commit();
    }) : null;
    if (extra) extra.classList.add("extra");
    if (extra) extra.title = "More about this effect, as written in the file (JSON): its style, a condition (\"if\"), quiet…";
    return el("div", { class: "effect" }, pick, argControl(spec.arg, eff[spec.key], (v) => { eff[spec.key] = v; commit(); }), extra, tools);
  });
  const add = el("select", { "aria-label": "Add an effect", onchange: (e) => {
    const w = wordOf(words, e.target.value);
    if (!w) return;
    list.push({ [w.key]: blank(w.arg) });
    again();
  } }, el("option", { value: "" }, list.length ? "and then…" : "nothing; add…"), ...words.map((w) => el("option", { value: w.key }, w.label)));
  return el("div", { class: "effects" }, ...rows, add);
}

// One question as the form sees it: {not, key, arg}, or null when the condition is richer than one question.
function readCondition(value, words) {
  if (typeof value === "string") {
    const not = value.startsWith("!");
    const text = not ? value.slice(1) : value;
    const cut = text.indexOf(":");
    if (cut < 0) return { not, key: "flag", arg: text };
    const word = wordOf(words, text.slice(0, cut).trim());
    if (!word) return null;
    const rest = text.slice(cut + 1).trim();
    const arg = word.arg.pair ? rest.split(":") : word.arg === "number" ? Number(rest) : rest;
    return fitsArg(word.arg, arg) ? { not, key: word.key, arg } : null;
  }
  if (!isObject(value) || Object.keys(value).length !== 1) return null;
  const key = Object.keys(value)[0];
  if (key === "not") {
    const inner = readCondition(value.not, words);
    return inner && !inner.not ? Object.assign(inner, { not: true }) : null;
  }
  const word = wordOf(words, key);
  return word && word.arg !== "json" && fitsArg(word.arg, value[key]) ? { not: false, key, arg: value[key] } : null;
}

// ...and written back: the short form ("has:key", "!flag") where the engine reads one, the long form otherwise.
function writeCondition({ not, key, arg }, words) {
  if (!key) return undefined;
  const spec = wordOf(words, key).arg;
  const plain = (v) => typeof v === "string" && v !== "" && !v.includes(":") && !v.startsWith("!");
  const short = spec.measure || spec === "number" ? false : Array.isArray(arg) ? ["quest", "item_state", "state"].includes(key) && arg.every(plain) : plain(arg);
  if (short) return (not ? "!" : "") + (key === "flag" ? arg : `${key}:${Array.isArray(arg) ? arg.join(":") : arg}`);
  return not ? { not: { [key]: arg } } : { [key]: arg };
}

function conditionControl(kind, f, thing) {
  const all = state.game.conditions;
  const value = thing[f.key];
  const put = (v) => { if (v === undefined || v === "") delete thing[f.key]; else thing[f.key] = v; touched(kind); };
  const empty = value === undefined || value === "";
  const now = empty ? { not: false, key: "", arg: "" } : readCondition(value, all);
  if (!now) {                                                          // richer than one question: as written
    return el("div", { class: "effects" }, el("div", { class: "effect written" }, jsonInput(value, put), el("span", { class: "note" }, "More than one question; it is edited as written in the file.")));
  }
  const offered = all.filter((w) => w.arg !== "json" && (!w.short || w.key === now.key));
  const write = () => put(writeCondition(now, all));
  const pick = el("select", { "aria-label": "Condition", onchange: (e) => {
    now.key = e.target.value;
    now.arg = now.key ? blank(wordOf(all, now.key).arg) : "";
    write();
    renderForm();
  } }, el("option", { value: "", selected: !now.key }, "always"), ...offered.map((w) => el("option", { value: w.key, selected: w.key === now.key }, w.label)));
  if (!now.key) return el("div", { class: "effects" }, el("div", { class: "effect" }, pick));
  const no = el("input", { type: "checkbox", checked: now.not, onchange: (e) => { now.not = e.target.checked; write(); } });
  return el("div", { class: "effects" }, el("div", { class: "effect" }, pick, argControl(wordOf(all, now.key).arg, now.arg, (v) => { now.arg = v; write(); }),
    el("label", { class: "tick", title: "Holds when this is not so" }, no, " not")));
}

// What is not covered by a form: the other keys of an object, as JSON. Nothing is hidden, nothing dropped.
function restArea(kind, thing, known, plain) {
  const rest = {};
  for (const [k, v] of Object.entries(thing)) if (!known.has(k)) rest[k] = v;
  const usual = plain || "Fields without a form of their own yet, as JSON. They are kept exactly as written.";
  const note = el("p", { class: "note" }, usual);
  const text = JSON.stringify(rest, null, 2);
  const area = el("textarea", { class: "code", spellcheck: "false", rows: String(Math.min(28, Math.max(3, text.split("\n").length + 1))),
    oninput: (e) => {
      let parsed;
      const bad = (why) => { note.textContent = why; note.classList.add("bad"); };
      try { parsed = JSON.parse(e.target.value || "{}"); } catch (err) { return bad("Not valid JSON yet: " + err.message); }
      if (!isObject(parsed)) return bad("This must be a JSON object: { … }");
      const clash = Object.keys(parsed).find((k) => known.has(k));
      if (clash) return bad(`"${clash}" has its own field above.`);
      note.textContent = usual; note.classList.remove("bad");
      for (const k of Object.keys(thing)) if (!known.has(k) && !(k in parsed)) delete thing[k];      // keep the order the file had
      for (const [k, v] of Object.entries(parsed)) thing[k] = v;
      touched(kind);
    } });
  area.value = text;
  return { area, note, empty: Object.keys(rest).length === 0 };
}

// Fields marked "rare" in the schema are shown where a thing has them; elsewhere they wait in one "Add…" list,
// so that a form is as long as the thing and not as long as everything a thing could have.
function offered(fields, obj, path) {
  const at = (f) => `${state.kind}/${state.id}/${path}/${f.key}`;
  const now = fields.filter((f) => !f.rare || obj[f.key] !== undefined || state.shown.has(at(f)));
  const later = fields.filter((f) => !now.includes(f));
  if (!later.length) return { now, more: null };
  const more = el("select", { class: "more", "aria-label": "Add a part", onchange: (e) => {
    const f = later.find((x) => x.key === e.target.value);
    if (f) { state.shown.add(at(f)); renderForm(); }
  } }, el("option", { value: "" }, "Add…"), ...later.map((f) => el("option", { value: f.key }, f.label)));
  return { now, more };
}

// The fields of an object that is part of a thing (an exit, a move, a dialogue node), with its other keys as JSON.
function subform(kind, fields, obj, path) {
  const fit = fields.filter((f) => fits(f, obj[f.key]));
  const known = new Set(fit.map((f) => f.key));
  const laid = offered(fit, obj, path);
  const parts = laid.now.map((f) => field(f.label, control(kind, f, obj, `${path}/${f.key}`)));
  if (laid.more) parts.push(laid.more);
  const rest = restArea(kind, obj, known);
  const other = field("Other fields", rest.area, rest.note);
  if (!rest.empty) parts.push(other);
  else {
    other.hidden = true;
    parts.push(other, el("button", { type: "button", class: "link", onclick: (e) => { other.hidden = false; e.target.remove(); } }, "Other fields…"));
  }
  return parts;
}

const naming = (row, fallback) => {
  const said = [row.name, row.door_name, row.text, row.id, row.type].find((v) => typeof v === "string" && v.trim());
  return said ? (said.length > 64 ? said.slice(0, 61) + "…" : said) : fallback;
};

// One entry of a list or of a set of named things: closed until asked for, so a long thing stays short.
function entry(key, title, tools, body) {
  const where = `${state.kind}/${state.id}/${key}`;
  return el("details", { class: "entry", "data-where": where, open: state.open.has(where), ontoggle: (e) => { if (e.target.open) state.open.add(where); else state.open.delete(where); } },
    el("summary", {}, el("span", { class: "entry-title" }, title), el("span", { class: "entry-tools" }, ...tools)), ...body());
}

function control(kind, f, thing, path) {
  const change = (value) => { put(thing, f.key, value); touched(kind); renderList(); };
  const value = thing[f.key];
  path = path || f.key;
  const again = () => { touched(kind); renderForm(); };
  const tool = (label, title, act, off) => el("button", { type: "button", class: "quiet small", title, disabled: !!off, onclick: (e) => { e.preventDefault(); act(); again(); } }, label);
  if (f.type === "effects") return effectsControl(kind, f, thing);
  if (f.type === "condition") return conditionControl(kind, f, thing);
  if (f.type === "banner") return bannerField(kind, f, thing, path);
  if (f.type === "endscreen") return endScreenField(kind, f, thing, path);
  if (f.type === "group") {
    if (!isObject(value)) return el("button", { type: "button", class: "quiet", onclick: () => { thing[f.key] = {}; state.open.add(`${state.kind}/${state.id}/${path}`); again(); } }, `Add ${f.label.toLowerCase()}`);
    return el("div", { class: "group" }, ...subform(kind, f.fields, value, path));
  }
  if (f.type === "rows") {
    const list = Array.isArray(value) ? value : [];
    const one = f.one || "row";
    return el("div", { class: "rows" },
      ...list.map((row, i) => entry(`${path}/${i}`, naming(row, `${one} ${i + 1}`), [
        tool("↑", "Move up", () => { list.splice(i - 1, 0, list.splice(i, 1)[0]); }, i === 0),
        tool("↓", "Move down", () => { list.splice(i + 1, 0, list.splice(i, 1)[0]); }, i === list.length - 1),
        tool("Remove", `Remove this ${one}`, () => { list.splice(i, 1); if (!list.length) delete thing[f.key]; })],
      () => subform(kind, f.fields, row, `${path}/${i}`))),
      el("button", { type: "button", class: "quiet", onclick: () => {
        if (!Array.isArray(thing[f.key])) thing[f.key] = [];
        thing[f.key].push({});
        state.open.add(`${state.kind}/${state.id}/${path}/${thing[f.key].length - 1}`);
        again();
      } }, `Add ${/^[aeiou]/.test(one) ? "an" : "a"} ${one}`));
  }
  if (f.type === "map") {
    const map = isObject(value) ? value : {};
    const one = f.one || "entry";
    const name = el("input", { type: "text", class: "code", placeholder: `name for a new ${one}`, "aria-label": `Name for a new ${one}`, spellcheck: "false" });
    const rename = (old) => {
      const next = (prompt(`A new name for "${old}":`, old) || "").trim();
      if (!next || next === old || next in map) return false;
      thing[f.key] = Object.fromEntries(Object.entries(map).map(([k, v]) => [k === old ? next : k, v]));
      return true;
    };
    return el("div", { class: "rows" },
      ...Object.entries(map).map(([k, row]) => entry(`${path}/${k}`, k, [
        el("button", { type: "button", class: "quiet small", title: "Change its name. What refers to it is not changed.", onclick: (e) => { e.preventDefault(); if (rename(k)) again(); } }, "Rename"),
        tool("Remove", `Remove this ${one}`, () => { delete map[k]; if (!Object.keys(map).length) delete thing[f.key]; })],
      () => subform(kind, f.fields, row, `${path}/${k}`))),
      el("form", { class: "row", onsubmit: (e) => {
        e.preventDefault();
        const k = name.value.trim();
        if (!k || k in map) return;
        if (!isObject(thing[f.key])) thing[f.key] = {};
        thing[f.key][k] = {};
        state.open.add(`${state.kind}/${state.id}/${path}/${k}`);
        again();
      } }, name, el("button", { type: "submit", class: "quiet" }, `Add ${/^[aeiou]/.test(one) ? "an" : "a"} ${one}`)));
  }
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
  if (f.type === "lines") {                                  // a list of lines, one a line (commas and all)
    const area = el("textarea", { rows: "3", oninput: (e) => change(e.target.value.split("\n").map((x) => x.trim()).filter(Boolean)) });
    area.value = Array.isArray(value) ? value.join("\n") : "";
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
  if (f.type === "range") {
    const pair = Array.isArray(value) ? value.slice() : [0, 0];
    const num = (i, label) => el("input", { type: "number", step: "any", class: "short", "aria-label": label, value: Array.isArray(value) ? String(pair[i]) : "",
      oninput: (e) => { pair[i] = Number(e.target.value) || 0; change(pair.slice()); } });
    return el("span", { class: "pair" }, num(0, "Least"), " to ", num(1, "Most"));
  }
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
  if (state.sheet) return renderSheet(host);
  if (state.finish) return renderFinish(host);
  const kind = state.kind && kindOf(state.kind);
  const hit = kind && state.id !== null ? find(kind, state.id) : null;
  if (!hit && kind && kind.key === "scenes" && things(kind).length) return renderMap(host);
  if (!hit) {
    host.replaceChildren(el("p", { class: "empty" }, !kind ? "Choose something on the left to edit it."
      : things(kind).length ? `Choose a ${kind.one} in the list, or add a new one below it.`
        : `This game has no ${kind.label.toLowerCase()} yet. Type an id below the list and press Add.`));
    return;
  }
  const { thing } = hit;
  const single = kind.shape === "object";
  const fields = kind.fields.filter((f) => fits(f, thing[f.key]));
  const rowsOk = (d) => Array.isArray(d) && d.every((r) => typeof r === "string");
  const drawn = kind.editor === "sprite" && (thing.pixels === undefined || rowsOk(thing.pixels))
    && (thing.palette === undefined || (thing.palette && typeof thing.palette === "object" && !Array.isArray(thing.palette)))
    && (thing.frames === undefined || (Array.isArray(thing.frames) && thing.frames.every(rowsOk)))
    && (thing.lod === undefined || (Array.isArray(thing.lod) && thing.lod.every((l) => l && rowsOk(l.pixels) && l.pixels.length)));
  const mapped = kind.editor === "level" && (thing.map === undefined || rowsOk(thing.map)) && (thing.legend === undefined || isObject(thing.legend));
  const built = kind.editor === "model" && (thing.materials === undefined || isObject(thing.materials))
    && (thing.parts === undefined || (Array.isArray(thing.parts) && thing.parts.every(isObject)));
  const known = new Set(fields.map((f) => f.key).concat(kind.shape === "list" ? ["id"] : [], drawn ? ["palette", "pixels", "frames", "lod", "keep"] : [],
    mapped ? ["map", "legend", "events", "bot", "floor", "ceiling"] : [], built ? ["materials", "parts"] : []));
  const parts = [];

  const head = el("div", { class: "head" }, el("h2", {}, single ? kind.label : titleOf(kind, hit)));
  if (!single) {
    head.append(
      el("button", { type: "button", class: "quiet", onclick: () => duplicate(kind, hit) }, "Duplicate"),
      el("button", { type: "button", class: "quiet warn", onclick: () => remove(kind, hit) }, "Delete"));
  }
  parts.push(head);
  if (kind.key === "dialogues" && isObject(thing.nodes) && Object.keys(thing.nodes).length) parts.push(dialogueSheet(kind, hit));
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
  const laid = offered(fields, thing, "");
  for (const f of laid.now) parts.push(field(f.label, control(kind, f, thing)));
  if (laid.more) parts.push(laid.more);
  if (drawn) parts.push(spriteEditor(kind, thing));
  if (mapped) parts.push(levelEditor(kind, thing, hit.id));
  if (kind.editor === "weapon") parts.push(weaponSheet(kind, thing, hit.id));
  if (kind.editor === "model") parts.push(modelSheet(kind, thing, hit.id, built));

  // everything the schema does not describe is still here, as JSON
  const rest = restArea(kind, thing, known, kind.fields.length || drawn ? "" : "This kind has no form yet: edit it as JSON.");
  parts.push(field(kind.fields.length || drawn ? "Everything else" : "Content", rest.area, rest.note));
  if (mapped && rest.empty) parts[parts.length - 1].hidden = true;

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

// ---------------------------------------------------------------------- pictures of the game: rooms, conversations
function sv(tag, attrs, ...kids) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v);
  }
  node.append(...kids.filter((k) => k !== null && k !== undefined && k !== false));
  return node;
}
const short = (text, n) => (text.length > n ? text.slice(0, n - 1) + "…" : text);
const arrowHead = (id) => sv("defs", {}, sv("marker", { id, viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "7", markerHeight: "7", orient: "auto-start-reverse" },
  sv("path", { d: "M 0 0 L 10 5 L 0 10 z", class: "head" })));

// Where the rooms are: the grid the player's own map uses, one level at a time. Drag a room to pin it somewhere else.
async function renderMap(host) {
  const kind = kindOf("scenes");
  host.replaceChildren(el("div", { class: "head" }, el("h2", {}, "Map")), el("p", { class: "lead" }, "Drawing the map…"));
  let map;
  try { map = await api("/api/map", { pending: pending() }); } catch (err) { host.replaceChildren(el("p", { class: "empty" }, "The map cannot be drawn: " + err.message)); return; }
  if (state.kind !== "scenes" || state.id !== null || state.workshop) return;
  const room = Object.fromEntries(map.rooms.map((r) => [r.id, r]));
  const placed = map.rooms.filter((r) => r.placed);
  if (!map.levels.includes(state.level)) state.level = room[map.start] && room[map.start].placed ? room[map.start].z : map.levels[0];
  const here = placed.filter((r) => r.z === state.level);
  const W = 172, H = 78, BW = 140, BH = 46, PAD = 24;
  const minX = Math.min(...here.map((r) => r.x)), minY = Math.min(...here.map((r) => r.y));
  const cx = (r) => (r.x - minX) * W + PAD + BW / 2, cy = (r) => (r.y - minY) * H + PAD + BH / 2;
  const svg = sv("svg", { class: "picture", role: "img", "aria-label": `Map of level ${state.level}: ${here.length} rooms`,
    width: (Math.max(...here.map((r) => r.x)) - minX) * W + BW + 2 * PAD, height: (Math.max(...here.map((r) => r.y)) - minY) * H + BH + 2 * PAD + 14 }, arrowHead("way-head"));
  const drawn = new Set();
  for (const w of map.ways) {                               // the ways first, so that rooms lie on top of them
    const a = room[w.from], b = room[w.to];
    if (!a || !b || !a.placed || !b.placed || a.z !== state.level || b.z !== state.level) continue;
    const pair = [w.from, w.to].sort().join(" ");
    if (drawn.has(pair)) continue;
    drawn.add(pair);
    const other = map.ways.find((o) => o.from === w.to && o.to === w.from);
    const barred = w.barred || (other && other.barred) || "";
    const dx = cx(b) - cx(a), dy = cy(b) - cy(a);
    const edge = w.one_way ? Math.min(dx ? (BW / 2 + 3) / Math.abs(dx) : 1, dy ? (BH / 2 + 3) / Math.abs(dy) : 1) : 0;   // stop at the room's edge, so the arrow shows
    svg.append(sv("line", { x1: cx(a), y1: cy(a), x2: cx(b) - dx * edge, y2: cy(b) - dy * edge, class: "way" + (barred ? " barred" : ""), "marker-end": w.one_way ? "url(#way-head)" : null },
      sv("title", {}, `${w.name || "A way"} from ${a.name} to ${b.name}` + (barred ? `, ${barred}` : "") + (w.one_way ? ", one way" : ""))));
  }
  for (const r of here) {
    const stairs = map.ways.filter((w) => w.from === r.id && (w.generated || w.missing || (room[w.to] && room[w.to].placed && room[w.to].z !== r.z)));
    const flagged = state.problems.some((p) => p.kind === "scenes" && p.id === r.id);
    const g = sv("g", { class: "room" + (r.id === map.start ? " first" : "") + (flagged ? " flagged" : "") + (r.reached ? "" : " lost"), transform: `translate(${cx(r) - BW / 2},${cy(r) - BH / 2})`, tabindex: "0", role: "button",
      "aria-label": `${r.name}. Enter opens it.`, onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select("scenes", r.id); } } },
    sv("rect", { width: BW, height: BH, rx: "6" }),
    sv("text", { x: BW / 2, y: 20, class: "name" }, short(r.name, 19)),
    sv("text", { x: BW / 2, y: 36, class: "sub" }, short(r.id, 22) + (r.id === map.start ? " (start)" : "")),
    sv("title", {}, `${r.name} (${r.id})` + (r.reached ? "" : ", which no exit leads to") + (r.pinned ? "" : ", placed by the game") + ". Click to open, drag to move."));
    stairs.forEach((w, i) => {
      const up = w.level > 0, to = room[w.to];
      g.append(sv("text", { x: BW - 6 - i * 16, y: BH + 13, class: "stair" + (w.missing ? " bad" : ""), onpointerdown: (e) => e.stopPropagation(),
        onclick: (e) => { e.stopPropagation(); if (to && to.placed) { state.level = to.z; renderMap(host); } } },
      w.missing ? "?" : up ? "▲" : "▼", sv("title", {}, w.missing ? `${w.name || "An exit"} leads to "${w.to}", which does not exist` : w.generated ? `${w.name || "An exit"}: leads into rooms the game makes as it is played`
        : `${w.name || "Stairs"} to ${to.name}, level ${to.z}`)));
    });
    let from = null;                                        // a click opens the room; a drag of more than half a cell pins it there
    g.addEventListener("pointerdown", (e) => { from = [e.clientX, e.clientY]; g.setPointerCapture(e.pointerId); });
    g.addEventListener("pointermove", (e) => { if (from) g.setAttribute("transform", `translate(${cx(r) - BW / 2 + e.clientX - from[0]},${cy(r) - BH / 2 + e.clientY - from[1]})`); });
    g.addEventListener("pointerup", (e) => {
      if (!from) return;
      const dx = Math.round((e.clientX - from[0]) / W), dy = Math.round((e.clientY - from[1]) / H);
      from = null;
      if (!dx && !dy) return select("scenes", r.id);
      if (here.some((o) => o.x === r.x + dx && o.y === r.y + dy)) { status("There is already a room in that place.", true); return renderMap(host); }
      find(kind, r.id).thing.map = [r.x + dx, r.y + dy, r.z];
      touched(kind);
      status(`${r.name} is pinned to its new place on the map. Nothing is written until you save.`);
      renderMap(host);
    });
    svg.append(g);
  }
  const lost = map.rooms.filter((r) => !r.reached);
  host.replaceChildren(...[
    el("div", { class: "head" }, el("h2", {}, "Map"),
      ...(map.levels.length > 1 ? map.levels.map((z) => el("button", { type: "button", class: "quiet" + (z === state.level ? " on" : ""), "aria-pressed": z === state.level ? "true" : "false",
        onclick: () => { state.level = z; renderMap(host); } }, `Level ${z}`)) : [])),
    el("p", { class: "lead" }, "The rooms where the player's own map puts them. Click a room to open it; drag one to pin it to another place. " +
      "A dashed way is locked, blocked or guarded; an arrow is a way with no way back; ▲ and ▼ lead to another level." +
      (map.generated ? " This game also makes rooms as it is played; those are not here." : "")),
    el("div", { class: "picture-box" }, svg),
    lost.length ? el("p", { class: "lead" }, "Drawn with a dashed edge, because no exit leads there from the first scene: ",
      ...lost.flatMap((r, i) => [i ? ", " : "", el("button", { type: "button", class: "link", onclick: () => select("scenes", r.id) }, r.name)]), ".") : null].filter(Boolean));
}

// How a conversation runs: nodes from left to right in the order they can be reached, jumps as arrows.
function dialogueSheet(kind, hit) {
  const box = el("div", { class: "picture-box" }, el("p", { class: "note" }, "Drawing the conversation…"));
  const sheet = el("div", { class: "sheet wide" }, el("h3", {}, "How it runs"), box);
  api("/api/dialogue", { tree: hit.thing }).then((g) => {
    const BW = 176, BH = 52, CW = 250, RH = 72, PAD = 16;
    const cols = {};
    const last = Math.max(0, ...g.nodes.filter((n) => n.reached).map((n) => n.depth));
    for (const n of g.nodes) { const c = n.reached ? n.depth : last + 1; (cols[c] = cols[c] || []).push(n); n.col = c; n.row = cols[c].length - 1; }
    const at = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
    const x = (n) => PAD + n.col * CW, y = (n) => PAD + 18 + n.row * RH;
    const svg = sv("svg", { class: "picture", role: "img", "aria-label": `The conversation ${hit.id}: ${g.nodes.length} nodes`,
      width: PAD * 2 + Object.keys(cols).length * CW - (CW - BW), height: PAD * 2 + 18 + Math.max(...Object.values(cols).map((c) => c.length)) * RH }, arrowHead("jump-head"));
    g.jumps.forEach((j, i) => {
      const a = at[j.from], b = at[j.to];
      const forward = b.col > a.col;
      const x1 = forward ? x(a) + BW : x(a) + BW / 2, y1 = forward ? y(a) + BH / 2 : y(a), x2 = forward ? x(b) : x(b) + BW / 2 + 12, y2 = forward ? y(b) + BH / 2 : y(b);
      const lift = 18 + (i % 4) * 7;
      const d = forward ? `M ${x1} ${y1} C ${x1 + 50} ${y1}, ${x2 - 50} ${y2}, ${x2} ${y2}` : `M ${x1} ${y1} C ${x1} ${y1 - lift}, ${x2} ${y2 - lift}, ${x2} ${y2}`;
      svg.append(sv("path", { d, class: "jump" + (forward ? "" : " back") + (j.kind === "then" ? " then" : ""), "marker-end": "url(#jump-head)" },
        sv("title", {}, j.kind === "then" ? `${j.from} goes on to ${j.to} by itself` : `"${j.by}" leads from ${j.from} to ${j.to}`)));
      if (j.by && forward) svg.append(sv("text", { x: (x1 + x2) / 2, y: (y1 + y2) / 2 - 4, class: "by" }, short(j.by, 22)));
    });
    for (const n of g.nodes) {
      const open = () => {
        const where = `${kind.key}/${hit.id}/nodes/${n.id}`;
        state.open.add(where);
        renderForm();
        const target = document.querySelector(`details[data-where="${CSS.escape(where)}"]`);
        if (target) target.scrollIntoView({ block: "center" });
      };
      svg.append(sv("g", { class: "room" + (n.start ? " first" : "") + (n.reached ? "" : " lost"), transform: `translate(${x(n)},${y(n)})`, tabindex: "0", role: "button", "aria-label": `Node ${n.id}. Enter opens it.`,
        onclick: open, onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } } },
      sv("rect", { width: BW, height: BH, rx: "6" }),
      sv("text", { x: 10, y: 20, class: "name left" }, short(n.id, 20) + (n.start ? " (start)" : "")),
      sv("text", { x: 10, y: 38, class: "sub left" }, short(n.text.replace(/\s+/g, " "), 27)),
      n.stays ? sv("text", { x: BW - 8, y: 20, class: "sub right" }, `${n.stays} ↺`) : null,
      sv("title", {}, (n.reached ? "" : "Never reached. ") + (n.stays ? `${n.stays} answer${n.stays === 1 ? "" : "s"} given without leaving this node. ` : "") + (n.text || "(no text)"))));
    }
    const notes = [];
    if (g.nodes.some((n) => !n.reached)) notes.push("A node with a dashed edge is never reached.");
    for (const m of g.missing) notes.push(m.from ? `"${m.from}" jumps to "${m.to}", which does not exist.` : `It starts at "${m.to}", which does not exist.`);
    box.replaceChildren(svg);
    sheet.append(el("p", { class: "note" + (g.missing.length ? " bad" : "") }, ["Click a node to open it below. A solid arrow is a choice, a dotted one a node going on by itself; ↺ counts answers that stay on the node.", ...notes].join(" ")));
  }).catch((err) => box.replaceChildren(el("p", { class: "note bad" }, err.message)));
  return sheet;
}

// ---------------------------------------------------------------------- can it be finished?
// The game's walkthrough, played by the real engine on the game as it is in the page.
async function renderFinish(host) {
  const area = el("textarea", { class: "code walk", spellcheck: "false", rows: "16", "aria-label": "The walkthrough" });
  const out = el("div", {});
  const keep = el("button", { type: "button", class: "quiet", onclick: async () => {
    try { status(`Kept as ${(await api("/api/walkthrough", { text: area.value })).saved} in the game's folder.`); } catch (err) { status("Could not keep the walkthrough: " + err.message, true); }
  } }, "Keep this walkthrough");
  const go = el("button", { type: "button", class: "go", onclick: async () => {
    go.disabled = true;
    out.replaceChildren(el("p", { class: "note" }, "Playing…"));
    try {
      const res = await api("/api/finish", { pending: pending(), text: area.value });
      const parts = [];
      if (!res.walkthroughs.length) parts.push(el("p", { class: "note bad" }, "There is nothing to play yet: write the commands a player would type, one per line."));
      else parts.push(el("h3", {}, res.finished ? "Yes: every way through ends in a win." : "Not as it stands."));
      for (const w of res.walkthroughs) {
        parts.push(el("p", { class: w.won ? "" : "bad" }, el("b", {}, (w.won ? "✓ " : "✗ ") + w.name), w.won ? `: won in ${w.turns} turns.`
          : `: ${w.result ? "ended with “" + w.result + "”" : "not finished"}. At line ${w.stopped.line}, “${w.stopped.command}”, ${w.stopped.why}.`));
        for (const r of w.refused) parts.push(el("p", { class: "note" }, `Line ${r.line}, “${r.command}”, was refused: ${r.said}`));
        if (!w.won) parts.push(el("pre", { class: "tail" }, w.tail.join("\n")));
      }
      for (const [what, kindKey] of [["scenes", "scenes"], ["quests", "quests"]]) {
        const cover = (res.coverage || {})[what];
        if (cover && cover.missing.length) {
          parts.push(el("p", { class: "note" }, `No walkthrough ${what === "scenes" ? "enters" : "completes"} ${cover.missing.length} of the ${cover.total} ${what}: `,
            ...cover.missing.flatMap((id, i) => [i ? ", " : "", el("button", { type: "button", class: "link", onclick: () => select(kindKey, id) }, id)]), "."));
        }
      }
      out.replaceChildren(...parts);
    } catch (err) {
      out.replaceChildren(el("p", { class: "note bad" }, err.message));
    }
    go.disabled = false;
  } }, "Play it");
  host.replaceChildren(
    el("div", { class: "head" }, el("h2", {}, "Can it be finished?")),
    el("p", { class: "lead" }, "No program can tell in general whether an adventure can be won. What can be checked, exactly and every time, is that a known way through still works - " +
      "after every change you make. Write that way here: one command per line, as a player would type them, answers to the game's questions included. " +
      "A line “== name” starts another way through, played from a fresh start; “#” starts a comment; “seed 7” sets the dice."),
    area, el("div", { class: "row gap" }, go, keep), out);
  try { area.value = (await api("/api/walkthrough", {})).text; } catch (err) { status("Could not read the walkthrough: " + err.message, true); }
  if (area.value.trim()) go.click();
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

// A picture given as colours, row by row (null: nothing there), on the dark of a screen.
function paintColours(canvas, rows, cell) {
  const h = rows.length, w = Math.max(1, ...rows.map((r) => r.length));
  canvas.width = w * cell;
  canvas.height = h * cell;
  const c = canvas.getContext("2d");
  c.fillStyle = "#0f1724";
  c.fillRect(0, 0, canvas.width, canvas.height);
  rows.forEach((r, y) => r.forEach((col, x) => { if (col) { c.fillStyle = col; c.fillRect(x * cell, y * cell, cell, cell); } }));
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

// ---------------------------------------------------------------------- banners, drawn as the game draws them
// The engine draws the banner (/api/banner) and sends its cells; the page paints them on a canvas the way a
// terminal does: blocks and braille dots as shapes, so they join without seams.
const BLOCKS = { "▀": [0, 0, 1, 0.5], "▄": [0, 0.5, 1, 1], "█": [0, 0, 1, 1], "▌": [0, 0, 0.5, 1], "▐": [0.5, 0, 1, 1],
  "▁": [0, 0.875, 1, 1], "▔": [0, 0, 1, 0.125], "▖": [0, 0.5, 0.5, 1], "▗": [0.5, 0.5, 1, 1], "▘": [0, 0, 0.5, 0.5], "▝": [0.5, 0, 1, 0.5] };
const SHADES = { "░": 0.3, "▒": 0.55, "▓": 0.8 };
const DOTS = [[0, 0], [0, 1], [0, 2], [1, 0], [1, 1], [1, 2], [0, 3], [1, 3]];

function paintCells(canvas, rows, cols, lines) {
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  const ctx = canvas.getContext("2d");
  const px = Math.round(13 * dpr);
  const font = (bold) => `${bold ? "bold " : ""}${px}px ui-monospace, "DejaVu Sans Mono", Menlo, Consolas, monospace`;
  ctx.font = font(false);
  const cw = Math.max(1, Math.round(ctx.measureText("M").width)), ch = Math.round(px * 1.2);
  const width = (row) => row.reduce((n, run) => n + [...run[0]].length, 0);
  const w = Math.max(0, ...rows.map(width));
  cols = Math.max(cols, w);
  lines = Math.max(lines, rows.length + 2);
  canvas.width = cols * cw;
  canvas.height = lines * ch;
  canvas.style.width = `${canvas.width / dpr}px`;
  canvas.style.height = `${canvas.height / dpr}px`;
  ctx.fillStyle = "#0b0e14";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.textBaseline = "middle";
  const left = Math.floor((cols - w) / 2), top = Math.floor((lines - rows.length) / 2);
  rows.forEach((row, y) => {
    let x = left;
    for (const [text, fg, bg, bold] of row) {
      for (const c of text) {
        const X = x * cw, Y = (top + y) * ch;
        if (bg) { ctx.fillStyle = bg; ctx.fillRect(X, Y, cw, ch); }
        ctx.fillStyle = fg || "#c8cfdb";
        const code = c.codePointAt(0);
        if (BLOCKS[c]) {
          const [a, b, d, e] = BLOCKS[c];
          ctx.fillRect(X + Math.round(a * cw), Y + Math.round(b * ch), Math.round(d * cw) - Math.round(a * cw), Math.round(e * ch) - Math.round(b * ch));
        } else if (SHADES[c]) {
          ctx.globalAlpha = SHADES[c];
          ctx.fillRect(X, Y, cw, ch);
          ctx.globalAlpha = 1;
        } else if (code >= 0x2800 && code <= 0x28ff) {
          const r = Math.max(0.8, Math.min(cw / 2, ch / 4) * 0.36);
          DOTS.forEach(([dx, dy], i) => {
            if ((code - 0x2800) & (1 << i)) { ctx.beginPath(); ctx.arc(X + cw * (0.27 + 0.46 * dx), Y + ch * (0.14 + 0.24 * dy), r, 0, 2 * Math.PI); ctx.fill(); }
          });
        } else if (c !== " ") {
          ctx.font = font(bold);
          ctx.fillText(c, X, Y + ch / 2);
        }
        x += 1;
      }
    }
  });
}

function bannerField(kind, f, thing, path) {
  const value = thing[f.key];
  if (!isObject(value)) {
    return el("button", { type: "button", class: "quiet", onclick: () => { thing[f.key] = {}; touched(kind); renderForm(); } }, `Add ${f.label.toLowerCase()}`);
  }
  const game = kindOf("game");
  const cfg = game && fileOf(game) ? fileOf(game).data : {};
  const own = isObject(cfg.palettes) ? Object.keys(cfg.palettes) : [];
  const fields = f.fields.map((x) => (x.key === "palette" ? Object.assign({}, x, { options: own.concat(x.options.filter((o) => !own.includes(o))) }) : x));
  const canvas = el("canvas", { class: "banner-canvas", role: "img", "aria-label": `${f.label}, as the game draws it` });
  const note = el("p", { class: "note" });
  const SIZES = [[78, "Desktop"], [40, "Phone"], [24, "24 columns"]];
  let width = state.bannerWidth || 78, drawn = null, timer = null, wait = null;
  const sizes = el("span", { class: "row" }, ...SIZES.map(([w, label]) => el("button", { type: "button", class: "quiet small", "aria-pressed": String(w === width), onclick: (e) => {
    width = state.bannerWidth = w;
    for (const b of sizes.children) b.setAttribute("aria-pressed", String(b === e.currentTarget));
    show();
  } }, label)));
  const play = el("button", { type: "button", class: "quiet small", onclick: () => animate() }, "Play the animation");

  async function show() {
    clearTimeout(timer);
    try { drawn = await api("/api/banner", { pending: pending(), key: f.key, width }); } catch (err) { note.textContent = "It cannot be drawn: " + err.message; return; }
    paintCells(canvas, drawn.rows, width, drawn.size[1] + 2);
    const [w, h] = drawn.size;
    const fell = drawn.style !== drawn.chosen;
    note.textContent = `${drawn.style}, ${w}×${h} on a screen ${width} columns wide` +
      (fell ? `: ${drawn.chosen} does not fit here, so the game writes it plain. A shorter text or a wider screen shows ${drawn.chosen}.` : ".") +
      (drawn.effect && drawn.effect !== "none" ? ` Animation: ${drawn.effect}.` : "");
    play.disabled = !drawn.frames.length;
  }

  function animate() {
    if (!drawn || !drawn.frames.length) return;
    clearTimeout(timer);
    const h = drawn.size[1] + 2;
    let i = 0;
    const step = () => {
      if (i >= drawn.frames.length) { paintCells(canvas, drawn.rows, width, h); return; }
      const [rows, secs] = drawn.frames[i++];
      paintCells(canvas, rows, width, h);
      timer = setTimeout(step, Math.max(16, secs * 1000));
    };
    step();
  }

  const group = el("div", { class: "group" }, ...subform(kind, fields, value, path));
  const later = () => { clearTimeout(wait); wait = setTimeout(show, 250); };
  group.addEventListener("input", later);
  group.addEventListener("change", later);
  show();
  return el("div", { class: "banner-field" }, group, el("div", { class: "banner-preview" }, canvas, el("div", { class: "row" }, sizes, play), note));
}

// The end screen of a game of levels: its settings, and the screen as the game draws it (numbers made up).
function endScreenField(kind, f, thing, path) {
  const value = thing[f.key];
  if (!isObject(value)) {
    return el("button", { type: "button", class: "quiet", onclick: () => { thing[f.key] = { heading: "THE END" }; touched(kind); renderForm(); } }, `Add ${f.label.toLowerCase()}`);
  }
  const canvas = el("canvas", { class: "banner-canvas", role: "img", "aria-label": "The end screen, as the game draws it" });
  const note = el("p", { class: "note" });
  let drawn = null, timer = null, wait = null, at = 0;
  function paint() {
    clearTimeout(timer);
    if (!drawn || !drawn.frames.length) return;
    paintCells(canvas, drawn.frames[at % drawn.frames.length], drawn.size[0], drawn.size[1]);
    if (drawn.every > 0 && drawn.frames.length > 1 && canvas.isConnected) timer = setTimeout(() => { at += 1; paint(); }, drawn.every * 1000);
  }
  async function show() {
    try { drawn = await api("/api/endscreen", { pending: pending(), width: 100, height: 34 }); } catch (err) { note.textContent = "It cannot be drawn: " + err.message; return; }
    at = 0;
    note.textContent = drawn.frames.length ? `On a screen 100×34. The numbers are made up; the game counts the real ones.` +
      (drawn.every > 0 && drawn.frames.length > 1 ? ` The pictures take turns, ${drawn.every} seconds each.` : "") : "Nothing to draw yet.";
    paint();
  }
  const group = el("div", { class: "group" }, ...subform(kind, f.fields, value, path));
  const later = () => { clearTimeout(wait); wait = setTimeout(show, 300); };
  group.addEventListener("input", later);
  group.addEventListener("change", later);
  show();
  return el("div", { class: "banner-field" }, group, el("div", { class: "banner-preview" }, canvas, note));
}

// A sheet of the game's pictures, to look at or to take to another program: a PNG, and an atlas of where each one is.
const SHEETS = { monsters: "Monsters: standing, steps, attack", sprites: "Every sprite", tiles: "Tiles (the game's and the engine's)" };

function base64(buffer) {
  const bytes = new Uint8Array(buffer);
  let text = "";
  for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(text);
}

// A picture file as the editor sends it: a PNG as it is (its colours exact), anything else - or a PNG too big
// to send whole - as the pixels the browser reads from it, made at most 512 pixels on a side.
async function pictureOf(file) {
  const bitmap = await createImageBitmap(file);
  const big = Math.max(bitmap.width, bitmap.height);
  if (file.type === "image/png" && big <= 512) return { send: { png: base64(await file.arrayBuffer()) }, bitmap, w: bitmap.width, h: bitmap.height };
  const k = Math.min(1, 512 / big);
  const w = Math.max(1, Math.round(bitmap.width * k)), h = Math.max(1, Math.round(bitmap.height * k));
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const g = c.getContext("2d");
  g.imageSmoothingEnabled = k < 1;
  g.drawImage(bitmap, 0, 0, w, h);
  return { send: { rgba: base64(g.getImageData(0, 0, w, h).data.buffer), w, h }, bitmap, w, h };
}

async function apiBlob(path, body) {
  if (HOSTED) return api(path, body);
  const res = await fetch(path, { method: "POST", headers: { "X-CLIo-Token": KEY, "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
  return res.blob();
}

function renderSheet(host) {
  const sh = state.sheet;
  const img = el("img", { class: "sheet-image", alt: "The sheet" });
  const note = el("p", { class: "note" });
  const ask = () => ({ pending: pending(), what: sh.what, scale: sh.scale, labels: sh.labels, background: sh.dark ? "dark" : "clear" });
  async function show() {
    note.textContent = "Drawing…";
    try {
      const blob = await apiBlob("/api/sheet", ask());
      if (sh.url) URL.revokeObjectURL(sh.url);
      sh.url = URL.createObjectURL(new Blob([blob], { type: "image/png" }));
      img.src = sh.url;
      const atlas = await api("/api/sheet", Object.assign(ask(), { format: "atlas" }));
      const size = atlas.meta.size;
      note.textContent = `${Object.keys(atlas.frames).length} pictures on ${size.w}×${size.h} pixels, each ${sh.scale} times as big.` +
        " The atlas lists where each one is (the JSON form many engines read).";
    } catch (err) { note.textContent = "It cannot be drawn: " + err.message; }
  }
  const pick = (label, control) => el("label", { class: "row" }, label, " ", control);
  const what = el("select", { onchange: (e) => { sh.what = e.target.value; show(); } },
    ...Object.entries(SHEETS).map(([k, label]) => el("option", { value: k, selected: k === sh.what }, label)));
  const scale = el("select", { onchange: (e) => { sh.scale = Number(e.target.value); show(); } },
    ...[1, 2, 3, 4, 6, 8].map((n) => el("option", { value: String(n), selected: n === sh.scale }, `${n}×`)));
  const labels = el("input", { type: "checkbox", checked: sh.labels, onchange: (e) => { sh.labels = e.target.checked; show(); } });
  const dark = el("input", { type: "checkbox", checked: sh.dark, onchange: (e) => { sh.dark = e.target.checked; show(); } });
  const name = () => `${state.game.id}-${sh.what}`;
  const save = el("button", { type: "button", onclick: async () => {
    try { download(name() + ".png", new Blob([await apiBlob("/api/sheet", ask())], { type: "image/png" })); status(`The sheet was downloaded as ${name()}.png.`); }
    catch (err) { status("Could not download: " + err.message, true); }
  } }, "Download the PNG");
  const atlas = el("button", { type: "button", class: "quiet", onclick: async () => {
    try {
      const a = await api("/api/sheet", Object.assign(ask(), { format: "atlas" }));
      download(name() + ".json", new Blob([JSON.stringify(a, null, 1)], { type: "application/json" }));
      status(`The atlas was downloaded as ${name()}.json.`);
    } catch (err) { status("Could not download: " + err.message, true); }
  } }, "Download the atlas (JSON)");
  const backNote = el("p", { class: "note" });
  const backList = el("ul", { class: "changes" });
  function told(said, r) {                                   // kept on the panel: taking changes in draws it again
    sh.back = { said, r };
    backNote.textContent = said;
    backList.replaceChildren(...(r ? [...r.changed.map((n) => el("li", {}, n)),
      ...r.skipped.map((n) => el("li", { class: "warn" }, "left out: " + n)),
      ...r.unknown.map((n) => el("li", { class: "warn" }, "not in the game: " + n))] : []));
  }
  if (sh.back) told(sh.back.said, sh.back.r);
  const back = el("input", { type: "file", accept: ".png,.json,image/png,application/json", multiple: true, hidden: true, onchange: async (e) => {
    const files = [...e.target.files];
    e.target.value = "";
    const png = files.find((f) => /\.png$/i.test(f.name)), json = files.find((f) => /\.json$/i.test(f.name));
    if (!png || !json) { told("Choose both: the sheet's PNG and the atlas (.json) written with it."); return; }
    told("Reading the sheet…");
    try {
      const result = await api("/api/sheetimport", { pending: pending(), png: base64(await png.arrayBuffer()), atlas: await json.text() });
      const r = result.report;
      told(r.changed.length ? `${r.changed.length} picture${r.changed.length === 1 ? "" : "s"} changed, ${r.same} the same. Nothing is written until you save.`
        : `No picture was changed (${r.same} the same).`, r);
      if (Object.keys(result.files).length) adopt(result);
      else show();
    } catch (err) { told("It cannot be taken back: " + err.message); }
  } });
  host.replaceChildren(el("h2", {}, "A sheet of pictures"),
    el("p", { class: "note" }, "The game's pictures laid out on one image - to look over, to print, or to take to another program. Unsaved changes are on it too."),
    el("div", { class: "row" }, pick("What:", what), pick("Size:", scale), pick("Names under them", labels), pick("Dark background", dark)),
    el("div", { class: "row" }, save, atlas), note, el("div", { class: "sheet-box" }, img),
    el("h3", {}, "Take an edited sheet back in"),
    el("p", { class: "note" }, "Drawn over in another program? Choose the PNG and its atlas (.json) together: the pictures that were changed come back - " +
      "a monster's steps and attack too - with their colours added to the palettes. Keep each picture's place and size; paint in its squares " +
      "(a square of the sheet's size is one pixel). A tile of the engine's that was changed becomes the game's own."),
    el("div", { class: "row" }, back, el("button", { type: "button", class: "quiet", onclick: () => back.click() }, "Choose the PNG and the atlas…")),
    backNote, backList);
  show();
}

// Drawing a sprite: a grid of palette letters, painted with the mouse (or the arrow keys and Space).
function spriteEditor(kind, thing) {
  const tile = kind.key === "tiles";                         // a wall, floor or ceiling of a first-person level
  if (!Array.isArray(thing.pixels)) {
    thing.pixels = tile ? Array(32).fill("a".repeat(32)) : Array(12).fill(CLEAR.repeat(12));
    if (tile && !isObject(thing.palette)) thing.palette = { a: "#3a3e48" };
  }
  if (!thing.palette || typeof thing.palette !== "object") thing.palette = {};
  if (thing.frames !== undefined && !Array.isArray(thing.frames)) delete thing.frames;
  const MAX = 64;
  let colours = {};
  let pen = Object.keys(thing.palette)[0] || CLEAR;
  let mirror = !tile, cursor = [0, 0], painting = false, at = 0, drawn = null, timer = null, wait = null, farWait = null;
  // drawing 0 is "pixels"; the others are "frames", played in turn after it
  const all = () => [thing.pixels].concat(thing.frames || []);
  const cur = () => all()[at] || thing.pixels;
  const cell = () => Math.max(6, Math.min(26, Math.floor(416 / Math.max(width(), thing.pixels.length))));
  const width = () => Math.max(1, ...all().flatMap((d) => d.map((r) => r.length)));
  const grid = el("canvas", { class: "sprite-grid", tabindex: "0", role: "img", "aria-label": "The drawing. Arrow keys move, Space paints." });
  const shown = el("canvas", { class: "banner-canvas", role: "img", "aria-label": "The sprite as the game draws it" });
  const shownNote = el("p", { class: "note" });
  const play = el("button", { type: "button", class: "quiet small", onclick: () => animate() }, "Play the animation");
  const swatches = el("div", { class: "swatches" });
  const picker = el("input", { type: "color", "aria-label": "Colour of the chosen paint" });
  const size = el("span", { class: "row" });
  const tabs = el("div", { class: "row frames" });

  function even() {                                          // every row of every drawing the same length and height
    const w = width(), h = thing.pixels.length;
    thing.pixels = thing.pixels.map((r) => r.padEnd(w, CLEAR));
    if (thing.frames) thing.frames = thing.frames.map((d) => { const out = d.map((r) => r.padEnd(w, CLEAR)).slice(0, h); while (out.length < h) out.push(CLEAR.repeat(w)); return out; });
  }
  function draw() {
    const rows = cur();
    paintSprite(grid, rows, colours, cell());
    const c = grid.getContext("2d");
    if (at > 0) {                                            // onion skin: the drawing before, faintly, where this one is empty
      const before = all()[at - 1];
      c.globalAlpha = 0.28;
      for (let y = 0; y < rows.length; y++) for (let x = 0; x < rows[y].length; x++) {
        const k = before[y] && before[y][x];
        if (rows[y][x] === CLEAR && colours[k]) { c.fillStyle = colours[k]; c.fillRect(x * cell(), y * cell(), cell(), cell()); }
      }
      c.globalAlpha = 1;
    }
    c.strokeStyle = "rgba(0,0,0,0.12)";
    for (let x = 0; x <= width(); x++) { c.beginPath(); c.moveTo(x * cell() + 0.5, 0); c.lineTo(x * cell() + 0.5, grid.height); c.stroke(); }
    for (let y = 0; y <= rows.length; y++) { c.beginPath(); c.moveTo(0, y * cell() + 0.5); c.lineTo(grid.width, y * cell() + 0.5); c.stroke(); }
    if (document.activeElement === grid) { c.strokeStyle = "#2447d6"; c.lineWidth = 2; c.strokeRect(cursor[0] * cell() + 1, cursor[1] * cell() + 1, cell() - 2, cell() - 2); c.lineWidth = 1; }
  }
  // the sprite as the engine draws it, in its style: asked again a moment after each change
  async function show() {
    clearTimeout(timer);
    if (!grid.isConnected) return;                           // another page is shown now: nothing to draw for
    if (tile) return tileShow();
    try { drawn = await api("/api/picture", { pending: pending(), name: state.id }); } catch (err) { shownNote.textContent = "It cannot be drawn: " + err.message; return; }
    const [w, h] = drawn.size;
    paintCells(shown, drawn.rows, w + 4, h + 2);
    const frames = (thing.frames || []).length;
    shownNote.textContent = `${drawn.style}, ${w}×${h} characters` + (drawn.small ? `; ${drawn.small[0]}×${drawn.small[1]} in dots where that is too wide` : "") +
      (drawn.effect && drawn.effect !== "none" ? `. Animation: ${drawn.effect}` : "") + (frames ? `, ${frames + 1} drawings` : "") + ".";
    play.disabled = !drawn.frames.length;
  }
  function later() { clearTimeout(wait); wait = setTimeout(show, 300); }
  function animate() {
    if (!drawn || !drawn.frames.length) return;
    clearTimeout(timer);
    if (tile) {                                                // a tile's drawings change a beat at a time
      let k = 0;
      const beat = () => {
        if (k >= drawn.frames.length) { paintCells(shown, drawn.rows, drawn.cols, drawn.lines); return; }
        paintCells(shown, drawn.frames[k++], drawn.cols, drawn.lines);
        timer = setTimeout(beat, 400);
      };
      return beat();
    }
    const [w, h] = drawn.size;
    let i = 0;
    const step = () => {
      if (i >= drawn.frames.length) { paintCells(shown, drawn.rows, w + 4, h + 2); return; }
      const [rows, secs] = drawn.frames[i++];
      paintCells(shown, rows, w + 4, h + 2);
      timer = setTimeout(step, Math.max(16, secs * 1000));
    };
    step();
  }
  function changed() { touched(kind); later(); farLater(); }
  function set(x, y, letter) {
    const rows = cur();
    const put = (cx) => { if (cx >= 0 && cx < width() && y >= 0 && y < rows.length) rows[y] = rows[y].slice(0, cx) + letter + rows[y].slice(cx + 1); };
    put(x);
    if (mirror) put(width() - 1 - x);
    changed();
    palette();                                              // which colours are in use may have changed
    draw();
  }
  function palette() {
    const used = new Set(all().map((d) => d.join("")).join(""));
    swatches.replaceChildren(
      el("button", { type: "button", class: "swatch clear" + (pen === CLEAR ? " on" : ""), title: "Nothing (rub out)", "aria-label": "Rub out", onclick: () => { pen = CLEAR; palette(); } }),
      ...Object.keys(thing.palette).map((k) => el("button", { type: "button", class: "swatch" + (pen === k ? " on" : ""), style: `background:${colours[k] || "transparent"}`,
        title: `Paint "${k}"${used.has(k) ? "" : " (not used)"}`, "aria-label": `Paint ${k}`, onclick: () => { pen = k; palette(); } })),
      el("button", { type: "button", class: "quiet", onclick: () => {
        const k = [...LETTERS].find((l) => !(l in thing.palette));
        if (!k) return;
        thing.palette[k] = colours[k] = "#8a96a8";
        pen = k;
        changed(); palette(); draw();
      } }, "Add a colour"));
    const mine = pen !== CLEAR;
    picker.hidden = !mine;
    if (mine) picker.value = colours[pen] || "#000000";
    if (mine && !used.has(pen)) swatches.append(el("button", { type: "button", class: "quiet", onclick: () => { delete thing.palette[pen]; delete colours[pen]; pen = CLEAR; changed(); palette(); } }, "Remove this colour"));
  }
  function resize(w, h) {
    w = Math.max(4, Math.min(MAX, w)); h = Math.max(4, Math.min(MAX, h));
    const now = width(), left = Math.floor((w - now) / 2);        // grow and shrink evenly on both sides, so it stays centred
    const fit = (d) => {
      const out = d.map((r) => (left >= 0 ? CLEAR.repeat(left) + r : r.slice(-left)).padEnd(w, CLEAR).slice(0, w));
      while (out.length < h) out.push(CLEAR.repeat(w));
      out.length = h;
      return out;
    };
    thing.pixels = fit(thing.pixels);
    if (thing.frames) thing.frames = thing.frames.map(fit);
    changed(); sizes(); draw();
  }
  function sizes() {
    size.replaceChildren("Width", el("input", { type: "number", min: "4", max: String(MAX), value: String(width()), onchange: (e) => resize(Number(e.target.value) || width(), thing.pixels.length) }),
      "Height", el("input", { type: "number", min: "4", max: String(MAX), value: String(thing.pixels.length), onchange: (e) => resize(width(), Number(e.target.value) || thing.pixels.length) }));
  }
  function frameTabs() {
    const n = all().length;
    tabs.replaceChildren(
      ...all().map((_, i) => el("button", { type: "button", class: "quiet small", "aria-pressed": String(i === at), title: i ? `Drawing ${i + 1}, played after the one before` : "The sprite itself",
        onclick: () => { at = i; frameTabs(); draw(); } }, String(i + 1))),
      el("button", { type: "button", class: "quiet small", onclick: () => {
        thing.frames = (thing.frames || []).slice();
        thing.frames.splice(at, 0, cur().slice());
        at += 1;
        changed(); frameTabs(); draw();
      } }, "Copy this drawing"),
      n > 1 && at > 0 ? el("button", { type: "button", class: "quiet small warn", onclick: () => {
        thing.frames.splice(at - 1, 1);
        if (!thing.frames.length) delete thing.frames;
        at = Math.max(0, at - 1);
        changed(); frameTabs(); palette(); draw();
      } }, "Remove this drawing") : "");
  }
  const at_ = (e) => { const box = grid.getBoundingClientRect(); return [Math.floor((e.clientX - box.left) / (box.width / width())), Math.floor((e.clientY - box.top) / (box.height / thing.pixels.length))]; };
  grid.addEventListener("pointerdown", (e) => { painting = true; grid.setPointerCapture(e.pointerId); cursor = at_(e); set(cursor[0], cursor[1], e.button === 2 ? CLEAR : pen); });
  grid.addEventListener("pointermove", (e) => { if (painting) { cursor = at_(e); set(cursor[0], cursor[1], e.buttons === 2 ? CLEAR : pen); } });
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
  picker.addEventListener("input", () => { if (pen !== CLEAR) { thing.palette[pen] = colours[pen] = picker.value; changed(); palette(); draw(); } });

  const seed = el("input", { type: "text", placeholder: "any words", value: state.id || "", "aria-label": "Words to grow a creature from" });
  const grow = el("button", { type: "button", class: "quiet", onclick: async () => {
    if (thing.pixels.join("").replace(/\./g, "") && !confirm("Replace this drawing (and its colours) with a grown one?")) return;
    try {
      const made = await api("/api/sprite", { seed: seed.value || "nobody", size: Math.min(32, thing.pixels.length) });
      thing.palette = made.palette; thing.pixels = made.pixels; colours = Object.assign({}, made.palette);
      delete thing.frames;
      at = 0;
      pen = Object.keys(thing.palette)[0] || CLEAR;
      changed(); sizes(); frameTabs(); palette(); draw();
    } catch (err) { status("Could not grow a sprite: " + err.message, true); }
  } }, "Grow");
  const tick = el("input", { type: "checkbox", checked: mirror, onchange: (e) => { mirror = e.target.checked; } });

  // ---- a monster grown on a body plan, and how it looks far away in a first-person level
  const body = el("select", { "aria-label": "Body plan" }, ...["biped", "beast", "floater", "crawler", "brute"].map((b) => el("option", { value: b }, b)));
  const tall = el("input", { type: "number", min: "10", max: "48", value: String(Math.max(12, Math.min(48, thing.pixels.length || 18))), "aria-label": "Height in pixels" });
  const growMonster = el("button", { type: "button", class: "quiet", onclick: async () => {
    if (thing.pixels.join("").replace(/\./g, "") && !confirm("Replace this drawing (and its colours) with a grown monster?")) return;
    try {
      const made = await api("/api/monster", { seed: seed.value || state.id || "nobody", body: body.value, size: Number(tall.value) || 18 });
      thing.palette = made.palette; thing.pixels = made.pixels; thing.lod = made.lod;
      if (made.keep) thing.keep = made.keep; else delete thing.keep;
      keep.value = thing.keep || "";
      colours = Object.assign({}, made.palette);
      delete thing.frames;
      at = 0;
      pen = Object.keys(thing.palette)[0] || CLEAR;
      changed(); sizes(); frameTabs(); palette(); draw(); farAway();
    } catch (err) { status("Could not grow a monster: " + err.message, true); }
  } }, "Grow a monster");
  const keep = el("input", { type: "text", class: "code short", value: thing.keep || "", placeholder: "eE", spellcheck: "false",
    "aria-label": "Letters that must stay in the far versions",
    oninput: (e) => { if (e.target.value.trim()) thing.keep = e.target.value.trim(); else delete thing.keep; changed(); } });
  const farBox = el("div", { class: "far" });
  const farNote = el("p", { class: "note" });
  function farLater() { if (!tile) { clearTimeout(farWait); farWait = setTimeout(farAway, 400); } }

  // ---- from a picture: any picture file made a drawing, its background cleared, its colours few
  const fromPic = { picture: null, made: null, points: [] };
  const picFile = el("input", { type: "file", accept: "image/*", hidden: true, onchange: async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    try { fromPic.picture = await pictureOf(file); fromPic.points = []; fromPic.name = file.name; await picMake(); }
    catch (err) { picNote.textContent = "That picture cannot be read: " + err.message; }
  } });
  const picHigh = el("input", { type: "number", min: "4", max: "64", class: "short", value: String(tile ? 32 : Math.max(8, Math.min(64, thing.pixels.length))), "aria-label": "Height in pixels", onchange: () => picMake() });
  const picColours = el("input", { type: "number", min: "2", max: "62", class: "short", value: "16", "aria-label": "Colours at most", onchange: () => picMake() });
  const picCorners = el("input", { type: "checkbox", checked: !tile, onchange: () => picMake() });
  const picOutline = el("input", { type: "checkbox", onchange: () => picMake() });
  const picSource = el("canvas", { class: "sprite-small pick", role: "img", "aria-label": "The picture: click its background to clear it", title: "Click the background to clear it" });
  const picResult = el("canvas", { class: "sprite-small", role: "img", "aria-label": "What it makes" });
  const picNote = el("p", { class: "note" });
  const picUse = el("button", { type: "button", disabled: true, onclick: () => picTake() }, "Use it");
  const picUndo = el("button", { type: "button", class: "quiet small", disabled: true, onclick: () => { fromPic.points.pop(); picMake(); } }, "Undo the last click");
  picSource.addEventListener("click", (e) => {
    const p = fromPic.picture;
    if (!p) return;
    const box = picSource.getBoundingClientRect();
    fromPic.points.push([Math.floor((e.clientX - box.left) / box.width * p.w), Math.floor((e.clientY - box.top) / box.height * p.h)]);
    picMake();
  });
  async function picMake() {
    const p = fromPic.picture;
    if (!p) return;
    const k = Math.min(1, 220 / Math.max(p.w, p.h)) * Math.max(1, Math.floor(220 / Math.max(p.w, p.h)));
    picSource.width = Math.round(p.w * k); picSource.height = Math.round(p.h * k);
    const g = picSource.getContext("2d");
    g.imageSmoothingEnabled = false;
    g.clearRect(0, 0, picSource.width, picSource.height);
    g.drawImage(p.bitmap, 0, 0, picSource.width, picSource.height);
    g.fillStyle = "#ff2fd0";
    for (const [x, y] of fromPic.points) g.fillRect(Math.floor((x + 0.5) * k) - 2, Math.floor((y + 0.5) * k) - 2, 5, 5);
    picUndo.disabled = !fromPic.points.length;
    picNote.textContent = "Making it…";
    try {
      fromPic.made = await api("/api/fromimage", Object.assign({}, p.send, { height: Number(picHigh.value) || null, colours: Number(picColours.value) || 16,
        clear: picCorners.checked ? "edges" : "alpha", clear_at: fromPic.points, outline: picOutline.checked, base: thing.palette }));
      const m = fromPic.made;
      paintSprite(picResult, m.pixels, m.palette, Math.max(2, Math.floor(160 / Math.max(m.size[0], m.size[1]))));
      picNote.textContent = `${fromPic.name}: ${m.source[0]}×${m.source[1]} pixels` + (m.scale > 1 ? `, drawn ${m.scale} times as big` : "") +
        ` - makes ${m.size[0]}×${m.size[1]} in ${m.colours} colours. Click the picture where it should be clear (its background), as often as it needs.`;
      picUse.disabled = false;
    } catch (err) { picNote.textContent = "It cannot be made: " + err.message; picUse.disabled = true; }
  }
  function picTake() {
    const m = fromPic.made;
    if (!m) return;
    const drawing = at === 0 ? "the drawing" : `drawing ${at + 1}`;
    if (cur().join("").replace(/\./g, "") && !confirm(`Replace ${drawing} with this picture?`)) return;
    const shared = (thing.frames || []).length || thing.walk || thing.attack || thing.lod;    // other drawings use its letters
    thing.palette = Object.assign({}, shared ? thing.palette : {}, m.palette);
    if (at === 0) thing.pixels = m.pixels.slice();
    else {                                                   // another drawing: put it on the sprite's own size, feet down
      const w = width(), h = thing.pixels.length;
      const rows = m.pixels.slice(Math.max(0, m.pixels.length - h)).map((r) => {
        const left = Math.max(0, Math.floor((w - r.length) / 2));
        return (CLEAR.repeat(left) + r).slice(0, w).padEnd(w, CLEAR);
      });
      while (rows.length < h) rows.unshift(CLEAR.repeat(w));
      thing.frames[at - 1] = rows;
    }
    even();
    coloursOf(thing.palette).then((c) => { colours = c; pen = Object.keys(thing.palette)[0] || CLEAR; changed(); sizes(); frameTabs(); palette(); draw(); farAway(); });
    status(`The picture is ${drawing} now. Nothing is written until you save.`);
  }
  const fromPicture = el("div", {},
    el("div", { class: "row" }, picFile, el("button", { type: "button", class: "quiet", onclick: () => picFile.click() }, "Choose a picture…"),
      el("label", {}, "Height ", picHigh), el("label", {}, "Colours ", picColours)),
    el("div", { class: "row" }, el("label", { class: "tick" }, picCorners, " Clear the background (the commonest colour at its edges)"), el("label", { class: "tick" }, picOutline, " A dark outline")),
    el("div", { class: "row pic-pair" }, picSource, picResult),
    el("div", { class: "row" }, picUse, picUndo), picNote);

  // ---- a tile: as a level draws it, repeated, or started from one of the engine's
  const where = el("select", { "aria-label": "Shown as", onchange: () => show() },
    ...[["wall", "on the walls"], ["floor", "on the floor"], ["ceiling", "on the ceiling"]].map(([v, l]) => el("option", { value: v }, l)));
  const repeated = el("canvas", { class: "sprite-small", role: "img", "aria-label": "The tile repeated" });
  const engineTile = el("select", { "aria-label": "One of the engine's tiles" });
  if (tile) {
    levelsInfo(true).then((info) => {
      engineTile.replaceChildren(...Object.keys(info.tiles).filter((t) => !info.tiles[t].own || info.tiles[t].engine).sort()
        .map((t) => el("option", { value: t, selected: t === state.id }, t)));
    }).catch(() => {});
  }
  const fromEngine = el("button", { type: "button", class: "quiet", onclick: async () => {
    if (!confirm(`Replace this drawing (and its colours) with the engine's "${engineTile.value}"?`)) return;
    try {
      const made = await api("/api/tile", { name: engineTile.value });
      thing.palette = made.palette; thing.pixels = made.pixels; colours = Object.assign({}, made.palette);
      delete thing.frames;
      at = 0;
      pen = Object.keys(thing.palette)[0] || CLEAR;
      changed(); sizes(); frameTabs(); palette(); draw();
    } catch (err) { status("Could not copy the tile: " + err.message, true); }
  } }, "Draw over it");
  async function tileShow() {
    try { drawn = await api("/api/tileview", { pending: pending(), name: state.id, where: where.value }); }
    catch (err) { shownNote.textContent = "It cannot be drawn: " + err.message; return; }
    paintCells(shown, drawn.rows, drawn.cols, drawn.lines);
    const frames = (thing.frames || []).length;
    shownNote.textContent = `${width()}×${thing.pixels.length} pixels, in a small room ${where.value === "wall" ? "on every wall" : "on every " + where.value} cell` +
      (frames ? `; ${frames + 1} drawings, one a beat` : "") + ".";
    play.disabled = !drawn.frames.length;
    const w = width(), h = thing.pixels.length, rows = [];
    for (let y = 0; y < h * 2; y++) rows.push(thing.pixels[y % h].repeat(3));
    paintSprite(repeated, rows, colours, Math.max(2, Math.floor((6 * 16) / Math.max(w, h))), "#0f1724");
  }

  async function farAway() {
    if (tile) return;
    let res;
    try { res = await api("/api/distances", { sprite: { pixels: thing.pixels, palette: colours, lod: thing.lod, keep: thing.keep } }); }
    catch (err) { farNote.textContent = "It cannot be drawn: " + err.message; return; }
    const views = res.distances.map((d) => {
      const c = el("canvas", { class: "far-view", role: "img",
        title: `${d.cells} cell${d.cells === 1 ? "" : "s"} away: ${d.drawing ? "far version " + d.drawing + (d.made ? " (made by the game)" : "") : "the drawing itself"}` });
      paintColours(c, d.pixels, 4);
      return el("figure", { class: "far-one" }, c, el("figcaption", {}, `${d.cells}`));
    });
    const lods = (thing.lod || []).map((l, i) => lodCanvas(l, i));
    farBox.replaceChildren(
      el("div", { class: "far-row" }, ...views),
      el("p", { class: "note" }, thing.lod
        ? "Far versions, smallest last: click to paint with the chosen colour, right button to rub out."
        : "No far versions are kept: the game makes them when it loads. Keep them to draw over them."),
      el("div", { class: "far-row" }, ...lods),
      el("div", { class: "row" },
        el("button", { type: "button", class: "quiet small", onclick: async () => {
          try { thing.lod = (await api("/api/far", { pixels: thing.pixels, keep: thing.keep || "" })).lod; touched(kind); later(); farAway(); }
          catch (err) { status("Could not make far versions: " + err.message, true); }
        } }, thing.lod ? "Make them again from the drawing" : "Keep them, to draw over"),
        thing.lod ? el("button", { type: "button", class: "quiet small warn", onclick: () => { delete thing.lod; touched(kind); later(); farAway(); } },
          "Let the game make them") : ""));
    farNote.textContent = "1 to 6: the sprite one to six cells away, as a level draws it at 80 columns. " +
      "Far away a sprite is drawn from a smaller drawing; the letters to keep (eyes, a mouth) win when it shrinks.";
  }
  function lodCanvas(l, i) {
    const c = el("canvas", { class: "sprite-small lod", role: "img", "aria-label": `Far version ${i + 1}`, title: `Far version ${i + 1}: ${l.pixels[0].length}×${l.pixels.length}` });
    const paint = () => paintSprite(c, l.pixels, colours, 8, "#0f1724");
    paint();
    c.addEventListener("pointerdown", (e) => {
      const box = c.getBoundingClientRect();
      const w = Math.max(...l.pixels.map((r) => r.length)), h = l.pixels.length;
      const x = Math.floor((e.clientX - box.left) / (box.width / w)), y = Math.floor((e.clientY - box.top) / (box.height / h));
      const letter = e.button === 2 ? CLEAR : pen;
      const put = (cx) => { if (cx >= 0 && cx < w && y >= 0 && y < h) l.pixels[y] = l.pixels[y].padEnd(w, CLEAR).slice(0, cx) + letter + l.pixels[y].padEnd(w, CLEAR).slice(cx + 1); };
      put(x);
      if (mirror) put(w - 1 - x);
      touched(kind); paint(); farLater();
    });
    c.addEventListener("contextmenu", (e) => e.preventDefault());
    return el("figure", { class: "far-one" }, c, el("figcaption", {}, `${i + 1}`));
  }

  even();
  coloursOf(thing.palette).then((c) => { colours = c; palette(); draw(); farAway(); });
  sizes();
  frameTabs();
  show();
  // the fields below the drawing (style, animation...) change the picture too
  setTimeout(() => {
    const form = grid.closest(".sheet") && grid.closest(".sheet").parentElement;
    if (form) { form.addEventListener("change", (e) => { if (!grid.contains(e.target)) later(); }); form.addEventListener("input", (e) => { if (e.target.type === "number") later(); }); }
  }, 0);
  if (tile) {
    return el("div", { class: "sheet sprite" },
      el("div", { class: "sprite-row" }, grid, el("div", {},
        el("h3", {}, "Paint"), swatches, el("div", { class: "row" }, picker, el("label", { class: "tick" }, tick, " Mirror left and right")),
        el("h3", {}, "Size"), size,
        el("h3", {}, "Drawings"), tabs,
        el("h3", {}, "Start from the engine's"), el("div", { class: "row" }, engineTile, fromEngine),
        el("h3", {}, "From a picture"), fromPicture)),
      el("h3", {}, "In a level"), el("div", { class: "row" }, where, play),
      el("div", { class: "banner-preview" }, shown, shownNote),
      el("h3", {}, "Repeated"), repeated,
      el("p", { class: "note" }, "Click or drag to paint, right button to rub out. A tile is drawn on a cell's face whatever its size (32×32 is the engine's). " +
        `Use it in a level's legend: {"wall": "${state.id || "name"}"}, {"floor": ...} or {"ceiling": ...}, or as the floor or ceiling of a whole level. ` +
        "A tile named like one of the engine's (steel, screens, hazard, door, door_x, sealed, exit, fist, shoot...) takes its place everywhere. " +
        "Rubbed-out pixels show what is behind a wall (bars, windows); the wall still stops shots and sight. More drawings change one a beat."));
  }
  return el("div", { class: "sheet sprite" },
    el("div", { class: "sprite-row" }, grid, el("div", {},
      el("h3", {}, "Paint"), swatches, el("div", { class: "row" }, picker, el("label", { class: "tick" }, tick, " Mirror left and right")),
      el("h3", {}, "Size"), size,
      el("h3", {}, "Drawings"), tabs,
      el("h3", {}, "Grow one from words"), el("div", { class: "row" }, seed, grow),
      el("h3", {}, "Grow a monster"), el("div", { class: "row" }, body, tall, growMonster),
      el("h3", {}, "From a picture"), fromPicture)),
    el("h3", {}, "As the game draws it"),
    el("div", { class: "banner-preview" }, shown, el("div", { class: "row" }, play), shownNote),
    el("h3", {}, "Far away, in a first-person level"),
    el("div", { class: "row" }, el("label", {}, "Letters to keep far away ", keep)),
    farBox, farNote,
    el("p", { class: "note" }, "Click or drag to paint, right button to rub out. With the keyboard: arrow keys move, Space paints, Delete rubs out. " +
      "More drawings play in turn after the first (how fast is set above); the one before shows faintly while you draw. " +
      `Use it as a picture anywhere art goes: "art": "${state.id || "name"}" in a scene or an item, "portrait" on a character, or name it "title" for the title screen; ` +
      "an enemy fights with it as its \"sprite\"."));
}

// ---------------------------------------------------------------------- first-person levels: the map painter
// A level's map is rows of characters. What a character means comes from the level's legend, else from the engine's
// (sent by /api/levels, with small pictures of the tiles and of the monsters' and items' sprites). The picture of the
// level from any cell, and the level bot's play, come from the engine itself.
let levelInfo = null;
const levelUi = {};                                            // per level: pen, tool, the cell looked from, style
const artCache = new Map();
async function levelsInfo(fresh) {
  if (!levelInfo || fresh) { levelInfo = await api("/api/levels", { pending: pending() }); artCache.clear(); }
  return levelInfo;
}
const STEPS = { n: [0, -1], e: [1, 0], s: [0, 1], w: [-1, 0] };
const TURN = "nesw";
const FREE_CHARS = "abcdefghijklmnopqrstuvwxyzABCDFGHIJKLMNOQTUVYZ0123456789!$&*:;?^_|<>/";

function specOf(thing, info, ch) {
  const legend = isObject(thing.legend) ? thing.legend : {};
  let spec = ch in legend ? legend[ch] : info.legend[ch];
  if (spec === undefined || spec === null) return null;
  if (typeof spec === "string") spec = info.things[spec] && info.things[spec].kind === "monster" ? { monster: spec } : { item: spec };
  return isObject(spec) ? spec : null;
}

function sortOf(spec) {
  if (!spec) return "unknown";
  if (spec.monster) return "monster";
  if (spec.item) return "item";
  if (spec.start) return "start";
  if (spec.exit) return "exit";
  if (spec.switch) return "switch";
  if (spec.crate) return "crate";
  if (spec.plate) return "plate";
  if (spec.teleport) return "pad";
  if (spec.lift) return "lift";
  if (spec.door) return "door";
  if (spec.panel) return "panel";
  if (spec.toxic) return "toxic";
  if (spec.wall || spec.texture || spec.opens_on) return "wall";
  return "floor";
}
const SORTS = [["floor", "Floor"], ["toxic", "Toxic floor"], ["wall", "Wall"], ["door", "Door"], ["panel", "Secret wall"],
  ["monster", "Monster"], ["item", "Item"], ["start", "Start"], ["exit", "Exit switch"], ["switch", "Switch (sets off an event)"],
  ["crate", "Crate (pushed)"], ["plate", "Pressure plate"], ["pad", "Teleporter pad"], ["lift", "Lift"]];
const solidSort = (k) => ["wall", "panel", "exit", "switch", "unknown"].includes(k);
const blocksWalk = (k) => solidSort(k) || k === "crate";

function tileOf(spec) {                                        // the tile a wall-like cell is drawn with
  const k = sortOf(spec);
  if (k === "door") return spec.sealed || (spec.opens_on && !spec.key) ? "sealed" : spec.key ? "door_" + spec.key : "door";
  if (k === "panel") return spec.panel === "shoot" ? "shoot" : "fist";
  if (k === "exit") return "exit";
  if (k === "switch") return "switch";
  if (k === "wall") return spec.wall || spec.texture || "steel";
  return null;
}

function describe(spec, info) {
  if (!spec) return "not explained: add it to the legend";
  const name = (id) => (info.things[id] ? info.things[id].name : `${id} (not found)`);
  const k = sortOf(spec);
  const what = {
    monster: () => name(spec.monster) + (info.things[spec.monster] && info.things[spec.monster].boss ? " (boss)" : ""),
    item: () => name(spec.item), start: () => "where the player starts", exit: () => (spec.exit === "secret" ? "the secret exit switch" : "the exit switch"),
    switch: () => `a switch: sets off ${spec.switch}` + (spec.label ? ` (labelled ${spec.label})` : ""),
    door: () => (spec.key ? `door: needs the ${spec.key} key` : spec.sealed || spec.opens_on ? "sealed door" : "door") + (spec.open ? ", open" : ""),
    panel: () => (spec.panel === "shoot" ? "dented vent: shoot it (secret)" : "hollow wall: punch it (secret)"),
    toxic: () => "toxic floor", wall: () => `wall: ${spec.wall || spec.texture || "steel"}`, floor: () => "floor",
    crate: () => (spec.crate === "heavy" ? "a container: only a vehicle shoves it" : "a crate: walk into it to push it"),
    plate: () => `pressure plate "${spec.plate}"`,
    pad: () => `teleporter pad "${spec.teleport}"` + (spec.arrive ? ", arrivals only" : "") + (spec.facing ? `, facing ${spec.facing}` : ""),
    lift: () => `lift "${spec.lift}", deck ${spec.deck || 0}`,
  }[k]();
  const more = [];
  if (spec.on_enter) more.push(`sets off ${spec.on_enter}`);
  if (spec.on_pickup) more.push(`taken: sets off ${spec.on_pickup}`);
  if (spec.wake_on) more.push(`wakes on ${spec.wake_on}`);
  if (spec.awake) more.push("awake");
  if (spec.opens_on && k !== "door") more.push(`opens on ${spec.opens_on}`);
  if (spec.opens_on && k === "door") more.push(`opens on ${spec.opens_on}`);
  if (spec.closes_on) more.push(`shuts on ${spec.closes_on}`);
  if (spec.open_while) more.push(`open while plate "${spec.open_while}" is down`);
  if (spec.secret && k !== "panel") more.push("a secret area");
  if (spec.oil) more.push("oil on the floor (slippery, burns)");
  else if (spec.slick) more.push("slick floor (things slide)");
  if (spec.conveyor) more.push(`a belt moving ${({ n: "north", e: "east", s: "south", w: "west" })[String(spec.conveyor)[0]] || spec.conveyor}`);
  if (spec.roll) more.push(`rolls ${({ n: "north", e: "east", s: "south", w: "west" })[String(spec.roll)[0]] || spec.roll} when it wakes`);
  if (spec.sky) more.push("open to the sky");
  if (spec.floor) more.push(`floor ${spec.floor}`);
  if (spec.ceiling) more.push(`ceiling ${spec.ceiling}`);
  return what + (more.length ? "; " + more.join(", ") : "");
}

function tileArt(info, name, size) {
  const key = `t/${name}/${size}`;
  if (artCache.has(key)) return artCache.get(key);
  const t = info.tiles[name] || info.tiles.steel;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  const n = t.thumb.length || 1;
  t.thumb.forEach((row, y) => row.forEach((col, x) => {
    if (col) { g.fillStyle = col; g.fillRect(Math.floor((x * size) / n), Math.floor((y * size) / n), Math.ceil(size / n), Math.ceil(size / n)); }
  }));
  artCache.set(key, c);
  return c;
}

function thingArt(info, id, size) {
  const key = `s/${id}/${size}`;
  if (artCache.has(key)) return artCache.get(key);
  const t = info.things[id];
  let c = null;
  if (t && t.picture && t.picture.length) {
    const h = t.picture.length, w = Math.max(...t.picture.map((r) => r.length));
    const k = Math.min((size - 2) / h, (size - 2) / w);
    c = document.createElement("canvas");
    c.width = c.height = size;
    const g = c.getContext("2d");
    const ox = (size - w * k) / 2, oy = size - 1 - h * k;
    t.picture.forEach((row, y) => row.forEach((col, x) => {
      if (col) { g.fillStyle = col; g.fillRect(ox + x * k, oy + y * k, Math.max(1, k), Math.max(1, k)); }
    }));
  }
  artCache.set(key, c);
  return c;
}

function paintCell(g, info, thing, ch, x, y, cs) {
  const spec = specOf(thing, info, ch);
  const k = sortOf(spec);
  const X = x * cs, Y = y * cs;
  const tile = tileOf(spec);
  if (tile) g.drawImage(tileArt(info, tile, cs), X, Y);
  else {
    const floor = (spec && spec.floor) || (k !== "toxic" ? thing.floor : null);
    if (floor && info.tiles[floor]) g.drawImage(tileArt(info, floor, cs), X, Y);
    else { g.fillStyle = k === "toxic" ? "#3a9a32" : (x + y) % 2 ? "#3d3830" : "#35312a"; g.fillRect(X, Y, cs, cs); }
    if (k === "monster" || k === "item") {
      const art = thingArt(info, spec.monster || spec.item, cs);
      if (art) g.drawImage(art, X, Y);
      else { g.fillStyle = k === "monster" ? "#ff6b5e" : "#f0c85a"; g.font = `${Math.round(cs * 0.8)}px ui-monospace, monospace`; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(ch, X + cs / 2, Y + cs / 2 + 1); }
    }
    if (spec && spec.oil) { g.fillStyle = "#211c24"; g.fillRect(X, Y, cs, cs); g.fillStyle = "#4a3a64"; g.fillRect(X + cs * 0.2, Y + cs * 0.55, cs * 0.35, Math.max(1, cs / 10)); }
    else if (spec && spec.slick) { g.fillStyle = "#3e5462"; g.fillRect(X, Y, cs, cs); g.fillStyle = "#80a0b0"; g.fillRect(X + cs * 0.15, Y + cs * 0.3, cs * 0.5, Math.max(1, cs / 10)); }
    if (spec && spec.conveyor && !["monster", "item", "crate"].includes(k)) {
      const d = "nesw".indexOf(String(spec.conveyor)[0]);
      g.fillStyle = "#2e3034"; g.fillRect(X, Y, cs, cs);
      g.save(); g.translate(X + cs / 2, Y + cs / 2); g.rotate((Math.max(0, d) - 1) * Math.PI / 2);
      g.strokeStyle = "#d6aa2c"; g.lineWidth = Math.max(1, cs / 7); g.beginPath();
      g.moveTo(-cs * 0.22, -cs * 0.28); g.lineTo(cs * 0.12, 0); g.lineTo(-cs * 0.22, cs * 0.28); g.stroke(); g.restore(); g.lineWidth = 1;
    }
    if (k === "plate") { g.fillStyle = "#968046"; g.fillRect(X + cs * 0.2, Y + cs * 0.2, cs * 0.6, cs * 0.6); }
    if (k === "pad") { g.strokeStyle = "#4fd8ea"; g.lineWidth = Math.max(1, cs / 8); g.beginPath(); g.arc(X + cs / 2, Y + cs / 2, cs * 0.32, 0, 2 * Math.PI); g.stroke(); g.lineWidth = 1; }
    if (k === "lift") { g.strokeStyle = "#d7af28"; g.lineWidth = Math.max(1, cs / 7); g.strokeRect(X + 2, Y + 2, cs - 4, cs - 4); g.lineWidth = 1; }
    if (k === "crate") {
      const art = thingArt(info, spec.crate === "heavy" && info.things.container ? "container" : "crate", cs);
      if (art) g.drawImage(art, X, Y);
      else { g.fillStyle = "#7a5c3a"; g.fillRect(X + cs * 0.12, Y + cs * 0.12, cs * 0.76, cs * 0.76); g.strokeStyle = "#4f3a24"; g.strokeRect(X + cs * 0.12 + 0.5, Y + cs * 0.12 + 0.5, cs * 0.76, cs * 0.76); }
    }
    if (k === "start") {
      const f = TURN.indexOf(String(thing.facing || "n")[0]);
      g.fillStyle = "#ffffff"; g.font = `bold ${Math.round(cs * 0.85)}px ui-monospace, monospace`; g.textAlign = "center"; g.textBaseline = "middle";
      g.fillText("▲►▼◄"[Math.max(0, f)], X + cs / 2, Y + cs / 2 + 1);
    }
  }
  if (!spec) { g.fillStyle = "#c62828"; g.fillRect(X, Y, cs, cs); g.fillStyle = "#fff"; g.font = `bold ${Math.round(cs * 0.75)}px ui-monospace, monospace`; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(ch === " " ? "·" : ch, X + cs / 2, Y + cs / 2 + 1); }
  if (spec && EVENT_KEYS.concat(["switch"]).some((key) => spec[key])) {             // something happens here: a corner, in the event's colour
    g.fillStyle = "#ffd54a";
    g.beginPath(); g.moveTo(X + cs, Y); g.lineTo(X + cs - Math.max(4, cs / 3), Y); g.lineTo(X + cs, Y + Math.max(4, cs / 3)); g.fill();
  }
  if (k === "panel") { g.fillStyle = "#c79bff"; g.fillRect(X + 1, Y + cs - 4, 3, 3); }
}
const EVENT_KEYS = ["on_enter", "on_pickup", "opens_on", "closes_on", "wake_on"];

function levelEditor(kind, thing, id) {
  if (!Array.isArray(thing.map) || !thing.map.length) {
    thing.map = ["#####E#####", "#.........#", "#.........#", "#....@....#", "###########"];
    touched(kind);
  }
  const ui = levelUi[id] = levelUi[id] || { pen: "#", tool: "paint", cam: null, style: "pixel" };
  let info = null, cs = 16, painting = false, wait = null;
  const W = () => Math.max(...thing.map.map((r) => r.length));
  const grid = el("canvas", { class: "level-grid", tabindex: "0", role: "img", "aria-label": "The map. Click or drag to paint; right button paints floor." });
  const hover = el("p", { class: "note" }, "Point at a cell to see what it is.");
  const palette = el("div", { class: "palette-list" });
  const editBox = el("div", { class: "legend-edit" });
  const eventsBox = el("div", {});
  const tilesBox = el("div", { class: "row" });
  const sizeBox = el("span", { class: "row" });
  const toolBox = el("span", { class: "row" });
  const view = el("canvas", { class: "banner-canvas level-view", tabindex: "0", role: "img", "aria-label": "The level seen from the chosen cell. Arrow keys walk and turn." });
  const viewNote = el("p", { class: "note" });
  const styleSel = el("select", { "aria-label": "Drawn as", onchange: (e) => { ui.style = e.target.value; look(); } },
    ...["pixel", "dots", "dots-fill"].map((s) => el("option", { value: s, selected: ui.style === s }, s)));
  const checkOut = el("div", {});

  const used = () => new Set(thing.map.join(""));
  const legend = () => (isObject(thing.legend) ? thing.legend : (thing.legend = {}));
  function changed() { touched(kind); clearTimeout(wait); wait = setTimeout(look, 350); }
  function startCell() {
    for (let y = 0; y < thing.map.length; y++) for (let x = 0; x < thing.map[y].length; x++) {
      if (sortOf(specOf(thing, info, thing.map[y][x])) === "start") return [x, y];
    }
    return [1, 1];
  }
  function draw() {
    const w = W(), h = thing.map.length;
    cs = Math.max(8, Math.min(22, Math.floor(620 / Math.max(w, h))));
    grid.width = w * cs; grid.height = h * cs;
    const g = grid.getContext("2d");
    g.imageSmoothingEnabled = false;
    g.fillStyle = "#11141a"; g.fillRect(0, 0, grid.width, grid.height);
    thing.map.forEach((row, y) => { for (let x = 0; x < w; x++) paintCell(g, info, thing, x < row.length ? row[x] : " ", x, y, cs); });
    g.strokeStyle = "rgba(0,0,0,0.25)";
    for (let x = 0; x <= w; x++) { g.beginPath(); g.moveTo(x * cs + 0.5, 0); g.lineTo(x * cs + 0.5, grid.height); g.stroke(); }
    for (let y = 0; y <= h; y++) { g.beginPath(); g.moveTo(0, y * cs + 0.5); g.lineTo(grid.width, y * cs + 0.5); g.stroke(); }
    if (ui.cam) {                                              // where the picture below is seen from
      const [x, y, f] = [ui.cam.x, ui.cam.y, ui.cam.f];
      g.strokeStyle = "#4fc3ff"; g.lineWidth = 2; g.strokeRect(x * cs + 1, y * cs + 1, cs - 2, cs - 2); g.lineWidth = 1;
      const [dx, dy] = STEPS[f];
      g.fillStyle = "#4fc3ff"; g.beginPath();
      const cx = x * cs + cs / 2, cy = y * cs + cs / 2;
      g.moveTo(cx + dx * cs * 0.45, cy + dy * cs * 0.45); g.lineTo(cx - dy * cs * 0.25, cy + dx * cs * 0.25); g.lineTo(cx + dy * cs * 0.25, cy - dx * cs * 0.25); g.fill();
    }
  }
  function put(x, y, ch) {
    if (y < 0 || y >= thing.map.length || x < 0 || x >= W()) return;
    const row = thing.map[y].padEnd(W(), "#");
    if (row[x] === ch) return;
    thing.map[y] = row.slice(0, x) + ch + row.slice(x + 1);
    changed(); draw(); swatches();
  }
  const cellAt = (e) => { const b = grid.getBoundingClientRect(); return [Math.floor((e.clientX - b.left) / (b.width / W())), Math.floor((e.clientY - b.top) / (b.height / thing.map.length))]; };
  grid.addEventListener("pointerdown", (e) => {
    const [x, y] = cellAt(e);
    if (ui.tool === "look") { ui.cam = { x, y, f: ui.cam ? ui.cam.f : String(thing.facing || "n")[0] }; draw(); look(); return; }
    painting = true; grid.setPointerCapture(e.pointerId); put(x, y, e.button === 2 ? "." : ui.pen);
  });
  grid.addEventListener("pointermove", (e) => {
    const [x, y] = cellAt(e);
    const ch = (thing.map[y] || "")[x];
    if (ch !== undefined) hover.textContent = `(${x}, ${y})  ${ch === " " ? "space" : ch}: ${describe(specOf(thing, info, ch), info)}`;
    if (painting) put(x, y, e.buttons === 2 ? "." : ui.pen);
  });
  grid.addEventListener("pointerup", () => { painting = false; });
  grid.addEventListener("contextmenu", (e) => e.preventDefault());

  function swatch(ch) {
    const c = el("canvas", { width: "18", height: "18", "aria-hidden": "true" });
    paintCell(c.getContext("2d"), info, thing, ch, 0, 0, 18);
    return c;
  }
  function swatches() {
    const own = Object.keys(legend());
    const engine = Object.keys(info.legend).filter((ch) => ch !== " " && !own.includes(ch));
    const inMap = used();
    const button = (ch) => el("button", { type: "button", class: "pal" + (ui.pen === ch ? " on" : ""), title: describe(specOf(thing, info, ch), info),
      onclick: () => { ui.pen = ch; ui.tool = "paint"; tools(); swatches(); edit(); } },
      swatch(ch), el("code", {}, ch), el("span", { class: inMap.has(ch) ? "" : "unused" }, describe(specOf(thing, info, ch), info)));
    const unknown = [...inMap].filter((ch) => !specOf(thing, info, ch));
    palette.replaceChildren(
      el("p", { class: "note" }, "This level's characters"), ...own.map(button),
      el("button", { type: "button", class: "quiet small", onclick: () => {
        const ch = [...FREE_CHARS].find((c) => !(c in legend()) && !(c in info.legend) && !inMap.has(c));
        if (!ch) return;
        legend()[ch] = {};
        ui.pen = ch;
        changed(); swatches(); edit();
      } }, "Add a character"),
      ...(unknown.length ? [el("p", { class: "note bad" }, `Not explained: ${unknown.map((c) => (c === " " ? "space" : c)).join(" ")}`)] : []),
      el("p", { class: "note" }, "The engine's characters"), ...engine.map(button));
  }
  function tools() {
    const radio = (value, label) => el("label", { class: "tick" }, el("input", { type: "radio", name: `tool-${id}`, checked: ui.tool === value,
      onchange: () => { ui.tool = value; } }), " " + label);
    toolBox.replaceChildren(radio("paint", "Paint"), radio("look", "Look from a cell"));
  }
  function sizes() {
    const resize = (w, h) => {
      w = Math.max(3, Math.min(120, w)); h = Math.max(3, Math.min(120, h));
      thing.map = thing.map.slice(0, h).map((r) => r.padEnd(w, "#").slice(0, w));
      while (thing.map.length < h) thing.map.push("#".repeat(w));
      changed(); sizes(); draw();
    };
    sizeBox.replaceChildren("Width", el("input", { type: "number", min: "3", max: "120", value: String(W()), onchange: (e) => resize(Number(e.target.value) || W(), thing.map.length) }),
      "Height", el("input", { type: "number", min: "3", max: "120", value: String(thing.map.length), onchange: (e) => resize(W(), Number(e.target.value) || thing.map.length) }));
  }

  // ---- what the chosen character is
  const events = () => [...new Set([...Object.keys(isObject(thing.events) ? thing.events : {}),
    ...Object.values(legend()).filter(isObject).flatMap((s) => EVENT_KEYS.concat(["switch"]).map((k) => s[k]).filter(Boolean))])];
  function tileSelect(value, set, none) {
    return el("select", { onchange: (e) => set(e.target.value) }, el("option", { value: "", selected: !value }, none || "the engine's"),
      ...Object.keys(info.tiles).sort().map((t) => el("option", { value: t, selected: t === value }, t + (info.tiles[t].own ? " (this game's)" : ""))),
      value && !info.tiles[value] ? el("option", { value, selected: true }, `${value} (not found)`) : null);
  }
  function eventInput(value, set) {
    const listId = `ev-${id}`;
    return el("span", {}, el("input", { type: "text", class: "code short", list: listId, value: value || "", placeholder: "event", oninput: (e) => set(e.target.value.trim()) }),
      el("datalist", { id: listId }, ...events().map((v) => el("option", { value: v }))));
  }
  function edit() {
    const ch = ui.pen;
    const mine = ch in legend();
    const spec = specOf(thing, info, ch) || {};
    const head = el("h3", {}, `${ch === " " ? "space" : ch}: ${describe(specOf(thing, info, ch), info)}`);
    if (!mine) {
      editBox.replaceChildren(head, el("p", { class: "note" }, "The engine's meaning. Give it another in this level:"),
        el("button", { type: "button", class: "quiet", onclick: () => { legend()[ch] = JSON.parse(JSON.stringify(spec)); changed(); swatches(); edit(); } }, "Change its meaning here"));
      return;
    }
    const raw = legend()[ch];
    const s = typeof raw === "string" ? (info.things[raw] && info.things[raw].kind === "monster" ? { monster: raw } : { item: raw }) : Object.assign({}, raw);
    const write = () => {                                     // a monster or an item with nothing more is written as its id alone
      const keys = Object.keys(s).filter((k) => s[k] !== "" && s[k] !== false && s[k] !== undefined && s[k] !== null && !(k === "deck" && s[k] === 0));
      const clean = Object.fromEntries(keys.map((k) => [k, s[k]]));
      legend()[ch] = keys.length === 1 && (clean.monster || clean.item) ? (clean.monster || clean.item) : clean;
      changed(); draw(); swatches(); head.textContent = `${ch}: ${describe(specOf(thing, info, ch), info)}`;
    };
    const sort = sortOf(s);
    const setSort = (k) => {
      for (const key of Object.keys(s)) if (!EVENT_KEYS.includes(key) && key !== "floor" && key !== "ceiling") delete s[key];
      if (k === "toxic") s.toxic = true;
      if (k === "wall") s.wall = "steel";
      if (k === "door") s.door = true;
      if (k === "panel") s.panel = "fist";
      if (k === "monster") s.monster = Object.keys(info.things).find((t) => info.things[t].kind === "monster") || "";
      if (k === "item") s.item = Object.keys(info.things).find((t) => info.things[t].kind === "item") || "";
      if (k === "start") s.start = true;
      if (k === "exit") s.exit = true;
      if (k === "switch") s.switch = "switch";
      if (k === "crate") s.crate = true;
      if (k === "plate") s.plate = "plate";
      if (k === "pad") s.teleport = "pad";
      if (k === "lift") { s.lift = "lift"; s.deck = 0; }
      write(); edit();
    };
    const rows = [field("Is", el("select", { onchange: (e) => setSort(e.target.value) }, ...SORTS.map(([k, label]) => el("option", { value: k, selected: k === sort }, label))))];
    const choose = (key, kindName) => el("select", { onchange: (e) => { s[key] = e.target.value; write(); } },
      ...Object.keys(info.things).filter((t) => info.things[t].kind === kindName).map((t) => el("option", { value: t, selected: t === s[key] }, `${info.things[t].name} (${t})`)));
    const evRow = (key, label) => rows.push(field(label, eventInput(s[key], (v) => { s[key] = v; write(); })));
    if (sort === "monster") {
      rows.push(field("Monster", choose("monster", "monster"))); evRow("wake_on", "Wakes when this happens");
      rows.push(field("Awake from the start", el("input", { type: "checkbox", checked: !!s.awake, onchange: (e) => { s.awake = e.target.checked; write(); } })));
      rows.push(field("A ball: rolls this way when it wakes", el("select", { onchange: (e) => { s.roll = e.target.value; write(); } },
        ...["", "n", "e", "s", "w"].map((f) => el("option", { value: f, selected: (s.roll || "") === f }, f || "stays")))));
    }
    if (sort === "switch") {
      evRow("switch", "Throwing it sets off");
      rows.push(field("Label on it (a few letters)", el("input", { type: "text", class: "code short", maxlength: "8", value: s.label || "",
        oninput: (e) => { s.label = e.target.value.trim(); write(); } })));
    }
    if (sort === "item") { rows.push(field("Item", choose("item", "item"))); evRow("on_pickup", "Taking it sets off"); }
    if (sort === "wall") { rows.push(field("Tile", tileSelect(s.wall || s.texture, (v) => { delete s.texture; s.wall = v || "steel"; write(); }, "steel"))); evRow("opens_on", "Opens (becomes floor) when this happens"); }
    if (sort === "door") {
      rows.push(field("Needs the key", el("select", { onchange: (e) => { s.key = e.target.value; write(); } }, ...["", "r", "w", "x"].map((k) => el("option", { value: k, selected: (s.key || "") === k }, k || "no key")))));
      evRow("opens_on", "Opens when this happens (sealed until then)"); evRow("closes_on", "Shuts for good when this happens");
      rows.push(field("Open only while a plate is down", el("input", { type: "text", class: "code short", value: s.open_while || "", placeholder: "plate",
        oninput: (e) => { s.open_while = e.target.value.trim(); write(); } })));
      rows.push(field("Open from the start", el("input", { type: "checkbox", checked: !!s.open, onchange: (e) => { s.open = e.target.checked; write(); } })));
    }
    if (sort === "crate") rows.push(field("Heavy: a container only a vehicle can shove", el("input", { type: "checkbox",
      checked: s.crate === "heavy", onchange: (e) => { s.crate = e.target.checked ? "heavy" : true; write(); edit(); } })));
    if (sort === "plate") rows.push(field("Its name (doors and walls open while it is down)", el("input", { type: "text", class: "code short", value: s.plate || "",
      oninput: (e) => { s.plate = e.target.value.trim() || "plate"; write(); } })));
    if (sort === "pad") {
      rows.push(field("Its name (pads of one name lead to each other)", el("input", { type: "text", class: "code short", value: s.teleport || "",
        oninput: (e) => { s.teleport = e.target.value.trim() || "pad"; write(); } })));
      rows.push(field("Only arrives here", el("input", { type: "checkbox", checked: !!s.arrive, onchange: (e) => { s.arrive = e.target.checked; write(); } })));
      rows.push(field("Faces on arrival", el("select", { onchange: (e) => { s.facing = e.target.value; write(); } },
        ...["", "n", "e", "s", "w"].map((f) => el("option", { value: f, selected: (s.facing || "") === f }, f || "as before")))));
    }
    if (sort === "lift") {
      rows.push(field("Its name (the two ends of a lift)", el("input", { type: "text", class: "code short", value: s.lift || "",
        oninput: (e) => { s.lift = e.target.value.trim() || "lift"; write(); } })));
      rows.push(field("Deck (the lower end rides down to it)", el("input", { type: "number", value: String(s.deck || 0), oninput: (e) => { s.deck = Number(e.target.value) || 0; write(); } })));
    }
    if (sort === "exit") rows.push(field("The secret exit (the scene's \"on_secret_exit\" runs)", el("input", { type: "checkbox", checked: s.exit === "secret",
      onchange: (e) => { s.exit = e.target.checked ? "secret" : true; write(); } })));
    if (!solidSort(sort) && !["door", "plate", "pad", "lift", "toxic"].includes(sort)) {
      const now = s.conveyor ? "belt " + String(s.conveyor)[0] : s.oil ? "oil" : s.slick ? "slick" : "";
      rows.push(field("Floor surface", el("select", { onchange: (e) => {
        delete s.oil; delete s.slick; delete s.conveyor;
        const v = e.target.value;
        if (v === "oil") s.oil = true;
        else if (v === "slick") s.slick = true;
        else if (v.startsWith("belt ")) s.conveyor = v.slice(5);
        write();
      } }, ...[["", "plain"], ["oil", "oil (slippery; fire runs along it)"], ["slick", "slick (things slide until stopped)"],
        ["belt n", "a belt moving north"], ["belt e", "a belt moving east"], ["belt s", "a belt moving south"], ["belt w", "a belt moving west"]]
        .map(([v, label]) => el("option", { value: v, selected: v === now }, label)))));
    }
    if (sort === "floor" || sort === "door") rows.push(field("A secret area (counted when the player stands in it)",
      el("input", { type: "checkbox", checked: !!s.secret, onchange: (e) => { s.secret = e.target.checked; write(); } })));
    if (sort === "panel") rows.push(field("Opened by", el("select", { onchange: (e) => { s.panel = e.target.value; write(); } },
      el("option", { value: "fist", selected: s.panel !== "shoot" }, "a punch (a hollow wall)"), el("option", { value: "shoot", selected: s.panel === "shoot" }, "a shot (a dented vent)"))));
    if (!solidSort(sort) && sort !== "door") {
      if (sort !== "item") evRow("on_enter", "Stepping here sets off");
      rows.push(field("Floor tile", tileSelect(s.floor, (v) => { s.floor = v; write(); })));
      rows.push(field("Ceiling tile", tileSelect(s.ceiling, (v) => { s.ceiling = v; write(); })));
      rows.push(field("Open to the sky (the level's \"sky\" over it, no ceiling)", el("input", { type: "checkbox", checked: !!s.sky,
        onchange: (e) => { s.sky = e.target.checked; write(); } })));
    }
    const rename = el("input", { type: "text", class: "code short", maxlength: "1", value: ch, "aria-label": "The character", onchange: (e) => {
      const next = e.target.value;
      if (next.length !== 1 || next === ch) { e.target.value = ch; return; }
      if (next in legend() || used().has(next)) { status(`"${next}" is in use already.`, true); e.target.value = ch; return; }
      legend()[next] = legend()[ch]; delete legend()[ch];
      thing.map = thing.map.map((r) => r.split(ch).join(next));
      ui.pen = next; changed(); draw(); swatches(); edit();
    } });
    editBox.replaceChildren(head, field("Character", rename), ...rows,
      el("button", { type: "button", class: "quiet small warn", onclick: () => {
        if (used().has(ch) && !confirm(`The map uses "${ch}". Remove it from the legend anyway?`)) return;
        delete legend()[ch]; ui.pen = "#"; changed(); draw(); swatches(); edit();
      } }, "Remove from the legend"));
  }
  function eventsSheet() {
    const texts = isObject(thing.events) ? thing.events : {};
    const all = events();
    eventsBox.replaceChildren(el("h3", {}, "Events"),
      el("p", { class: "note" }, "An event is set off by a cell (stepping on it) or an item (taking it); then walls and doors set to open on it open, " +
        "doors set to shut on it shut, and monsters set to wake on it wake. The text is shown when it happens."),
      ...(all.length ? all.map((name) => field(name, el("input", { type: "text", value: texts[name] || "", placeholder: "shown when it happens (optional)",
        oninput: (e) => { if (!isObject(thing.events)) thing.events = {}; if (e.target.value) thing.events[name] = e.target.value; else delete thing.events[name]; if (!Object.keys(thing.events).length) delete thing.events; touched(kind); } })))
        : [el("p", { class: "note" }, "None yet: give a cell or an item an event below the palette.")]));
  }
  function levelTiles() {
    tilesBox.replaceChildren(
      el("label", {}, "Floor ", tileSelect(thing.floor, (v) => { if (v) thing.floor = v; else delete thing.floor; changed(); draw(); swatches(); })),
      el("label", {}, "Ceiling ", tileSelect(thing.ceiling, (v) => { if (v) thing.ceiling = v; else delete thing.ceiling; changed(); })));
  }

  // ---- the level from a cell, as the engine draws it
  async function look() {
    if (!ui.cam) { const [x, y] = startCell(); ui.cam = { x, y, f: String(thing.facing || "n")[0] }; draw(); }
    let res;
    try { res = await api("/api/view", { pending: pending(), level: id, x: ui.cam.x, y: ui.cam.y, facing: ui.cam.f, style: ui.style }); }
    catch (err) { viewNote.textContent = "It cannot be drawn: " + err.message; return; }
    paintCells(view, res.rows, res.cols, res.lines);
    viewNote.textContent = `From (${res.at[0]}, ${res.at[1]}) facing ${{ n: "north", e: "east", s: "south", w: "west" }[res.facing]}` +
      (res.inside ? " - inside a wall" : "") + (res.seen.length ? `. In sight: ${res.seen.join(", ")}` : "") + ".";
  }
  function walk(cmd) {
    if (!ui.cam) return;
    const f = ui.cam.f;
    if (cmd === "left" || cmd === "right") ui.cam.f = TURN[(TURN.indexOf(f) + (cmd === "left" ? 3 : 1)) % 4];
    else {
      const [dx, dy] = STEPS[f].map((v) => (cmd === "back" ? -v : v));
      const ch = (thing.map[ui.cam.y + dy] || "")[ui.cam.x + dx];
      if (ch === undefined || blocksWalk(sortOf(specOf(thing, info, ch)))) return;
      ui.cam.x += dx; ui.cam.y += dy;
    }
    draw(); look();
  }
  view.addEventListener("keydown", (e) => {
    const cmd = { ArrowUp: "step", ArrowDown: "back", ArrowLeft: "left", ArrowRight: "right" }[e.key];
    if (cmd) { walk(cmd); e.preventDefault(); }
  });
  const walkButtons = el("span", { class: "row" },
    ...[["left", "↶ Turn left"], ["step", "↑ Step"], ["back", "↓ Back"], ["right", "Turn right ↷"]].map(([c, label]) =>
      el("button", { type: "button", class: "quiet small", onclick: () => walk(c) }, label)), styleSel);

  // ---- the level bot plays it
  const goals = el("input", { type: "text", class: "code", value: Array.isArray(thing.bot) ? thing.bot.join(", ") : "", placeholder: "item ids or map characters, in order; E last",
    oninput: (e) => { const g = e.target.value.split(",").map((v) => v.trim()).filter(Boolean); if (g.length) thing.bot = g; else delete thing.bot; touched(kind); } });
  const play = el("button", { type: "button", class: "quiet", onclick: async () => {
    play.disabled = true;
    checkOut.replaceChildren(el("p", { class: "note" }, "Playing…"));
    try {
      const r = await api("/api/levelcheck", { pending: pending(), level: id, runs: 5 });
      const done = r.games.filter((g) => g.outcome === "exit").map((g) => g.beats);
      checkOut.replaceChildren(
        el("p", {}, `Finished ${r.finished} of ${r.runs}` + (done.length ? ` in ${Math.min(...done)} to ${Math.max(...done)} beats` : "") + (r.par ? ` (par ${r.par})` : "") +
          `. The level holds ${r.monsters} monsters, ${r.items} items and ${r.secrets} secrets.`),
        el("table", {}, el("thead", {}, el("tr", {}, ...["Game", "How it ended", "Beats", "Health", "Kills", "Secrets", "Where"].map((t) => el("th", {}, t)))),
          el("tbody", {}, ...r.games.map((g) => el("tr", {}, el("td", {}, String(g.seed + 1)), el("td", {}, { exit: "at the exit", dead: "dead", stuck: "stuck" }[g.outcome] || g.outcome),
            el("td", {}, String(g.beats)), el("td", {}, String(g.health)), el("td", {}, String(g.kills)), el("td", {}, String(g.secrets)),
            el("td", {}, el("button", { type: "button", class: "link", onclick: () => { ui.cam = { x: g.where[0], y: g.where[1], f: ui.cam ? ui.cam.f : "n" }; draw(); look(); } }, `(${g.where[0]}, ${g.where[1]})`)))))),
        el("p", { class: "note" }, "A simple player: it goes for its goals in order, fights what it sees and steps out of fire. If it can finish, a person can; " +
          "if it dies or gets stuck, look where it ended."));
    } catch (err) { checkOut.replaceChildren(el("p", { class: "note bad" }, err.message)); }
    play.disabled = false;
  } }, "Let the level bot play it");

  const box = el("div", { class: "sheet level" }, el("p", { class: "lead" }, "Drawing the map…"));
  levelsInfo(true).then((got) => {
    info = got;
    tools(); sizes(); swatches(); edit(); eventsSheet(); levelTiles(); draw(); look();
    box.replaceChildren(
      el("h3", {}, "Map"), el("div", { class: "row" }, sizeBox, toolBox),
      el("div", { class: "level-row" }, el("div", {}, grid, hover), el("div", { class: "level-side" }, palette)),
      editBox,
      el("h3", {}, "Tiles of the whole level"), tilesBox,
      el("h3", {}, "Seen from a cell"), view, walkButtons, viewNote,
      el("p", { class: "note" }, "Choose \"Look from a cell\" and click the map to stand somewhere; the arrow keys (with the picture chosen) or the buttons walk and turn. " +
        "Monsters are drawn where they start, asleep."),
      eventsBox,
      el("h3", {}, "The level bot"), field("Its goals", goals), play, checkOut);
  }).catch((err) => box.replaceChildren(el("p", { class: "note bad" }, "The map cannot be drawn: " + err.message)));
  return box;
}

// ---------------------------------------------------------------------- weapons: one in the hands
function weaponSheet(kind, thing, id) {
  const canvas = el("canvas", { class: "banner-canvas", role: "img", "aria-label": "The weapon in the player's hands" });
  const note = el("p", { class: "note" });
  let drawn = null, timer = null, wait = null;
  async function show() {
    clearTimeout(timer);
    try { drawn = await api("/api/weaponview", { pending: pending(), weapon: id }); } catch (err) { note.textContent = "It cannot be drawn: " + err.message; return; }
    paintCells(canvas, drawn.rows, drawn.cols, drawn.lines);
    note.textContent = drawn.drawn ? "Fire it to see a shot (a punch, for a fist) as a level plays it." : `There is no sprite "${drawn.sprite || ""}": draw one under Sprites (a weapon sprite starts with w_ by custom).`;
  }
  function fire() {
    if (!drawn) return;
    clearTimeout(timer);
    let i = 0;
    const step = () => {
      if (i >= drawn.frames.length) { paintCells(canvas, drawn.rows, drawn.cols, drawn.lines); return; }
      paintCells(canvas, drawn.frames[i++], drawn.cols, drawn.lines);
      timer = setTimeout(step, 60);
    };
    step();
  }
  const later = () => { clearTimeout(wait); wait = setTimeout(show, 300); };
  setTimeout(() => {
    const form = canvas.closest("#form");
    if (form) { form.addEventListener("input", later); form.addEventListener("change", later); }
  }, 0);
  show();
  return el("div", { class: "sheet" }, el("h3", {}, "In the player's hands"), canvas,
    el("div", { class: "row" }, el("button", { type: "button", class: "quiet", onclick: fire }, "Fire"),
      thing.sprite ? el("button", { type: "button", class: "quiet", onclick: () => select("sprites", thing.sprite) }, "Edit its sprite") : null), note,
    el("p", { class: "note" }, `The id is the key that picks it in a level (${id}); a pick-up gives it with "weapon": "${id}".`));
}

// ---------------------------------------------------------------------- 3D models: build one, see it
const SHAPES = ["box", "wedge", "cylinder", "cone", "sphere", "ring"];
const ROUND = ["cylinder", "cone", "ring"];
const round3 = (v) => Math.round(v * 1000) / 1000;
function hexOf(c) {                                              // "#rrggbb" or [r, g, b] as a colour input wants it
  if (Array.isArray(c) && c.length >= 3) return "#" + c.slice(0, 3).map((v) => Math.max(0, Math.min(255, Math.round(+v || 0))).toString(16).padStart(2, "0")).join("");
  return typeof c === "string" && /^#[0-9a-fA-F]{6}$/.test(c) ? c.toLowerCase() : "#808080";
}

function modelSheet(kind, thing, id, built) {
  const canvas = el("canvas", { class: "banner-canvas", role: "img", "aria-label": "The model in a small room, as a level draws it" });
  const note = el("p", { class: "note" }), facts = el("p", { class: "note" }), importNote = el("p", { class: "note" });
  const clipsBox = el("span", { class: "row" });
  let drawn = null, timer = null, wait = null, at = 0;
  const paint = (rows) => { if (drawn && rows) paintCells(canvas, rows, drawn.cols, drawn.lines); };
  const still = () => paint(drawn && drawn.turn[at]);
  async function show() {
    clearTimeout(timer);
    try { drawn = await api("/api/modelview", { pending: pending(), name: id }); } catch (err) { note.textContent = "It cannot be drawn: " + err.message; return; }
    note.classList.toggle("bad", drawn.problems.length > 0);
    note.textContent = drawn.problems.join(" ");
    if (drawn.problems.length) { facts.textContent = ""; return; }
    facts.textContent = `${drawn.triangles} triangles, ${drawn.parts} parts, ${drawn.materials} materials; ${drawn.height} cells high, ${drawn.width} across.` +
      (drawn.triangles > 400 ? " That is a lot of triangles for a terminal: a few hundred is plenty." : "");
    at %= drawn.turn.length;
    still();
    clipsBox.replaceChildren(...Object.keys(drawn.clips).map((c) => el("button", { type: "button", class: "quiet", onclick: () => play(drawn.clips[c], still) }, `Play ${c}`)));
  }
  function play(frames, then) {
    clearTimeout(timer);
    let i = 0;
    const step = () => { if (i >= frames.length) { if (then) then(); return; } paint(frames[i++]); timer = setTimeout(step, 90); };
    step();
  }
  const later = () => { clearTimeout(wait); wait = setTimeout(show, 350); };
  const changed = () => { touched(kind); later(); };
  setTimeout(() => {
    const form = canvas.closest("#form");
    if (form) { form.addEventListener("input", later); form.addEventListener("change", later); }
  }, 0);
  const turnBy = (d) => { if (drawn && drawn.turn.length) { at = (at + d + drawn.turn.length) % drawn.turn.length; still(); } };
  const controls = el("div", { class: "row" },
    el("button", { type: "button", class: "quiet", "aria-label": "Turn it left", onclick: () => turnBy(-1) }, "◀"),
    el("button", { type: "button", class: "quiet", "aria-label": "Turn it right", onclick: () => turnBy(1) }, "▶"),
    el("button", { type: "button", class: "quiet", onclick: () => drawn && play(drawn.turn.slice(at).concat(drawn.turn, drawn.turn.slice(0, at)), still) }, "Turn round"),
    el("button", { type: "button", class: "quiet", onclick: () => drawn && play(drawn.broken, () => { timer = setTimeout(still, 700); }) }, "Break it"),
    clipsBox);

  // materials: glTF's metallic-roughness, a row each
  const matsBox = el("div", { class: "model-list" });
  const mats = () => { if (!isObject(thing.materials)) thing.materials = {}; return thing.materials; };
  const partsOf = () => { if (!Array.isArray(thing.parts)) thing.parts = []; return thing.parts; };
  function renameMat(from, to) {
    const m = mats();
    if (!to || to === from || m[to] !== undefined || !validId(to)) { drawMats(); return; }
    const next = {};
    for (const [k, v] of Object.entries(m)) next[k === from ? to : k] = v;     // the order kept
    thing.materials = next;
    for (const p of partsOf()) if (p.material === from) p.material = to;
    drawMats(); drawParts(); changed();
  }
  function drawMats() {
    const m = mats();
    const num = (mat, key, min, max, step, label) => el("label", { class: "pair" }, label, el("input", { type: "number", class: "tiny", min, max, step, value: mat[key] ?? "",
      oninput: (e) => { if (e.target.value === "") delete mat[key]; else mat[key] = +e.target.value; changed(); } }));
    matsBox.replaceChildren(...Object.keys(m).map((name) => {
      const mat = isObject(m[name]) ? m[name] : (m[name] = {});
      return el("div", { class: "row model-row" },
        el("input", { type: "text", class: "code short", value: name, spellcheck: "false", "aria-label": "Material name", onchange: (e) => renameMat(name, e.target.value.trim()) }),
        el("input", { type: "color", value: hexOf(mat.color), "aria-label": "Colour", oninput: (e) => { mat.color = e.target.value; changed(); } }),
        num(mat, "metal", 0, 1, 0.05, "metal"), num(mat, "rough", 0.04, 1, 0.05, "rough"), num(mat, "glow", 0, 5, 0.1, "glow"),
        el("button", { type: "button", class: "quiet warn", onclick: () => {
          delete m[name];
          for (const p of partsOf()) if (p.material === name) delete p.material;
          drawMats(); drawParts(); changed();
        } }, "Remove"));
    }), el("button", { type: "button", class: "quiet", onclick: () => {
      let n = 1;
      while (m["material" + n] !== undefined) n++;
      m["material" + n] = { color: "#808080", metal: 0, rough: 0.5 };
      drawMats(); drawParts(); changed();
    } }, "Add a material"));
  }

  // parts: a shape, its material and group, its size, place and turn - and what its shape takes besides
  const partsBox = el("div", { class: "model-list" });
  const triple = (part, key, def, step, label) => {
    const now = () => (Array.isArray(part[key]) ? part[key].slice() : def.slice());
    return el("span", { class: "triple" }, label, ...[0, 1, 2].map((i) => el("input", { type: "number", class: "tiny", step, value: now()[i] ?? def[i], "aria-label": `${label} ${"xyz"[i]}`,
      oninput: (e) => {
        const v = now();
        v[i] = e.target.value === "" ? def[i] : +e.target.value;
        if (key !== "size" && v.every((c, j) => c === def[j])) delete part[key]; else part[key] = v.map(round3);
        changed();
      } })));
  };
  const numberIn = (part, key, min, max, step, label, def) => el("label", { class: "pair" }, label, el("input", { type: "number", class: "tiny", min, max, step, value: part[key] ?? def,
    oninput: (e) => { if (e.target.value === "" || +e.target.value === def) delete part[key]; else part[key] = +e.target.value; changed(); } }));
  function drawParts() {
    const list = partsOf(), names = Object.keys(mats());
    partsBox.replaceChildren(...list.map((part, i) => {
      const shape = part.shape || "box";
      const extra = [];
      if (ROUND.includes(shape)) {
        extra.push(el("label", { class: "pair" }, "along", el("select", { onchange: (e) => { if (e.target.value === "z") delete part.axis; else part.axis = e.target.value; changed(); } },
          ...["z", "x", "y"].map((a) => el("option", { value: a, selected: (part.axis || "z") === a }, a)))));
        extra.push(numberIn(part, "sides", 3, 32, 1, "sides", 8));
      }
      if (shape === "ring") extra.push(numberIn(part, "thick", 0.05, 0.9, 0.05, "thick", 0.3), numberIn(part, "tube", 3, 12, 1, "tube", 6));
      if (shape === "sphere") extra.push(numberIn(part, "detail", 0, 3, 1, "detail", 1));
      const copy = (mirror) => {
        const c = JSON.parse(JSON.stringify(part));
        if (mirror) {                                      // the same part on the other side: x and the turns about z and y the other way
          const a = c.at || [0, 0, 0];
          c.at = [round3(-a[0]), a[1], a[2]];
          if (c.turn) c.turn = [round3(-c.turn[0]), c.turn[1], round3(-c.turn[2])];
        }
        list.splice(i + 1, 0, c);
        drawParts(); changed();
      };
      return el("div", { class: "model-part" },
        el("div", { class: "row" },
          el("strong", {}, String(i + 1)),
          el("select", { "aria-label": "Shape", onchange: (e) => { part.shape = e.target.value; drawParts(); changed(); } }, ...SHAPES.map((s) => el("option", { value: s, selected: shape === s }, s))),
          el("select", { "aria-label": "Material", onchange: (e) => { if (e.target.value) part.material = e.target.value; else delete part.material; changed(); } },
            el("option", { value: "" }, "(the first material)"), ...names.map((n) => el("option", { value: n, selected: part.material === n }, n))),
          el("input", { type: "text", class: "code short", placeholder: "group", spellcheck: "false", value: part.group || "", "aria-label": "Group: parts that spin or break together",
            onchange: (e) => { const v = e.target.value.trim(); if (v) part.group = v; else delete part.group; changed(); } }),
          el("button", { type: "button", class: "quiet", title: "A copy of it, next in the list", onclick: () => copy(false) }, "Copy"),
          el("button", { type: "button", class: "quiet", title: "A copy on the other side (left for right)", onclick: () => copy(true) }, "Mirror"),
          i ? el("button", { type: "button", class: "quiet", title: "Up the list", "aria-label": "Up the list", onclick: () => { [list[i - 1], list[i]] = [list[i], list[i - 1]]; drawParts(); changed(); } }, "↑") : null,
          el("button", { type: "button", class: "quiet warn", onclick: () => { list.splice(i, 1); drawParts(); changed(); } }, "Remove")),
        el("div", { class: "row" }, triple(part, "size", [1, 1, 1], 0.05, "size"), triple(part, "at", [0, 0, 0], 0.05, "at"), triple(part, "turn", [0, 0, 0], 5, "turn°"), ...extra));
    }));
  }
  const addShape = el("select", { "aria-label": "Shape of the new part" }, ...SHAPES.map((s) => el("option", { value: s }, s)));
  const addPart = el("button", { type: "button", class: "quiet", onclick: () => {
    const p = { shape: addShape.value, size: [0.4, 0.4, 0.4], at: [0, 0, 0.2] };
    const first = Object.keys(mats())[0];
    if (first) p.material = first; else mats().plain = { color: "#808080", metal: 0, rough: 0.5 };
    partsOf().push(p);
    drawMats(); drawParts(); changed();
  } }, "Add a part");

  // a glTF file from Blender: its meshes, materials and animations, keeping how the model moves
  const scale = el("input", { type: "number", class: "short", min: "0.01", step: "0.05", value: "0.4", "aria-label": "Cells per metre" });
  const file = el("input", { type: "file", accept: ".glb,.gltf", onchange: async (e) => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    importNote.textContent = `Reading ${f.name}…`;
    try {
      const got = await api("/api/modelimport", { data: base64(await f.arrayBuffer()), name: id, scale: +scale.value || 0.4 });
      const keep = {};
      for (const k of ["bob", "turning", "smooth", "spin", "scale", "break"]) if (thing[k] !== undefined) keep[k] = thing[k];
      for (const k of Object.keys(thing)) delete thing[k];
      Object.assign(thing, keep, got.spec);
      touched(kind);
      status(`${f.name} taken in` + (got.notes.length ? ": " + got.notes.join(" ") : "."));
      renderForm();
    } catch (err) { importNote.textContent = "It could not be taken in: " + err.message; }
  } });

  if (built) { drawMats(); drawParts(); }
  show();
  const mesh = isObject(thing.mesh) && Array.isArray(thing.mesh.v) && thing.mesh.v.length;
  return el("div", { class: "sheet" },
    el("h3", {}, "In a small room, as a level draws it"), canvas, controls, facts, note,
    built ? el("div", {},
      el("h3", {}, "Materials"),
      el("p", { class: "note" }, "As glTF has them: a colour, how metal (0 to 1) and how rough (0.04 to 1) it is; glow makes it shine in the dark."), matsBox,
      el("h3", {}, "Parts"),
      el("p", { class: "note" }, "x is right, y forward (where it faces), z up; a cell is 1. Turn is yaw, pitch and roll in degrees. A group's parts spin together (\"spin\" below) and, " +
        "with Destroyed: parts or groups, fly off together." + (mesh ? " It has an imported mesh too: the parts are added to it." : "")),
      partsBox, el("div", { class: "row" }, addShape, addPart))
      : el("p", { class: "note" }, "Its materials or parts are not as the builder wants them: edit them in the JSON below."),
    el("h3", {}, "From Blender"),
    el("p", { class: "note" }, "Export glTF 2.0 (.glb). Its meshes, materials, vertex colours, PNG textures and animations take this model's place; " +
      "how it bobs, turns, spins and breaks stays. clio.py --import-model does the same from a terminal."),
    el("div", { class: "row" }, el("label", { class: "pair" }, "Cells per metre", scale), file), importNote);
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
    let blob;
    if (HOSTED) blob = await api("/api/archive", {});
    else {
      const res = await fetch("/api/archive", { method: "POST", headers: { "X-CLIo-Token": KEY, "Content-Type": "application/json" }, body: "{}" });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
      blob = await res.blob();
    }
    download(state.game.id + ".zip", blob);
    tab.unkept = false;
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
$("sheet").addEventListener("click", () => {
  state.id = null;
  state.workshop = null;
  state.sheet = { what: state.kind === "tiles" ? "tiles" : state.kind === "sprites" ? "sprites" : "monsters", scale: state.kind === "tiles" ? 2 : 4, labels: true, dark: false, url: null };
  renderList(); renderForm();
});
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
$("finish").addEventListener("click", () => { state.finish = true; state.workshop = null; state.id = null; renderList(); renderForm(); });
$("checkup").addEventListener("click", async () => {
  try {
    const found = (await api("/api/advice", { pending: pending() })).advice;
    $("found").hidden = false;
    $("found-count").textContent = found.length === 0 ? "Check-up: every room can be reached and everything is referred to by something."
      : `Check-up: ${found.length} thing${found.length === 1 ? "" : "s"} that may not be meant. These are not errors; the game runs.`;
    $("found-list").replaceChildren(...found.map((p) => el("li", {}, el("button", { type: "button", onclick: () => select(p.kind, p.id) }, el("span", { class: "snippet" }, p.text)))));
  } catch (err) {
    status("Could not run the check-up: " + err.message, true);
  }
});
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
window.addEventListener("beforeunload", (e) => { if (state.dirty.size || tab.unkept) { e.preventDefault(); e.returnValue = ""; } });
window.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); if (state.dirty.size) saveAll(); }
});

// ---------------------------------------------------------------------- the editor without a server
// Opened from a web address, the page starts a worker that runs Python and the CLIo engine in the browser
// (worker.js). The game is read from a folder or a zip file on this computer and lives in the worker's memory.
// Where the browser lets a page write into a folder it was given (Chrome, Edge), Save writes there; elsewhere the
// changes stay in the page until "Download game".
const tab = { worker: null, waking: null, next: 0, asked: new Map(), game: null, home: "", folder: null, unkept: false, manifest: null };
const SKIP = (name) => name === "__pycache__" || name === "saves" || (name.startsWith(".") && name !== ".editor-backup");
const MOST_FILES = 3000;

function ask(cmd, more, transfer) {
  return new Promise((resolve, reject) => {
    const id = tab.next += 1;
    tab.asked.set(id, { resolve, reject });
    tab.worker.postMessage(Object.assign({ id, cmd }, more || {}), transfer || []);
  });
}

function wake() {                                                    // once; opening a game waits for it
  if (tab.waking) return tab.waking;
  const extra = PARAMS.get("pyodide") ? "?pyodide=" + encodeURIComponent(PARAMS.get("pyodide")) : "";
  tab.worker = new Worker("worker.js" + extra, { type: "module" });
  tab.worker.onmessage = (event) => {
    const m = event.data;
    if (m.type === "status") { if (!state.game) status(m.text); return; }
    const waiting = tab.asked.get(m.id);
    if (!waiting) return;
    tab.asked.delete(m.id);
    if (m.ok) waiting.resolve(m); else waiting.reject(new Error(m.error));
  };
  tab.worker.onerror = (event) => {
    for (const waiting of tab.asked.values()) waiting.reject(new Error(event.message || "The engine could not be started."));
    tab.asked.clear();
  };
  tab.waking = ask("init");
  return tab.waking;
}

async function hostedApi(path, body) {
  const out = await ask("api", { game: tab.game, path, body: JSON.stringify(body || {}) });
  if (out.bytes) return new Blob([out.bytes], { type: out.bytes[0] === 0x89 ? "image/png" : "application/zip" });
  const answer = JSON.parse(out.json);
  if (!answer.ok) throw new Error(answer.error);
  if (path === "/api/walkthrough" && body && "text" in body) await kept();
  return answer.data;
}

// A game without a folder to save into is kept by the browser between visits (IndexedDB), whole, under its id.
const KEPT = "clio-editor";

function shelf(mode, work) {
  return new Promise((resolve, reject) => {
    const opening = indexedDB.open(KEPT, 1);
    opening.onupgradeneeded = () => opening.result.createObjectStore("games", { keyPath: "id" });
    opening.onerror = () => reject(opening.error);
    opening.onsuccess = () => {
      const tx = opening.result.transaction("games", mode);
      const request = work(tx.objectStore("games"));
      tx.oncomplete = () => { opening.result.close(); resolve(request && request.result); };
      tx.onabort = tx.onerror = () => { opening.result.close(); reject(tx.error); };
    };
  });
}

async function keepInBrowser() {
  const { files } = await ask("files", { game: tab.game });
  await shelf("readwrite", (games) => games.put({ id: state.game.id, title: (state.game.files.game && state.game.files.game.data.title) || state.game.title, when: Date.now(), files }));
}

// After something was written: put the same files into the folder the game came from; without one, keep the game in
// the browser. Returns what to tell the author.
async function kept() {
  if (!tab.folder) {
    try {
      await keepInBrowser();
      tab.unkept = false;
      return " The game is kept in this browser; Download game gives you its files.";
    } catch (err) {
      tab.unkept = true;
      return " The changes are in this page only: use Download game to keep them.";
    }
  }
  try {
    const { files } = await ask("changed", { game: tab.game });
    for (const [path, data] of files) {
      const parts = (tab.home ? tab.home + "/" + path : path).split("/");         // the game may sit inside the folder that was opened
      let dir = tab.folder;
      for (const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part, { create: true });
      const out = await (await dir.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
      await out.write(data);
      await out.close();
    }
    tab.unkept = false;
    return " Your folder has the changes.";
  } catch (err) {
    tab.unkept = true;
    return ` Your folder could not be written to (${err.message}): use Download game to keep the changes.`;
  }
}

async function readFolder(dir, prefix, into) {                       // a folder the browser gave us, as [path, bytes] pairs
  for await (const [name, handle] of dir.entries()) {
    if (SKIP(name)) continue;
    if (handle.kind === "directory") await readFolder(handle, prefix + name + "/", into);
    else {
      if (into.length >= MOST_FILES) throw new Error("There are too many files in that folder for it to be a game. Choose the game's own folder.");
      into.push([prefix + name, new Uint8Array(await (await handle.getFile()).arrayBuffer())]);
    }
  }
  return into;
}

async function openGame(what, work) {
  $("open").classList.add("busy");
  status("Opening " + what + "…");
  try {
    await wake();
    const placed = await work();
    tab.game = placed.game;
    tab.home = placed.home || "";
    await begin();
    $("open").hidden = true;
    document.body.classList.remove("opening");
  } catch (err) {
    tab.folder = null;
    status("Could not open " + what + ": " + err.message, true);
  }
  $("open").classList.remove("busy");
}

// A page shown inside another site's page (an itch.io project) is not allowed to ask for a folder to write into.
const EMBEDDED = (() => { try { return window.top !== window.self && !window.top.location.href; } catch (err) { return true; } })();
const CAN_WRITE = !!window.showDirectoryPicker && !EMBEDDED;

async function openFolder() {
  if (!CAN_WRITE) return $("open-dir-input").click();
  let dir;
  try { dir = await window.showDirectoryPicker({ id: "clio-game", mode: "readwrite" }); } catch (err) {
    if (err.name !== "AbortError") $("open-dir-input").click();     // not allowed here after all: the folder as a list of files
    return;                                                          // or they changed their mind
  }
  await openGame(dir.name, async () => {
    const files = await readFolder(dir, "", []);
    tab.folder = dir;
    return ask("open", { name: dir.name, files }, files.map(([, data]) => data.buffer));
  });
}

async function openPicked(list) {                                    // the fallback: a folder as a list of files, read only
  const files = [];
  let name = "game";
  for (const file of list) {
    const parts = (file.webkitRelativePath || file.name).split("/");
    if (parts.length > 1) name = parts[0];
    if (parts.some(SKIP)) continue;
    if (files.length >= MOST_FILES) return status("There are too many files in that folder for it to be a game. Choose the game's own folder.", true);
    files.push([parts.slice(parts.length > 1 ? 1 : 0).join("/"), new Uint8Array(await file.arrayBuffer())]);
  }
  if (files.length) await openGame(name, () => ask("open", { name, files }, files.map(([, data]) => data.buffer)));
}

async function openZip(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  await openGame(file.name, () => ask("open-zip", { name: file.name.replace(/\.zip$/i, ""), bytes }, [bytes.buffer]));
}

async function welcome() {
  document.body.classList.add("opening");
  $("open").hidden = false;
  status("");
  const stays = "Save keeps the game in this browser, where you find it again next time, and Download game gives you the folder back as a zip file.";
  $("open-note").replaceChildren(...(CAN_WRITE
    ? ["Opened as a folder, the game is saved straight back into that folder; your browser will ask you to allow it. Opened any other way, " + stays[0].toLowerCase() + stays.slice(1)]
    : EMBEDDED && window.showDirectoryPicker
      ? ["Inside another page the editor cannot write into your folder: " + stays + " ", el("a", { href: location.href, target: "_blank", rel: "noopener" }, "Open the editor in a tab of its own"), " to save straight into the folder."]
      : ["In this browser a page cannot write into a folder: " + stays + " Chrome and Edge can save straight into the folder."]));
  showKept();
  $("open-folder").addEventListener("click", openFolder);
  $("open-zip").addEventListener("click", () => $("open-zip-input").click());
  $("open-dir-input").addEventListener("change", (e) => { openPicked([...e.target.files]); e.target.value = ""; });
  $("open-zip-input").addEventListener("change", (e) => { if (e.target.files[0]) openZip(e.target.files[0]); e.target.value = ""; });
  wake().then(() => { if (!state.game) status(""); }, (err) => status("The engine could not be started: " + err.message, true));
  try {
    tab.manifest = await (await fetch("manifest.json", { cache: "no-cache" })).json();
  } catch (err) {
    return;                                                          // no list of games: a folder or a zip still open
  }
  const offer = (game, name, label, about) => el("li", {}, el("button", { type: "button", class: "quiet", onclick: () =>
    openGame(label, () => ask("open", { name, fetch: { folder: game.folder, files: game.files } })) }, label), about ? el("span", { class: "note" }, about) : null);
  $("open-games").append(offer(tab.manifest.starter, "mygame", "A new game", "The Cellar: two rooms and three items, to turn into your own."),
    ...tab.manifest.games.map((g) => offer(g, g.id, g.title, g.about)));
}

async function showKept() {                                         // games this browser kept from earlier visits
  let games = [];
  try { games = (await shelf("readonly", (store) => store.getAll())) || []; } catch (err) { /* no storage here: nothing was kept */ }
  games.sort((a, b) => b.when - a.when);
  $("open-kept").hidden = !games.length;
  $("open-kept-list").replaceChildren(...games.map((g) => el("li", {},
    el("button", { type: "button", class: "quiet", onclick: () => openGame(g.title, () => ask("open", { name: g.id, files: g.files })) }, g.title),
    el("span", { class: "note" }, `Kept in this browser. Last saved ${new Date(g.when).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}. `,
      el("button", { type: "button", class: "link", onclick: async () => {
        if (!confirm(`Forget "${g.title}"? The copy in this browser is deleted. Files you downloaded stay.`)) return;
        try { await shelf("readwrite", (store) => store.delete(g.id)); } catch (err) { /* nothing to forget */ }
        showKept();
      } }, "Forget it")))));
}

// ---------------------------------------------------------------------- start
async function begin() {
  state.game = await api("/api/game");
  state.problems = state.game.problems;
  $("title").textContent = state.game.title;
  $("folder").textContent = !HOSTED ? state.game.folder
    : tab.folder ? `${tab.folder.name}${tab.home ? "/" + tab.home : ""} - saved into the folder you opened` : `${state.game.id} - kept in this browser when you save`;
  status(state.problems.length ? "" : "The engine finds no problems.");
  renderAll();
  select("game", "game");
}

(async function start() {
  if (!HOSTED && !KEY) {                                               // on this computer, but is it clio.py that serves the page?
    const res = await fetch("/api/game").catch(() => null);           // clio.py says "no key" (403); a plain file server has no such address
    if (!res || res.status !== 403) HOSTED = true;
  }
  $("reopen").hidden = !HOSTED;
  $("reopen").addEventListener("click", () => location.reload());     // the browser asks first when something is not kept
  if (HOSTED) welcome();
  else begin().catch((err) => status("Could not open the game: " + err.message, true));
})();
