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
  if (f.type === "tags" || f.type === "refs") return Array.isArray(value) && value.every((v) => typeof v === "string");
  if (f.type === "sprite") return typeof value === "string";
  if (f.type === "effects") return Array.isArray(value) || isObject(value);
  if (f.type === "condition") return typeof value === "string" || Array.isArray(value) || isObject(value);
  if (f.type === "group") return isObject(value);
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

  // everything the schema does not describe is still here, as JSON
  const rest = restArea(kind, thing, known, kind.fields.length || drawn ? "" : "This kind has no form yet: edit it as JSON.");
  parts.push(field(kind.fields.length || drawn ? "Everything else" : "Content", rest.area, rest.note));

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
  if (out.bytes) return new Blob([out.bytes], { type: "application/zip" });
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
