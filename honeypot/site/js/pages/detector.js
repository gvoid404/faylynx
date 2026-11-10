// Live Detector: posts the prompt and this prompt's keystroke/mouse events to /<TOKEN>/classify and
// shows the fused gateway category returned by the server (content model + behavior model).
const VERSION_PREFIX = "/" + (location.pathname.split("/")[1] || "");
let rec = null, last = null;
const pct = v => Math.round(v * 100) + "%";
const LABEL = { "Allow": "Allow", "Shadow AI": "Shadow AI", "Automated AI Pipelines": "Automated AI Pipeline" };
const CLS = { "Allow": "dt-allow", "Shadow AI": "dt-shadow", "Automated AI Pipelines": "dt-auto" };

export async function init() {
  rec = await import(VERSION_PREFIX + "/js/recorder.js");
  const $ = id => document.getElementById(id);
  const box = $("dt-prompt");
  if (!box) return;
  rec.start(box);
  $("dt-clear").addEventListener("click", () => { box.value = ""; rec.start(box); $("dt-result").hidden = true; box.focus(); });
  $("dt-go").addEventListener("click", async () => {
    const prompt = box.value;
    if (!prompt.trim()) return;
    $("dt-go").disabled = true; $("dt-status").textContent = "Analyzing...";
    try {
      const res = await fetch(VERSION_PREFIX + "/classify", { method: "POST",
        headers: { "Content-Type": "application/json;charset=UTF-8", "X-Source": "classify" },
        body: JSON.stringify({ prompt, events: rec.take(), ts: Date.now() }) });
      const r = await res.json();
      if (r.error) throw new Error(r.error);
      last = r; render(r); $("dt-status").textContent = "";
    } catch (e) { $("dt-status").textContent = "Could not analyze: " + e.message; }
    $("dt-go").disabled = false; rec.start(box);
  });
  document.querySelectorAll("#dt-fb button").forEach(b => b.addEventListener("click", () => {
    if (!last) return;
    fetch(VERSION_PREFIX + "/feedback", { method: "POST", headers: { "Content-Type": "application/json;charset=UTF-8", "X-Source": "feedback" },
      body: JSON.stringify({ request_id: last.request_id, true_class: b.dataset.c, predicted: last.category, ts: Date.now() }) });
    $("dt-fb-msg").textContent = "Thanks, recorded: " + LABEL[b.dataset.c];
  }));

  function render(r) {
    const v = $("dt-verdict"); v.textContent = LABEL[r.category] || r.category; v.className = "dt-verdict " + (CLS[r.category] || "");
    const order = ["Allow", "Shadow AI", "Automated AI Pipelines"];
    $("dt-content").innerHTML = order.map(c => {
      const p = (r.content_probs && r.content_probs[c]) || 0;
      return `<div>${LABEL[c]} <span class="dt-small">${pct(p)}</span></div><div class="dt-bar"><span style="width:${pct(p)}"></span></div>`;
    }).join("");
    const b = r.behavior || {};
    const f = x => (x === null || x === undefined ? "n/a" : x);
    $("dt-actor").innerHTML = r.actor === null ? "<div>No typing or mouse activity was captured.</div>" :
      `<div><strong>${r.actor === "automated" ? "Looks automated" : "Looks human"}</strong> <span class="dt-small">(${pct(r.p_automated)} automated)</span></div>
       <div class="dt-bar"><span style="width:${pct(r.p_automated)}"></span></div>
       <div class="dt-small">keystrokes ${f(b._n_keydown)} · pastes ${f(b._n_paste)} · typing-rhythm variation ${f(b.inter_key_cv)} · key-hold variation ${f(b.dwell_cv)} · mouse straightness ${f(b.mouse_straightness)} · filled without typing ${f(b.prog_fill_ratio)}</div>`;
    $("dt-models").textContent = "models: content " + (r.models ? r.models.content : "?") + ", behavior " + (r.models ? r.models.actor : "?");
    $("dt-fb-msg").textContent = ""; $("dt-result").hidden = false;
  }
}
export function cleanup() { if (rec) rec.stop(); }
