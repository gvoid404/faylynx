// AI-gateway prompt-capture page. Shows a consent gate, then a sequence of scenario cards; the
// participant writes a prompt for each. On send we POST the prompt + its ground-truth class +
// light metadata to /<VERSION>/prompt (the server appends it to captures/<VERSION>_prompt.jsonl).
// Keystroke/mouse behavior on this page is recorded by the global tracker (js/script.js) into
// captures/<VERSION>_mm.jsonl, so prompt text, behavior, and connection data all share one token.

const VERSION_PREFIX = "/" + (location.pathname.split("/")[1] || "");
const N_CARDS = 4;                       // scenario cards per session
const REPLIES = [
  "Here's a draft — let me know if you'd like it shorter or in a different tone.",
  "Sure. Here's a summary of the key points you shared.",
  "Done. I've put that into a clean table for you.",
  "Thanks — here's my take on that, with a couple of caveats.",
];

function getCookie(name) {
  const m = document.cookie.match(RegExp("(?:^|;\\s*)" + name + "=([^;]*)"));
  return m ? m[1] : null;
}

function post(endpoint, obj) {
  try {
    fetch(VERSION_PREFIX + endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json;charset=UTF-8", "X-Source": "prompt" },
      body: JSON.stringify(obj),
      keepalive: true,
      credentials: "include",
    });
  } catch (e) { /* best effort */ }
}

function pickScenarios(all) {
  // human sessions: Allow + Shadow AI only; randomize, balance a bit
  const human = all.filter(s => s.class === "Allow" || s.class === "Shadow AI");
  for (let i = human.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [human[i], human[j]] = [human[j], human[i]];
  }
  // try to include at least one of each class
  const allow = human.filter(s => s.class === "Allow");
  const shadow = human.filter(s => s.class === "Shadow AI");
  const out = [];
  if (allow.length) out.push(allow[0]);
  if (shadow.length) out.push(shadow[0]);
  for (const s of human) { if (out.length >= N_CARDS) break; if (!out.includes(s)) out.push(s); }
  return out.slice(0, N_CARDS);
}

export async function init() {
  let scenarios = [];
  try {
    const res = await fetch(VERSION_PREFIX + "/gateway_scenarios.json");
    scenarios = (await res.json()).scenarios || [];
  } catch (e) { scenarios = []; }

  // ?scenario=<id> forces one card; ?class=<Allow|Shadow AI|Automated AI Pipelines> filters.
  // Used by the agent driver to enter a specific class (incl. Automated). No param => human flow.
  const params = new URLSearchParams(location.search);
  let cards;
  const forceId = params.get("scenario");
  const forceClass = params.get("class");
  if (forceId) {
    cards = scenarios.filter(s => s.id === forceId);
  } else if (forceClass) {
    cards = scenarios.filter(s => s.class === forceClass);
    for (let i = cards.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [cards[i], cards[j]] = [cards[j], cards[i]]; }
    cards = cards.slice(0, N_CARDS);
  } else {
    cards = pickScenarios(scenarios);
  }

  const $ = id => document.getElementById(id);
  const consent = $("gw-consent"), task = $("gw-task"), reply = $("gw-reply"), done = $("gw-done");
  const agree = $("gw-agree"), startBtn = $("gw-start");
  const stepEl = $("gw-step"), totalEl = $("gw-total");
  const titleEl = $("gw-title"), instrEl = $("gw-instruction"), payloadEl = $("gw-payload");
  const promptEl = $("gw-prompt"), sendBtn = $("gw-send"), skipBtn = $("gw-skip");
  const replyText = $("gw-reply-text"), nextBtn = $("gw-next");
  if (!consent) return;
  totalEl.textContent = cards.length || N_CARDS;

  let idx = 0, tStart = 0;

  agree.addEventListener("change", () => { startBtn.disabled = !agree.checked; });
  startBtn.addEventListener("click", () => {
    post("/consent", { visitorId: getCookie("visitorId"), agreed: true, ts: Date.now() });
    consent.hidden = true; showCard();
  });

  function showCard() {
    const c = cards[idx];
    if (!c) { finish(); return; }
    stepEl.textContent = idx + 1;
    titleEl.textContent = c.title;
    instrEl.textContent = c.instruction;
    if (c.payload) { payloadEl.textContent = c.payload; payloadEl.hidden = false; }
    else { payloadEl.hidden = true; }
    promptEl.value = "";
    task.hidden = false; reply.hidden = true; done.hidden = true;
    tStart = performance.now();
    promptEl.focus();
  }

  function submit(skipped) {
    const c = cards[idx];
    post("/prompt", {
      visitorId: getCookie("visitorId"),
      scenario_id: c.id,
      target_class: c.class,
      prompt: skipped ? "" : promptEl.value,
      had_payload: !!c.payload,
      skipped: !!skipped,
      compose_ms: Math.round(performance.now() - tStart),
      order: idx,
      ts: Date.now(),
    });
    task.hidden = true;
    replyText.textContent = REPLIES[idx % REPLIES.length];
    reply.hidden = false;
  }

  sendBtn.addEventListener("click", () => { if (promptEl.value.trim()) submit(false); });
  skipBtn.addEventListener("click", () => submit(true));
  nextBtn.addEventListener("click", () => { idx += 1; showCard(); });

  function finish() {
    task.hidden = true; reply.hidden = true; done.hidden = false;
    post("/end", { webpage: "gateway", completed: true, ts: Date.now() });
  }
}
