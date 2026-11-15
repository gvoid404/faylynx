#!/usr/bin/env python3
"""Accuracy of the detector models, for Admin > Model accuracy (standard library only).

Three figures per model version, each the share judged correctly:
  content    the category from the prompt text alone (Allow / Shadow AI / Automated)
  behavior   person or agent, from typing and mouse behavior
  combined   the final gateway category, both models together

Every figure is taken on data the version was not trained on:
  original models   scored here on all collected study entries (they never saw them). With
                    fewer than MIN_ENTRIES entries: the content model's score on the held-out
                    prompt pool and the behavior model's cross-validation score.
  model updates     the estimates stored when the update was made, with participants held out
                    for the behavior model and prompts held out for the content model
                    (study/refine_models.py).
"""
import difflib, json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import inference as inf
import model_registry as reg

HERE = Path(__file__).resolve().parent
CAPTURE_DIR = HERE.parent / "captures"
BANK_FILE = HERE / "site" / "prompt_bank.json"
HARD = ["inter_key_cv", "dwell_cv", "mouse_straightness", "prog_fill_ratio", "paste_to_type_ratio", "has_mouse", "has_typing"]
CLASSES = ["Allow", "Shadow AI", "Automated AI Pipelines"]
MIN_ENTRIES = 20            # fewest usable entries before the collected data is used as the test
MIN_TEXT_MATCH = 0.6        # entries whose text is far from the assigned prompt are left out
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_rows_cache = {}            # signature of the capture files -> rows
_score_cache = {}           # (rows signature, model folder, model file times) -> scores


# ------------------------------------------------------------------ collected entries
def actor_of(token):
    """Who entered it, from the link token: P01..P99 = a person, AG-... = the agent driver."""
    if re.fullmatch(r"P\d{2}", token): return "human"
    if token.startswith("AG-"): return "agent"
    return None


def category(content, actor):
    """The gateway's category rule (Shadow AI outranks Automated)."""
    if content == "Shadow AI": return "Shadow AI"
    if content == "Automated AI Pipelines" or actor == "agent": return "Automated AI Pipelines"
    return "Allow"


def _squash(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def collected_rows(capture_dir=CAPTURE_DIR, bank=None):
    """One row per prompt entered by a participant or the agent driver: who entered it, which pool
    prompt it was, the text, how closely the text matches the assigned prompt (0..1), and the seven
    behavior features. Skipped prompts, test links and entries without behavior data are left out."""
    if bank is None:
        bank = json.load(open(BANK_FILE, encoding="utf-8"))
    byid = {p["id"]: p for p in bank["prompts"]}
    rows = []
    for fp in sorted(Path(capture_dir).glob("*_prompt.jsonl")):
        token = fp.name[:-len("_prompt.jsonl")]
        actor = actor_of(token)
        if actor is None:
            continue
        for line in open(fp, encoding="utf-8", errors="ignore"):
            if not line.strip():
                continue
            try:
                b = json.loads(json.loads(line)["body"])
            except Exception:                                       # noqa: BLE001
                continue
            if not isinstance(b, dict) or b.get("skipped") or not (b.get("prompt") or "").strip():
                continue
            p = byid.get(b.get("prompt_id"))
            if not p:
                continue
            x = inf.behavior_features(b.get("events") or [])
            if x is None:
                continue
            expected = p["type_text"] + (("\n\n" + p["paste_text"]) if p.get("paste_text") else "")
            match = difflib.SequenceMatcher(None, _squash(b["prompt"]), _squash(expected)).ratio()
            rows.append({"token": token, "true_actor": actor, "prompt_id": p["id"], "true_content": p["class"],
                         "prompt": b["prompt"], "text_match": round(match, 3), **{k: x[k] for k in HARD}})
    return rows


def _signature(capture_dir):
    sig = []
    d = Path(capture_dir)
    if d.is_dir():
        for fp in sorted(d.glob("*_prompt.jsonl")):
            try:
                st = fp.stat(); sig.append((fp.name, st.st_mtime_ns, st.st_size))
            except OSError:
                pass
    return tuple(sig)


def study_rows(capture_dir=CAPTURE_DIR):
    """Usable entries (text close to the assigned prompt), read again only when the files change."""
    sig = _signature(capture_dir)
    key = str(capture_dir)
    hit = _rows_cache.get(key)
    if not hit or hit[0] != sig:
        rows = [r for r in collected_rows(capture_dir) if r["text_match"] >= MIN_TEXT_MATCH]
        _rows_cache[key] = (sig, rows)
    return _rows_cache[key][1], sig


def _share(flags):
    flags = list(flags)
    return round(sum(flags) / len(flags), 3) if flags else None


def score(rows, folder):
    """How the models stored in `folder` do on `rows`."""
    content_ok, actor_ok, both_ok = [], [], []
    by_class = {c: [] for c in CLASSES}
    people, agents = [], []
    for r in rows:
        c = inf.classify_content(r["prompt"], folder)[0]
        a = "agent" if inf.actor_prob({k: r[k] for k in HARD}, folder) > 0.5 else "human"
        content_ok.append(c == r["true_content"]); by_class[r["true_content"]].append(c == r["true_content"])
        actor_ok.append(a == r["true_actor"])
        (people if r["true_actor"] == "human" else agents).append(a == r["true_actor"])
        both_ok.append(category(c, a) == category(r["true_content"], r["true_actor"]))
    return {"content": _share(content_ok), "behavior": _share(actor_ok), "combined": _share(both_ok),
            "content_by_category": {c: _share(v) for c, v in by_class.items() if v},
            "people_kept": _share(people), "agents_caught": _share(agents)}


def _score_cached(rows, sig, folder):
    folder = Path(folder)
    key = (sig, str(folder), tuple((folder / f).stat().st_mtime_ns for f in reg.FILES))
    if key not in _score_cache:
        if len(_score_cache) > 6:
            _score_cache.clear()
        _score_cache[key] = score(rows, folder)
    return _score_cache[key]


# ------------------------------------------------------------------ dates in the reader's time
def _local(iso, tz_minutes):
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) + timedelta(minutes=tz_minutes)
    except (TypeError, ValueError):
        return None


def _day(dt):
    return f"{MONTHS[dt.month - 1]} {dt.day}"


def _clock(dt, seconds=False):
    sec = f":{dt.second:02d}" if seconds else ""
    return f"{dt.hour % 12 or 12}:{dt.minute:02d}{sec} {'AM' if dt.hour < 12 else 'PM'}"


def _date(dt):
    return f"{_day(dt)}, {dt.year}"


# ------------------------------------------------------------------ the report
def _counts(rows):
    people = [r for r in rows if r["true_actor"] == "human"]
    return {"entries": len(rows), "people": len(people), "agents": len(rows) - len(people),
            "participants": len({r["token"] for r in people})}


def _original_point(rows, sig):
    pt = {"version_id": "baseline", "kind": "original", "name": "Original models", "x_label": "Original",
          "made": None, "made_text": "", "content_carried_over": False}
    if len(rows) >= MIN_ENTRIES:
        c = _counts(rows)
        pt.update(_score_cached(rows, sig, reg.BASELINE_DIR))
        pt.update(basis="collected", entries=c["entries"],
                  basis_text=f"Measured on the {c['entries']} entries collected so far ({c['people']} by people, "
                             f"{c['agents']} by agents). The original models were not trained on any of them.")
        return pt
    meta = reg.baseline_meta()
    bank = json.load(open(BANK_FILE, encoding="utf-8"))
    sizes = {}
    for p in bank["prompts"]:
        sizes[p["class"]] = sizes.get(p["class"], 0) + 1
    by_class = (meta.get("content") or {}).get("bank_acc") or {}
    known = [c for c in CLASSES if c in by_class and sizes.get(c)]
    content = round(sum(by_class[c] * sizes[c] for c in known) / sum(sizes[c] for c in known), 3) if known else None
    held_out = ", which were held out of its training" if (meta.get("content") or {}).get("bank_held_out") else ""
    pt.update(content=content, behavior=(meta.get("actor") or {}).get("cv5_acc"), combined=None,
              content_by_category={c: by_class[c] for c in known}, people_kept=None, agents_caught=None,
              basis="before_study", entries=None,
              basis_text=f"There are not enough study entries yet ({len(rows)} so far, {MIN_ENTRIES} are needed). Until then: the content "
                         f"model on the {sum(sizes.values())} pool prompts{held_out}, and the "
                         "behavior model by cross-validation on scripted sessions. Both together is not measured yet.")
    return pt


def _update_point(meta, by_id, tz_minutes, zone=""):
    rep = meta.get("report") or {}
    ra = rep.get("refined_actor_leave_participants_out") or {}
    rc = rep.get("refined_content_leave_prompts_out") or {}
    rk = rep.get("refined_category_heldout") or {}
    before = rep.get("current_models") or {}
    carried = rep.get("content_retrained") is False
    content = rc.get("accuracy_by_entry", rc.get("accuracy"))
    by_class = rc.get("recall_by_class_by_entry") or rc.get("recall_by_class") or {}
    if carried:
        # A behavior-only update keeps the content model of the version it started from, so it shows
        # that version's content figure. (The figure stored with the update was taken on fewer
        # entries; using it would draw a change where the model did not change.)
        base = by_id.get(before.get("version"))
        if base and base.get("content") is not None:
            content, by_class = base["content"], base.get("content_by_category") or {}
        else:
            content, by_class = before.get("content_accuracy"), before.get("content_recall_by_class") or {}
    made = _local(meta.get("created_at"), tz_minutes)
    n = rep.get("n_rows")
    if not rep:                                   # e.g. a version imported from files
        text = "No accuracy figures were stored with this version."
    else:
        text = (f"Estimated when this version was made, on {n} entries, by testing on participants and prompts that "
                "were held out of training.") if n else "Estimated when this version was made."
        if carried:
            text += " Only the behavior model was retrained; the content model and its figure are those of the version before it."
        if rk.get("accuracy") is None:
            text += " Both together was not estimated for this version."
    return {"version_id": meta["version_id"], "kind": "update", "name": "Update", "made": meta.get("created_at"),
            "made_text": (_date(made) + ", " + _clock(made) + zone) if made else "", "_made": made,
            "content": content, "behavior": ra.get("accuracy"), "combined": rk.get("accuracy"),
            "content_by_category": by_class, "people_kept": ra.get("human_kept_as_human"),
            "agents_caught": ra.get("agent_caught"), "content_carried_over": carried,
            "basis": "held_out", "entries": n, "basis_text": text}


def report(tz_minutes=None, capture_dir=CAPTURE_DIR):
    """Everything the Model accuracy page shows. tz_minutes: the reader's offset from UTC in
    minutes (east is positive); without it, times are given in UTC and say so."""
    zone = "" if tz_minutes is not None else " UTC"
    tz_minutes = tz_minutes or 0
    rows, sig = study_rows(capture_dir)
    points = [_original_point(rows, sig)]
    by_id = {"baseline": points[0]}
    for meta in reg.list_versions()[1:]:
        pt = _update_point(meta, by_id, tz_minutes, zone)
        by_id[pt["version_id"]] = pt; points.append(pt)
    # label under the chart: the day; with the time when two updates share a day (and the seconds
    # when they share the minute)
    updates = [p for p in points if p["kind"] == "update"]
    days = [(_day(p["_made"]) if p["_made"] else None) for p in updates]
    minutes = [(f"{d} {_clock(p['_made'])}" if p["_made"] else None) for p, d in zip(updates, days)]
    for p, d, m in zip(updates, days, minutes):
        made = p.pop("_made")
        if not made:
            p["x_label"], p["name"] = p["version_id"], "Update " + p["version_id"]
            continue
        p["x_label"] = d if days.count(d) == 1 else m if minutes.count(m) == 1 else f"{d} {_clock(made, seconds=True)}"
        if minutes.count(m) > 1:
            p["made_text"] = f"{_date(made)}, {_clock(made, seconds=True)}{zone}"
        p["name"] = f"Update of {_date(made)}"
    active = reg.active_id()
    for p in points:
        p["in_use"] = (p["version_id"] == active)
    now = datetime.now(timezone.utc) + timedelta(minutes=tz_minutes)
    return {"generated_text": f"{_date(now)}, {_clock(now)}{zone}", "generated_day": now.strftime("%Y-%m-%d"),
            "collected": _counts(rows), "current": next((p for p in points if p["in_use"]), points[0]),
            "history": points}
