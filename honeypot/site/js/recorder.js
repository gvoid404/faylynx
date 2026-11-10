// Per-task behavior recorder (same event format as the site tracker in script.js):
//   ["kd"/"ku", sel, key, repeat, t]  ["i", sel, inputType, value, t]  ["p", sel, text, t]
//   ["mm", sel, x, y, t]  ["md"/"mu", sel, button, x, y, t]
// start(el) begins a fresh buffer for one prompt; take() returns the events and clears it.
let buf = [], target = null, on = false;
const sel = e => (e && e.id ? "#" + e.id : (e && e.tagName ? e.tagName.toLowerCase() : "?"));
const H = {
  keydown: e => { if (e.target === target) buf.push(["kd", sel(e.target), e.key, e.repeat, performance.now()]); },
  keyup: e => { if (e.target === target) buf.push(["ku", sel(e.target), e.key, e.repeat, performance.now()]); },
  input: e => { if (e.target === target) buf.push(["i", sel(e.target), e.inputType || "", "", performance.now()]); },
  paste: e => { if (e.target === target) { let t = ""; try { t = e.clipboardData.getData("text"); } catch (x) {}
                 buf.push(["p", sel(e.target), t, performance.now()]); } },
  mousemove: e => { if (buf.length < 6000) buf.push(["mm", sel(e.target), e.clientX, e.clientY, performance.now()]); },
  mousedown: e => buf.push(["md", sel(e.target), e.button, e.clientX, e.clientY, performance.now()]),
  mouseup: e => buf.push(["mu", sel(e.target), e.button, e.clientX, e.clientY, performance.now()]),
};
export function start(el) {
  target = el; buf = [];
  if (!on) { for (const k in H) window.addEventListener(k, H[k], { passive: true, capture: true }); on = true; }
}
export function take() { const out = buf; buf = []; return out; }
export function stop() { if (on) { for (const k in H) window.removeEventListener(k, H[k], { capture: true }); on = false; } }
