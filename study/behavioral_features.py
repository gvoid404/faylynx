#!/usr/bin/env python3
"""
behavioral_features.py

Turns the browsing-agent honeypot's per-session captures into one feature row per session, for the
behavioral fingerprint model (Paper 2, Phase 3). Reads the honeypot `captures/` directory:

  captures/<TOKEN>_mm.jsonl    event stream (one HTTP POST per line; body holds an eventFrames list)
  captures/<TOKEN>_end.jsonl   present only if the task was completed
  captures/manifest.jsonl      one row per session from run_batch.py: token, bot, scenario, status, ...

A "session" is a <TOKEN> (the per-session URL version in the honeypot). The label (bot vs human,
which framework) comes from the manifest; pass --human-tokens or a manifest with a `bot` of "human"
for the control baseline.

Event formats (from honeypot/site/js/script.js; timestamp is always the last element):
  ["mm", selector, x, y, t]                 mouse move
  ["md"/"mu", selector, button, x, y, t]    mouse button
  ["kd"/"ku", selector, key, repeat, t]     key down / up
  ["i", selector, inputType, value, t]      input (value is the full field value)
  ["c", selector, value, (checked,) t]      change
  ["p", selector, text, t]                  paste
  ["sc"/"se", target, scrollX, scrollY, t]  scroll / scroll end

  python behavioral_features.py --captures /path/to/captures --out sessions_features.jsonl
  # then --csv sessions_features.csv for a flat table, or feed the jsonl to the model notebook.

Features are deliberately the ones that separate a typing human from a driven browser: keystroke
cadence and its regularity, dwell time, mouse-path straightness, paste-vs-type ratio, programmatic
fill (input with no preceding keystrokes), and overall event cadence. No raw text or coordinates
leave this script; only aggregate statistics.
"""
import argparse, json, math, os, re, statistics as st
from collections import Counter, defaultdict
from pathlib import Path

MM_RE = re.compile(r"^(?P<token>[A-Z0-9_\-]{1,32})_mm\.jsonl$")


def read_jsonl(p):
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try: yield json.loads(line)
                except Exception: continue


def event_frames(mm_path):
    """Yield event lists in order. Each capture POST body holds {'eventFrames': [...]}; concatenate."""
    for rec in read_jsonl(mm_path):
        body = rec.get("body")
        if not body: continue
        try: d = json.loads(body)
        except Exception: continue
        for ev in d.get("eventFrames", []):
            if isinstance(ev, list) and len(ev) >= 2:
                yield ev, rec.get("ua", "")


def _t(ev):
    """Timestamp is always the last element (performance.now() ms)."""
    try: return float(ev[-1])
    except Exception: return None


def _cv(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2: return None
    m = st.mean(xs)
    return (st.pstdev(xs) / m) if m else None


def session_features(mm_path):
    evs = []
    ua = ""
    for ev, u in event_frames(mm_path):
        evs.append(ev)
        if u and not ua: ua = u
    if not evs:
        return None
    codes = Counter(ev[0] for ev in evs)
    ts = [t for t in (_t(ev) for ev in evs) if t is not None]
    ts.sort()
    duration = (ts[-1] - ts[0]) / 1000.0 if len(ts) >= 2 else 0.0   # seconds
    n = len(evs)

    # --- keystrokes ---
    kd = [ev for ev in evs if ev[0] == "kd"]
    ku = [ev for ev in evs if ev[0] == "ku"]
    kd_t = sorted(_t(ev) for ev in kd if _t(ev) is not None)
    inter_key = [b - a for a, b in zip(kd_t, kd_t[1:])] if len(kd_t) > 1 else []
    # dwell: match each keydown to the next keyup on the same selector+key
    dwell = []
    ku_by = defaultdict(list)
    for ev in ku:
        if len(ev) >= 4: ku_by[(ev[1], ev[2])].append(_t(ev))
    for ev in kd:
        if len(ev) >= 4:
            downs = _t(ev); ups = [u for u in ku_by.get((ev[1], ev[2]), []) if u is not None and u >= downs]
            if downs is not None and ups: dwell.append(min(ups) - downs)

    # --- mouse ---
    mm = [ev for ev in evs if ev[0] == "mm"]
    pts = [(float(ev[2]), float(ev[3])) for ev in mm if len(ev) >= 5 and _isnum(ev[2]) and _isnum(ev[3])]
    path_len = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) if len(pts) > 1 else 0.0
    net_disp = math.dist(pts[0], pts[-1]) if len(pts) > 1 else 0.0
    straightness = (net_disp / path_len) if path_len > 0 else None   # 1.0 = perfectly straight (machine-like)

    # --- paste vs type, programmatic fill ---
    n_paste = codes.get("p", 0); n_input = codes.get("i", 0)
    typed_chars = 0
    for ev in kd:
        k = ev[2] if len(ev) >= 3 else ""
        if isinstance(k, str) and len(k) == 1: typed_chars += 1
    paste_chars = sum(len(str(ev[2])) for ev in evs if ev[0] == "p" and len(ev) >= 3)
    # inputs whose selector never saw a keydown before that input = programmatic fill()
    kd_selectors_by_time = sorted(((_t(ev), ev[1]) for ev in kd if _t(ev) is not None))
    prog_fill = 0
    for ev in evs:
        if ev[0] == "i":
            it = _t(ev); sel = ev[1]
            had_key = any(sel == s and t <= it for t, s in kd_selectors_by_time)
            if not had_key: prog_fill += 1

    feats = {
        "n_events": n,
        "duration_s": round(duration, 3),
        "events_per_s": round(n / duration, 3) if duration > 0 else None,
        "time_to_first_event_s": None,   # filled by caller if a session start is known
        # keystrokes
        "n_keydown": len(kd),
        "inter_key_mean_ms": round(st.mean(inter_key), 2) if inter_key else None,
        "inter_key_cv": round(_cv(inter_key), 4) if _cv(inter_key) is not None else None,   # low CV = machine-regular
        "dwell_mean_ms": round(st.mean(dwell), 2) if dwell else None,
        "dwell_cv": round(_cv(dwell), 4) if _cv(dwell) is not None else None,
        # mouse
        "n_mousemove": len(mm),
        "mouse_path_px": round(path_len, 1),
        "mouse_straightness": round(straightness, 4) if straightness is not None else None,
        "has_mouse": len(mm) > 0,
        # paste vs type
        "n_paste": n_paste,
        "n_input": n_input,
        "typed_chars": typed_chars,
        "paste_chars": paste_chars,
        "paste_to_type_ratio": round(paste_chars / typed_chars, 3) if typed_chars else (None if paste_chars == 0 else float("inf")),
        "programmatic_fill_inputs": prog_fill,      # inputs with no preceding keystroke -> machine fill()
        "prog_fill_ratio": round(prog_fill / n_input, 3) if n_input else None,
        # scroll
        "n_scroll": codes.get("sc", 0) + codes.get("se", 0),
        # raw code counts (kept for the model to use or ignore)
        "code_counts": dict(codes),
        "user_agent": ua,
    }
    return feats


def _isnum(x):
    try: float(x); return True
    except Exception: return False


def load_manifest(captures):
    """token -> {bot, scenario, status, ...} from manifest.jsonl, if present."""
    mp = Path(captures) / "manifest.jsonl"
    out = {}
    if mp.exists():
        for r in read_jsonl(mp):
            tok = r.get("token") or r.get("version")
            if tok: out[str(tok)] = r
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--captures", required=True, help="honeypot captures/ directory")
    ap.add_argument("--out", required=True, help="output JSONL, one row per session")
    ap.add_argument("--csv", help="also write a flat CSV (code_counts and user_agent dropped)")
    ap.add_argument("--human-tokens", help="comma list or a file of session tokens to label human (overrides manifest)")
    args = ap.parse_args()
    cap = Path(args.captures)
    manifest = load_manifest(cap)
    human = set()
    if args.human_tokens:
        if os.path.exists(args.human_tokens):
            human = {l.strip() for l in open(args.human_tokens) if l.strip()}
        else:
            human = {t.strip() for t in args.human_tokens.split(",") if t.strip()}

    rows = []
    for fn in sorted(os.listdir(cap)):
        m = MM_RE.match(fn)
        if not m: continue
        token = m.group("token")
        feats = session_features(cap / fn)
        if feats is None: continue
        man = manifest.get(token, {})
        bot = "human" if token in human else (man.get("bot") or "unknown")
        feats = {"token": token, "bot": bot, "scenario": man.get("scenario"),
                 "status": man.get("status"), "label": "human" if bot == "human" else "agent",
                 "completed": (cap / f"{token}_end.jsonl").exists(), **feats}
        rows.append(feats)

    with open(args.out, "w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    labs = Counter(r["label"] for r in rows); bots = Counter(r["bot"] for r in rows)
    print(f"wrote {len(rows)} sessions -> {args.out} | labels {dict(labs)} | bots {dict(bots)}")
    if not manifest and not human:
        print("note: no manifest.jsonl and no --human-tokens, so every session is labeled 'agent'/unknown; "
              "point --captures at a run_batch.py output or pass --human-tokens for the control sessions.")

    if args.csv:
        import csv
        drop = {"code_counts", "user_agent"}
        cols = [k for k in rows[0].keys() if k not in drop] if rows else []
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
            for r in rows: w.writerow(r)
        print(f"wrote {args.csv} ({len(cols)} columns)")


if __name__ == "__main__":
    main()
