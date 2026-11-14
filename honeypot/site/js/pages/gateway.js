// Prompt Study page. After consent, the participant enters prompts drawn from the study's prompt
// bank (prompt_bank.json). How many is set on the Admin page (default, fewest, most) and, when
// allowed, chosen by the participant before starting.
//   /<TOKEN>/gateway      TOKEN = a participant id in the bank's "sets" (P01..P20): their 12 assigned
//                         prompts come first, then more from the pool in an order fixed for that
//                         participant. Any other token: a random draw. Allow and Shadow AI alternate.
//   ?scenario=<promptId>  one specific prompt (used by the agent driver, incl. Automated ones).
// Each Send posts to /<TOKEN>/prompt: the entered text, the prompt id and its class, and the
// keystroke/mouse events for that one prompt (captures/<TOKEN>_prompt.jsonl on the server).
const VERSION_PREFIX = "/" + (location.pathname.split("/")[1] || "");
const TOKEN = location.pathname.split("/")[1] || "";
const REPLIES = ["Here's a draft. Let me know if you'd like it shorter.", "Sure, here is a summary of the key points.",
  "Done. I've organized that for you.", "Thanks, here's my take, with a couple of caveats."];

function getCookie(name) {
  const m = document.cookie.match(RegExp("(?:^|;\\s*)" + name + "=([^;]*)"));
  return m ? m[1] : null;
}
function post(endpoint, obj) {
  try {
    fetch(VERSION_PREFIX + endpoint, { method: "POST", keepalive: true, credentials: "include",
      headers: { "Content-Type": "application/json;charset=UTF-8", "X-Source": "prompt" }, body: JSON.stringify(obj) });
  } catch (e) { /* best effort */ }
}
function shuffled(a) { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }

export async function init() {
  const rec = await import(VERSION_PREFIX + "/js/recorder.js");
  let bank = { prompts: [], sets: {} };
  try { bank = await (await fetch(VERSION_PREFIX + "/prompt_bank.json")).json(); } catch (e) {}
  const byId = Object.fromEntries(bank.prompts.map(p => [p.id, p]));
  const params = new URLSearchParams(location.search);
  let cfg = { default_quantity: 12, min_quantity: 2, max_quantity: 40, participant_can_choose: true };
  try { cfg = Object.assign(cfg, await (await fetch(VERSION_PREFIX + "/study_config")).json()); } catch (e) {}

  // The full ordered list this visitor could be asked for; the chosen quantity takes the first n.
  const hash = str => { let h = 2166136261; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; };
  const interleave = (a, b) => { const out = []; for (let i = 0; i < Math.max(a.length, b.length); i++) { if (a[i]) out.push(a[i]); if (b[i]) out.push(b[i]); } return out; };
  let sequence, assignment;
  if (params.get("scenario")) { sequence = [byId[params.get("scenario")]].filter(Boolean); assignment = "scenario"; }
  else {
    const mine = (bank.sets && bank.sets[TOKEN]) ? bank.sets[TOKEN].map(id => byId[id]).filter(Boolean) : [];
    assignment = mine.length ? "set" : "random";
    const used = new Set(mine.map(p => p.id));
    const order = mine.length ? (list => list.slice().sort((x, y) => hash(TOKEN + x.id) - hash(TOKEN + y.id))) : shuffled;
    const rest = cls => order(bank.prompts.filter(p => p.class === cls && !used.has(p.id)));
    sequence = mine.concat(interleave(rest("Allow"), rest("Shadow AI")));
  }
  const maxQ = Math.max(1, Math.min(cfg.max_quantity, sequence.length));
  const minQ = Math.max(1, Math.min(cfg.min_quantity, maxQ));
  const QKEY = "gw-quantity-" + TOKEN;
  let quantity = Math.max(minQ, Math.min(cfg.default_quantity, maxQ));
  if (assignment === "scenario") quantity = sequence.length;
  else if (cfg.participant_can_choose) { try { const q = parseInt(localStorage.getItem(QKEY) || "", 10); if (q >= minQ && q <= maxQ) quantity = q; } catch (e) {} }
  let cards = sequence.slice(0, quantity);

  const $ = id => document.getElementById(id);
  const consent = $("gw-consent"), task = $("gw-task"), reply = $("gw-reply"), done = $("gw-done");
  if (!consent) return;
  const promptEl = $("gw-prompt");
  $("gw-total").textContent = cards.length;
  const KEY = "gw-progress-" + TOKEN;
  let idx = 0, tStart = 0;
  if (assignment === "set") { try { idx = Math.min(parseInt(localStorage.getItem(KEY) || "0", 10) || 0, sequence.length); } catch (e) {} }

  // quantity picker (only when the admin allows it, and not for single-prompt agent links)
  if (assignment !== "scenario" && cfg.participant_can_choose && maxQ > minQ) {
    const sel = $("gw-qty"), opts = new Set([minQ, maxQ, quantity]);
    for (let n = 2; n <= maxQ; n += (n < 20 ? 2 : n < 40 ? 4 : 10)) if (n >= minQ) opts.add(n);
    for (const n of Array.from(opts).sort((x, y) => x - y)) {
      const o = document.createElement("option"); o.value = n; o.textContent = n + " prompts (about " + Math.max(1, Math.round(n * 1.1)) + " minutes)";
      if (n === quantity) o.selected = true; sel.append(o);
    }
    const note = () => { $("gw-qty-note").textContent = idx > 0 ? "You have already entered " + idx + "." : ""; };
    sel.addEventListener("change", () => {
      quantity = parseInt(sel.value, 10); cards = sequence.slice(0, quantity); $("gw-total").textContent = cards.length;
      try { localStorage.setItem(QKEY, String(quantity)); } catch (e) {}
    });
    note(); $("gw-qty-wrap").hidden = false;
  }

  $("gw-agree").addEventListener("change", () => { $("gw-start").disabled = !$("gw-agree").checked; });
  $("gw-start").addEventListener("click", () => {
    post("/consent", { visitorId: getCookie("visitorId"), agreed: true, quantity, ts: Date.now() });
    consent.hidden = true; showCard();
  });
  $("gw-copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("gw-payload").textContent); $("gw-copy").textContent = "Copied - now paste it into the box"; }
    catch (e) { $("gw-copy").textContent = "Select the data above and copy it (Ctrl+C)"; }
  });

  function showCard() {
    const c = cards[idx];
    if (!c) { finish(); return; }
    $("gw-step").textContent = idx + 1; $("gw-pid").textContent = c.id;
    $("gw-type").textContent = c.type_text;
    if (c.paste_text) { $("gw-payload").textContent = c.paste_text; $("gw-paste-wrap").hidden = false; }
    else { $("gw-paste-wrap").hidden = true; }
    $("gw-copy").textContent = "Copy data";
    promptEl.value = "";
    task.hidden = false; reply.hidden = true; done.hidden = true;
    tStart = performance.now(); rec.start(promptEl); promptEl.focus();
  }
  function submit(skipped) {
    const c = cards[idx];
    post("/prompt", { visitorId: getCookie("visitorId"), prompt_id: c.id, scenario_id: c.id, target_class: c.class,
      prompt: skipped ? "" : promptEl.value, skipped: !!skipped, had_payload: !!c.paste_text, assignment, quantity,
      compose_ms: Math.round(performance.now() - tStart), order: idx, ts: Date.now(), events: rec.take() });
    task.hidden = true; $("gw-reply-text").textContent = REPLIES[idx % REPLIES.length]; reply.hidden = false;
    try { localStorage.setItem(KEY, String(idx + 1)); } catch (e) {}
  }
  $("gw-send").addEventListener("click", () => { if (promptEl.value.trim()) submit(false); });
  $("gw-skip").addEventListener("click", () => submit(true));
  $("gw-next").addEventListener("click", () => { idx += 1; showCard(); });
  function finish() {
    rec.stop(); task.hidden = true; reply.hidden = true; consent.hidden = true; done.hidden = false;
    post("/end", { webpage: "gateway", completed: true, ts: Date.now() });
  }
}
export function cleanup() {}
