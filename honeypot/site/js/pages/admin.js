// Admin page: sign-in with the admin password, then four tabs (overview, model updates and
// rollback, prompt pool and quantity, agent instructions). All data comes from /<TOKEN>/admin/api/*
// and needs the admin session cookie set at sign-in.
const VERSION_PREFIX = "/" + (location.pathname.split("/")[1] || "");
const TABS = ["overview", "models", "pool", "agents"];
const HASH_TO_TAB = { overview: "overview", models: "models", rollback: "models", pool: "pool", agents: "agents" };
let pollTimer = null, alive = false;

const $ = id => document.getElementById(id);
function el(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const k in (props || {})) { if (k === "class") e.className = props[k]; else if (k in e) e[k] = props[k]; else e.setAttribute(k, props[k]); }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined) e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return e;
}
const when = iso => (iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "");
const pct = v => (v === null || v === undefined ? "n/a" : Math.round(v * 100) + "%");
const LABEL = { "Allow": "Allow", "Shadow AI": "Shadow AI", "Automated AI Pipelines": "Automated" };

async function api(path, body) {
  const opt = { credentials: "same-origin", headers: { "X-PG-Admin": "1" } };
  if (body !== undefined) { opt.method = "POST"; opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const res = await fetch(VERSION_PREFIX + path, opt);
  let data = {};
  try { data = await res.json(); } catch (e) { data = { error: "Unexpected answer from the server." }; }
  if (res.status === 401 && path !== "/admin/login") { showLogin(); throw new Error(data.error || "Signed out"); }
  if (!res.ok) throw new Error(data.error || ("Error " + res.status));
  return data;
}
function msg(node, text, kind) {
  node.textContent = text; node.hidden = !text;
  node.className = "ad-msg" + (kind === "err" ? " ad-err" : kind === "ok" ? " ad-ok" : "");
}
// a button that asks for a second click before doing something that changes the live detector
function confirmClick(btn, action) {
  btn.addEventListener("click", () => {
    if (btn.dataset.armed === "1") { btn.dataset.armed = ""; btn.textContent = btn.dataset.label; action(); return; }
    btn.dataset.label = btn.dataset.label || btn.textContent; btn.dataset.armed = "1"; btn.textContent = "Click again to confirm";
    setTimeout(() => { if (btn.dataset.armed === "1") { btn.dataset.armed = ""; btn.textContent = btn.dataset.label; } }, 4000);
  });
}

function show(which) { for (const id of ["ad-wait", "ad-nopass", "ad-login", "ad-app"]) $(id).hidden = (id !== which); }
function showLogin() { stopPolling(); show("ad-login"); const pw = $("ad-pw"); if (pw) { pw.value = ""; pw.focus(); } }

function currentTab() { return HASH_TO_TAB[location.hash.replace("#", "")] || "overview"; }
function selectTab() {
  const tab = currentTab();
  for (const t of TABS) $("ad-p-" + t).hidden = (t !== tab);
  document.querySelectorAll("#ad-tabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.tab === tab ? "true" : "false"));
  stopPolling();
  if (tab === "overview") loadOverview();
  if (tab === "models") { loadModels(); loadUpdate(); }
  if (tab === "pool") loadPool();
  if (tab === "agents") loadAgents();
  if (location.hash === "#rollback") setTimeout(() => $("ad-rollback-card").scrollIntoView({ behavior: "smooth", block: "start" }), 50);
}

// ---------------------------------------------------------------- overview
async function loadOverview() {
  let d; try { d = await api("/admin/api/overview"); } catch (e) { return; }
  const r = d.roles, tiles = $("ad-tiles"); tiles.replaceChildren();
  const tile = (n, label) => tiles.append(el("div", { class: "ad-tile" }, el("b", {}, n), label));
  tile(d.participants.length, "participants with entries");
  tile(r.human.entries, "prompts entered by people");
  tile(r.agent.entries, "prompts entered by agents");
  tile(d.detector_uses, "Live Detector uses");
  tile(d.detector_feedback, "detector feedback clicks");
  tile(r.other.entries, "test entries (other links)");
  $("ad-last").textContent = d.last_activity ? "Last activity: " + when(d.last_activity) : "Nothing has been collected yet.";
  const t = $("ad-participants"); t.replaceChildren();
  if (!d.participants.length) t.append(el("tr", {}, el("td", { class: "ad-muted" }, "No participant (P01 to P20) has entered a prompt yet.")));
  else {
    t.append(el("tr", {}, el("th", {}, "Participant"), el("th", { class: "ad-num" }, "Prompts entered"), el("th", {}, "Last entry")));
    for (const p of d.participants) t.append(el("tr", {}, el("td", {}, p.token), el("td", { class: "ad-num" }, p.entries), el("td", {}, when(p.last))));
  }
  const a = d.active_model;
  $("ad-active").textContent = a.version_id === "baseline" ? "The original models (no update is in use)." : "Update from " + when(a.created_at) + " (version " + a.version_id + ").";
  $("ad-env").textContent = "Participants enter " + d.settings.default_quantity + " prompts by default" + (d.settings.participant_can_choose ? " and can pick between " + d.settings.min_quantity + " and " + d.settings.max_quantity + "." : ".");
}

// ---------------------------------------------------------------- models: update job
function envNotes(env) {
  const box = $("ad-update-env"); box.replaceChildren();
  if (!env.training_ready) {
    box.append(el("div", { class: "ad-msg ad-err" }, "The training tools are not installed on this server yet. Connect to the server and run this once (about 5 minutes):",
      el("code", { class: "ad-code" }, "cd ~/browsing-agent-honeypot && " + env.setup_command)));
  } else if (!env.corpus_present) {
    box.append(el("div", { class: "ad-msg" }, "Only the behavior model will be retrained. To retrain the content model too, copy the private training file to the server as " + env.corpus_path + " (see the README)."));
  } else {
    box.append(el("div", { class: "ad-msg ad-ok" }, "Ready: both the content model and the behavior model will be retrained."));
  }
  $("ad-run").disabled = !env.training_ready;
}
function reportView(rep) {
  const box = $("ad-report"); box.replaceChildren();
  if (!rep || !rep.current_models) return;
  const c = rep.current_models, ra = rep.refined_actor_leave_participants_out, rc = rep.refined_content_leave_prompts_out;
  const t = el("table", { class: "ad-table" });
  t.append(el("tr", {}, el("th", {}, "On the collected data"), el("th", { class: "ad-num" }, "Models before this update"), el("th", { class: "ad-num" }, "After (estimated on held-out data)")));
  const row = (name, before, after) => t.append(el("tr", {}, el("td", {}, name), el("td", { class: "ad-num" }, before), el("td", { class: "ad-num" }, after)));
  row("Content: right category from the text", pct(c.content_accuracy), rc ? pct(rc.accuracy) : (rep.content_retrained ? "not estimated" : "unchanged"));
  row("Behavior: person vs agent", pct(c.actor_accuracy), ra ? pct(ra.accuracy) : "not estimated");
  row("People correctly seen as people", pct(c.human_kept_as_human), ra ? pct(ra.human_kept_as_human) : "not estimated");
  row("Agents caught", pct(c.agent_caught), ra ? pct(ra.agent_caught) : "not estimated");
  row("Final 3-way category", pct(c.category_accuracy_3way), "");
  box.append(el("p", { class: "ad-muted" }, "Based on " + rep.n_rows + " entries (" + (rep.by_actor.human || 0) + " by people from " + rep.participants + " participants, " + (rep.by_actor.agent || 0) + " by agents)."), el("div", { class: "ad-tablewrap" }, t));
}
async function loadUpdate() {
  let s; try { s = await api("/admin/api/update/status"); } catch (e) { return; }
  if (!alive) return;
  envNotes(s.environment);
  const running = s.state === "running";
  $("ad-run").disabled = running || !s.environment.training_ready;
  $("ad-run").textContent = running ? "Update running..." : "Run model update";
  if (s.state === "idle") { msg($("ad-update-msg"), ""); }
  else if (running) msg($("ad-update-msg"), "Running since " + when(s.started_at) + ". This takes a few minutes; you can leave this page.");
  else if (s.state === "done") msg($("ad-update-msg"), "Last update finished " + when(s.finished_at) + ". " + (s.message || ""), "ok");
  else msg($("ad-update-msg"), "Last update did not finish (" + when(s.finished_at) + "): " + (s.message || ""), "err");
  reportView(s.report);
  const log = $("ad-log"); log.textContent = s.log_tail || ""; log.hidden = !(s.log_tail && (running || s.state === "failed"));
  if (running) { stopPolling(); pollTimer = setTimeout(loadUpdate, 2000); }
  else if (pollTimer !== null) { pollTimer = null; loadModels(); }
}
function stopPolling() { if (pollTimer) { clearTimeout(pollTimer); } pollTimer = null; }
async function runUpdate() {
  try {
    await api("/admin/api/update/start", { activate: $("ad-activate").checked });
    pollTimer = setTimeout(loadUpdate, 300);
    msg($("ad-update-msg"), "Starting...");
  } catch (e) { msg($("ad-update-msg"), e.message, "err"); }
}

// ---------------------------------------------------------------- models: versions + rollback
function versionSummary(v) {
  if (v.kind === "baseline") return "Original models, trained before any study data (" + (v.content.n_train || "?") + " prompts, " + (v.actor.n_train || "?") + " simulated sessions).";
  const r = v.report || {}; const parts = [v.note || "Model update"];
  if (r.n_rows) parts.push(r.n_rows + " collected entries, " + (r.participants || 0) + " participants");
  const ra = r.refined_actor_leave_participants_out, rc = r.refined_content_leave_prompts_out;
  if (ra) parts.push("behavior " + pct(ra.accuracy) + " on held-out participants");
  if (rc) parts.push("content " + pct(rc.accuracy) + " on held-out prompts");
  return parts.join("; ") + ".";
}
async function loadModels() {
  let d; try { d = await api("/admin/api/models"); } catch (e) { return; }
  const t = $("ad-versions"); t.replaceChildren();
  t.append(el("tr", {}, el("th", {}, "Made"), el("th", {}, "Version"), el("th", {}, "What it is"), el("th", {}, "")));
  for (const v of d.versions) {
    const cell = el("td", {});
    if (v.active) cell.append(el("span", { class: "ad-badge" }, "In use"));
    else {
      const b = el("button", { class: "ad-btn ad-quiet ad-small", type: "button" }, "Use this version");
      confirmClick(b, async () => {
        try { await api("/admin/api/models/activate", { version_id: v.version_id }); msg($("ad-models-msg"), "Now using " + (v.kind === "baseline" ? "the original models" : "version " + v.version_id) + ".", "ok"); loadModels(); }
        catch (e) { msg($("ad-models-msg"), e.message, "err"); }
      });
      cell.append(b);
    }
    t.append(el("tr", {}, el("td", {}, when(v.created_at)), el("td", {}, v.kind === "baseline" ? "original" : v.version_id), el("td", {}, versionSummary(v)), cell));
  }
  const a = $("ad-activations"); a.replaceChildren();
  if (!d.activations.length) a.append(el("tr", {}, el("td", { class: "ad-muted" }, "No changes yet: the original models have been in use since the site was set up.")));
  else {
    a.append(el("tr", {}, el("th", {}, "When"), el("th", {}, "Changed from"), el("th", {}, "To"), el("th", {}, "Why")));
    const nm = x => (x === "baseline" ? "original" : x);
    const why = n => (n || "").replace(/rolled back to (\d{4}-\d{2}-\d{2}T[\d:]+Z)/, (m, iso) => "rolled back to the end of " + new Date(iso).toLocaleDateString([], { dateStyle: "medium" }));
    for (const x of d.activations) a.append(el("tr", {}, el("td", {}, when(x.at)), el("td", {}, nm(x.from)), el("td", {}, nm(x.to)), el("td", {}, why(x.note))));
  }
}
async function rollback(to, text) {
  try { await api("/admin/api/models/rollback", { to }); msg($("ad-models-msg"), text, "ok"); loadModels(); }
  catch (e) { msg($("ad-models-msg"), e.message, "err"); }
}

// ---------------------------------------------------------------- pool + quantity
async function loadPool() {
  let d; try { d = await api("/admin/api/pool"); } catch (e) { return; }
  const s = d.settings;
  $("ad-q-default").value = s.default_quantity; $("ad-q-min").value = s.min_quantity; $("ad-q-max").value = s.max_quantity; $("ad-q-choose").checked = s.participant_can_choose;
  for (const id of ["ad-q-default", "ad-q-min", "ad-q-max"]) $(id).max = d.human_pool_size;
  $("ad-pool-size").textContent = "The pool people can draw from holds " + d.human_pool_size + " prompts (Allow and Shadow AI). Agents use all " + d.agent_pool_size + ", including the Automated ones.";
  const t = $("ad-pool-table"); t.replaceChildren();
  t.append(el("tr", {}, el("th", {}, "Category"), el("th", { class: "ad-num" }, "In the pool"), el("th", { class: "ad-num" }, "Passed screening"), el("th", { class: "ad-num" }, "In the source"), el("th", {}, "Source"), el("th", {}, "How they were chosen")));
  const breakdown = o => Object.entries(o || {}).map(([k, v]) => k + " " + v).join(", ");
  const cap = t => (t ? t.charAt(0).toUpperCase() + t.slice(1) : "");
  for (const c of (d.pool.classes || [])) {
    t.append(el("tr", {}, el("td", {}, LABEL[c.class] || c.class), el("td", { class: "ad-num" }, c.in_bank), el("td", { class: "ad-num" }, c.screened_pool),
      el("td", { class: "ad-num" }, c.source_size), el("td", {}, cap(c.source), el("div", { class: "ad-muted" }, breakdown(c.source_breakdown))),
      el("td", {}, cap(c.screening) + ". " + cap(c.selection) + ".", el("div", { class: "ad-muted" }, "In the pool by origin: " + breakdown(c.bank_by_corpus)))));
  }
  const notes = $("ad-pool-notes"); notes.replaceChildren();
  const lic = (d.pool.licenses || {});
  notes.append(el("p", {}, "Licenses. WildChat: " + (lic.WildChat || "") + ". LMSYS-Chat-1M: " + (lic.LMSYS || "") + ". Synthetic: " + (lic.synthetic || "") + "."));
  const cv = $("ad-coverage"); cv.replaceChildren();
  cv.append(el("tr", {}, el("th", {}, "Category"), el("th", { class: "ad-num" }, "In the pool"), el("th", {}, "Entered by people"), el("th", {}, "Entered by agents")));
  const cover = (n, total, entries) => n + " of " + total + " prompts (" + entries + (entries === 1 ? " entry)" : " entries)");
  for (const k of ["Allow", "Shadow AI", "Automated AI Pipelines"]) {
    const c = d.collected[k]; if (!c) continue;
    cv.append(el("tr", {}, el("td", {}, LABEL[k]), el("td", { class: "ad-num" }, c.in_bank), el("td", {}, cover(c.entered_by_humans, c.in_bank, c.human_entries)), el("td", {}, cover(c.entered_by_agents, c.in_bank, c.agent_entries))));
  }
  const auto = (d.collected["Automated AI Pipelines"] || {}).in_bank || 0;
  $("ad-agent-count").textContent = auto * 3 + d.human_pool_size;
}
async function saveSettings() {
  const body = { default_quantity: +$("ad-q-default").value, min_quantity: +$("ad-q-min").value, max_quantity: +$("ad-q-max").value, participant_can_choose: $("ad-q-choose").checked };
  try { await api("/admin/api/settings", body); $("ad-q-msg").textContent = "Saved. New visitors to the Prompt Study page get these numbers."; loadPool(); }
  catch (e) { $("ad-q-msg").textContent = e.message; }
}

// ---------------------------------------------------------------- agents
function loadAgents() {
  const base = location.origin;
  $("ad-cmd-test").textContent = "python sim_gateway.py --base " + base + " --user YOUR-STUDY-USERNAME --limit 6";
  $("ad-cmd-full").textContent = "python sim_gateway.py --base " + base + " --user YOUR-STUDY-USERNAME";
  api("/admin/api/pool").then(d => { const auto = (d.collected["Automated AI Pipelines"] || {}).in_bank || 0; $("ad-agent-count").textContent = auto * 3 + d.human_pool_size; }).catch(() => {});
}

// ---------------------------------------------------------------- start-up
export async function init() {
  alive = true;
  if (!$("ad-wait")) return;
  $("content").classList.add("ad-wide");
  $("ad-form").addEventListener("submit", async e => {
    e.preventDefault(); $("ad-signin").disabled = true;
    try { await api("/admin/login", { password: $("ad-pw").value }); $("ad-login-msg").hidden = true; show("ad-app"); selectTab(); }
    catch (err) { msg($("ad-login-msg"), err.message, "err"); }
    $("ad-pw").value = ""; $("ad-signin").disabled = false;
  });
  $("ad-signout").addEventListener("click", async () => { try { await api("/admin/logout", {}); } catch (e) {} showLogin(); });
  document.querySelectorAll("#ad-tabs button").forEach(b => b.addEventListener("click", () => { history.replaceState(history.state, "", "#" + b.dataset.tab); selectTab(); }));
  window.addEventListener("hashchange", onHash);
  $("ad-run").addEventListener("click", runUpdate);
  $("ad-q-save").addEventListener("click", saveSettings);
  confirmClick($("ad-rollback-base"), () => rollback("baseline", "The original models are in use again."));
  confirmClick($("ad-rollback-date"), () => {
    const v = $("ad-date").value;
    if (!v) { msg($("ad-models-msg"), "Pick a date first.", "err"); return; }
    const [y, m, d] = v.split("-").map(Number);
    const iso = new Date(y, m - 1, d, 23, 59, 59).toISOString().replace(/\.\d+Z$/, "Z");
    rollback(iso, "Rolled back to the models as they were at the end of " + new Date(y, m - 1, d).toLocaleDateString([], { dateStyle: "medium" }) + ".");
  });
  let s;
  try { s = await (await fetch(VERSION_PREFIX + "/admin/api/session", { credentials: "same-origin" })).json(); }
  catch (e) { $("ad-wait").textContent = "Could not reach the server."; return; }
  if (!s.password_set) show("ad-nopass");
  else if (s.authenticated) { show("ad-app"); selectTab(); }
  else showLogin();
}
function onHash() { if (alive && !$("ad-app").hidden) selectTab(); }
export function cleanup() {
  alive = false; stopPolling(); window.removeEventListener("hashchange", onHash);
  const c = document.getElementById("content"); if (c) c.classList.remove("ad-wide");
}
