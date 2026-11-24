#!/usr/bin/env python3
"""Summarize the live gateway study for the paper. Run on the server, from the repository root:

    python3 study/study_metrics.py > study_metrics.json

Reads captures/ and the model versions under runtime/ and prints one JSON object of counts and
scores. It prints no prompt text, IP address, header or participant name: only link tokens' roles
(person P01..P20, agent profile), prompt ids, classes and numbers. The file is still study data:
copy it to the laptop with scp, and do not commit it.

What it reports, for the original models, the active version and every stored version:
  * entries by people and agents, per participant and per agent profile, skipped and pasted-whole
  * content model accuracy and recall by class (pool prompts are held out of training)
  * behavior model: people kept as human, agents caught, by agent profile
  * fused category accuracy and should-flag precision/recall/F1 (flag = Shadow AI or Automated
    content, or entered by an agent)
  * confusion matrices, Wilson 95% intervals, and the estimates stored with each model update
"""
import json, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "honeypot"))
import accuracy as acc            # noqa: E402
import inference as inf           # noqa: E402
import model_registry as reg      # noqa: E402

CLASSES = ["Allow", "Shadow AI", "Automated AI Pipelines"]
HARD = acc.HARD


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def frac(k, n):
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "ci95": wilson(k, n)}


def profile(token):
    if acc.actor_of(token) == "human":
        return "person"
    m = re.match(r"AG-([A-Z]+)-", token)
    return {"FILL": "fill_bot", "TYPE": "type_bot", "EVASIVE": "evasive_bot"}.get(m.group(1) if m else "", "agent_other")


def raw_entries(capture_dir):
    """Per-entry flags the scoring rows do not carry (skipped, pasted whole, compose time)."""
    out = []
    for fp in sorted(Path(capture_dir).glob("*_prompt.jsonl")):
        token = fp.name[:-len("_prompt.jsonl")]
        if acc.actor_of(token) is None:
            continue
        for line in open(fp, encoding="utf-8", errors="ignore"):
            try:
                b = json.loads(json.loads(line)["body"])
            except Exception:                         # noqa: BLE001
                continue
            if isinstance(b, dict):
                out.append({"token": token, "profile": profile(token), "prompt_id": b.get("prompt_id"),
                            "skipped": bool(b.get("skipped")) or not (b.get("prompt") or "").strip(),
                            "pasted_whole": bool(b.get("pasted_whole")), "had_payload": bool(b.get("had_payload")),
                            "compose_ms": b.get("compose_ms")})
    return out


def median_compose(raw):
    out = {}
    for g in sorted({r["profile"] for r in raw}):
        xs = sorted(r["compose_ms"] for r in raw if r["profile"] == g and not r["skipped"] and isinstance(r["compose_ms"], (int, float)))
        out[g] = round(xs[len(xs) // 2] / 1000, 1) if xs else None
    return out


def evaluate(rows, folder):
    conf_c = {t: Counter() for t in CLASSES}; conf_k = {t: Counter() for t in CLASSES}
    actor = defaultdict(lambda: [0, 0]); flag = Counter(); pa = defaultdict(lambda: [0, 0])
    for r in rows:
        c = inf.classify_content(r["prompt"], folder)[0]
        p = inf.actor_prob({k: r[k] for k in HARD}, folder)
        a = "agent" if p > 0.5 else "human"
        conf_c[r["true_content"]][c] += 1
        tk, pk = acc.category(r["true_content"], r["true_actor"]), acc.category(c, a)
        conf_k[tk][pk] += 1
        g = profile(r["token"]); actor[g][0] += (a == r["true_actor"]); actor[g][1] += 1
        part = r["token"] if r["true_actor"] == "human" else "agents"
        pa[part][0] += (a == "human") if r["true_actor"] == "human" else 0; pa[part][1] += 1 if r["true_actor"] == "human" else 0
        should = tk != "Allow"; did = pk != "Allow"
        flag[("tp" if did else "fn") if should else ("fp" if did else "tn")] += 1
        # single channels
        flag[("c_tp" if c != "Allow" else "c_fn") if should else ("c_fp" if c != "Allow" else "c_tn")] += 1
        flag[("b_tp" if a == "agent" else "b_fn") if should else ("b_fp" if a == "agent" else "b_tn")] += 1
    n = len(rows)
    def prf(pre):
        tp, fp, fn, tn = flag[pre + "tp"], flag[pre + "fp"], flag[pre + "fn"], flag[pre + "tn"]
        P = tp / (tp + fp) if tp + fp else None; R = tp / (tp + fn) if tp + fn else None
        F = 2 * P * R / (P + R) if P and R else None
        return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": P and round(P, 4), "recall": R and round(R, 4),
                "f1": F and round(F, 4), "precision_ci95": wilson(tp, tp + fp), "recall_ci95": wilson(tp, tp + fn)}
    hum = [v for g, v in actor.items() if g == "person"]; ag = [v for g, v in actor.items() if g != "person"]
    return {
        "n_entries": n,
        "content_accuracy": frac(sum(conf_c[t][t] for t in CLASSES), n),
        "content_recall_by_class": {t: frac(conf_c[t][t], sum(conf_c[t].values())) for t in CLASSES if conf_c[t]},
        "content_confusion_true_to_pred": {t: dict(conf_c[t]) for t in CLASSES},
        "behavior_people_kept": frac(sum(v[0] for v in hum), sum(v[1] for v in hum)),
        "behavior_agents_caught": frac(sum(v[0] for v in ag), sum(v[1] for v in ag)),
        "behavior_by_profile": {g: frac(*v) for g, v in sorted(actor.items())},
        "behavior_people_kept_by_participant": {t: frac(*v) for t, v in sorted(pa.items()) if t != "agents"},
        "category_accuracy": frac(sum(conf_k[t][t] for t in CLASSES), n),
        "category_confusion_true_to_pred": {t: dict(conf_k[t]) for t in CLASSES},
        "should_flag_fused": prf(""), "should_flag_content_only": prf("c_"), "should_flag_behavior_only": prf("b_"),
    }


def main():
    cap = acc.CAPTURE_DIR
    all_rows = acc.collected_rows(cap)
    rows = [r for r in all_rows if r["text_match"] >= acc.MIN_TEXT_MATCH]
    raw = raw_entries(cap)
    people = sorted({r["token"] for r in raw if r["profile"] == "person"})
    feat_means = {}
    for who in ("human", "agent"):
        sub = [r for r in rows if r["true_actor"] == who]
        feat_means[who] = {k: round(sum(float(r[k] or 0) for r in sub) / len(sub), 4) if sub else None for k in HARD}
    out = {
        "data": {
            "entries_logged": len(raw), "entries_skipped": sum(r["skipped"] for r in raw),
            "entries_by_profile": dict(Counter(r["profile"] for r in raw)),
            "participants": len(people), "entries_per_participant": dict(Counter(r["token"] for r in raw if r["profile"] == "person")),
            "agent_sessions": len({r["token"] for r in raw if r["profile"] != "person"}),
            "pasted_whole_entries": dict(Counter(r["profile"] for r in raw if r["pasted_whole"] and not r["skipped"])),
            "with_payload_entries": dict(Counter(r["profile"] for r in raw if r["had_payload"] and not r["skipped"])),
            "compose_seconds_median": median_compose(raw),
            "scored_rows": len(all_rows), "rows_with_text_match_ok": len(rows), "min_text_match": acc.MIN_TEXT_MATCH,
            "scored_rows_by_actor_and_class": {f"{a}|{c}": n for (a, c), n in Counter((r["true_actor"], r["true_content"]) for r in rows).items()},
            "distinct_prompts_entered": len({r["prompt_id"] for r in rows}),
            "behavior_feature_means": feat_means,
        },
        "models": {},
        "versions": [],
    }
    folders = [("original", reg.BASELINE_DIR)]
    act = reg.active_id()
    for m in reg.list_versions():
        vid = m["version_id"]
        if vid == "baseline":
            continue
        folders.append((vid, reg.VERSIONS / vid))
        out["versions"].append({"version_id": vid, "created_at": m.get("created_at"), "note": m.get("note"), "kind": m.get("kind"),
                                "active": vid == act, "content": m.get("content"), "actor": m.get("actor"),
                                "stored_report": {k: (m.get("report") or {}).get(k) for k in (
                                    "n_rows", "current_models", "refined_actor_leave_participants_out",
                                    "refined_content_leave_prompts_out", "refined_category_heldout", "content_retrained")}})
    out["active_version"] = act
    for name, folder in folders:
        try:
            out["models"][name] = evaluate(rows, folder)
        except Exception as e:                        # noqa: BLE001
            out["models"][name] = {"error": f"{type(e).__name__}: {e}"}
    json.dump(out, sys.stdout, indent=1, default=str)


if __name__ == "__main__":
    main()
