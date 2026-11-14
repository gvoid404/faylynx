#!/usr/bin/env python3
"""Refine the gateway models with the collected live data, and report how the current models did.

Reads every captures/<TOKEN>_prompt.jsonl pulled from the server. One row per submitted prompt:
entered text, prompt id + class (from the bank), and that prompt's keystroke/mouse events.
Who typed it comes from the token: P01..P99 = human participant, AG-... = agent driver.

Steps
  1. score the CURRENT models on the live rows (content, actor, fused 3-way category)
  2. honest estimate of the refined models:
       actor   - leave-participants-out (humans grouped by participant, agents by prompt id)
       content - leave-prompts-out (grouped by prompt id, so a prompt is never in train and test)
  3. retrain on everything and export models/content_model.json + models/actor_model.json
     (copy those two files to the server's honeypot/models/ - the detector hot-reloads them)

  python refine_models.py --captures captures_live --p2 ..
"""
import argparse, difflib, json, re, subprocess, sys
from pathlib import Path
from collections import Counter
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import inference as inf

HARD = ["inter_key_cv", "dwell_cv", "mouse_straightness", "prog_fill_ratio", "paste_to_type_ratio", "has_mouse", "has_typing"]
CLASSES = ["Allow", "Shadow AI", "Automated AI Pipelines"]


def category(content, actor):
    if content == "Shadow AI": return "Shadow AI"
    if content == "Automated AI Pipelines" or actor == "agent": return "Automated AI Pipelines"
    return "Allow"


def load_rows(cap, bank):
    byid = {p["id"]: p for p in bank["prompts"]}
    rows = []
    for fp in sorted(Path(cap).glob("*_prompt.jsonl")):
        token = fp.name[:-len("_prompt.jsonl")]
        actor = "human" if re.fullmatch(r"P\d{2}", token) else ("agent" if token.startswith("AG-") else None)
        for line in open(fp, encoding="utf-8"):
            if not line.strip(): continue
            rec = json.loads(line)
            try: b = json.loads(rec["body"])
            except Exception: continue
            if b.get("skipped") or not (b.get("prompt") or "").strip() or actor is None: continue
            p = byid.get(b.get("prompt_id"))
            if not p: continue
            x = inf.behavior_features(b.get("events") or [])
            if x is None: continue
            expected = p["type_text"] + (("\n\n" + p["paste_text"]) if p.get("paste_text") else "")
            sim = difflib.SequenceMatcher(None, re.sub(r"\s+", " ", b["prompt"]).strip().lower(),
                                          re.sub(r"\s+", " ", expected).strip().lower()).ratio()
            rows.append({"token": token, "true_actor": actor, "prompt_id": p["id"], "true_content": p["class"],
                         "prompt": b["prompt"], "text_match": round(sim, 3),
                         "group_actor": token if actor == "human" else "AG:" + p["id"],
                         "ua": (rec.get("net") or {}).get("User-Agent", ""), "tls": (rec.get("net") or {}).get("X-TLS-Version", ""),
                         **{k: (np.nan if x[k] is None else x[k]) for k in HARD}})
    return pd.DataFrame(rows)


def prf(pred, truth):
    tp = int((pred & truth).sum()); fp = int((pred & ~truth).sum()); fn = int((~pred & truth).sum())
    p = tp / (tp + fp) if tp + fp else 0.0; r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--captures", required=True)
    ap.add_argument("--p2", default="..")
    ap.add_argument("--bank", default="prompt_bank.json")
    ap.add_argument("--out", default="models")
    ap.add_argument("--min-text-match", type=float, default=0.6, help="drop human rows whose text is far from the assigned prompt")
    a = ap.parse_args()
    bank = json.load(open(a.bank)); df = load_rows(a.captures, bank)
    if df.empty: sys.exit("no usable prompt rows found in " + a.captures)
    n0 = len(df); df = df[df.text_match >= a.min_text_match].reset_index(drop=True)
    rep = {"n_rows": len(df), "dropped_low_text_match": n0 - len(df),
           "by_actor": df.true_actor.value_counts().to_dict(), "by_content": df.true_content.value_counts().to_dict(),
           "participants": int(df[df.true_actor == "human"].token.nunique())}
    print(f"live rows: {len(df)} (dropped {n0-len(df)} low-match) | actors {rep['by_actor']} | content {rep['by_content']} | participants {rep['participants']}")

    # 1. current models on the live rows
    cp = [inf.classify_content(t)[0] for t in df.prompt]
    pa = [inf.actor_prob({k: (None if pd.isna(r[k]) else float(r[k])) for k in HARD}) for _, r in df.iterrows()]
    df["content_pred"] = cp; df["p_agent"] = np.round(pa, 3); df["actor_pred"] = np.where(df.p_agent > 0.5, "agent", "human")
    df["true_category"] = [category(c, x) for c, x in zip(df.true_content, df.true_actor)]
    df["pred_category"] = [category(c, x) for c, x in zip(df.content_pred, df.actor_pred)]
    truth_flag = df.true_category != "Allow"
    rep["current_models"] = {
        "content_accuracy": round(float((df.content_pred == df.true_content).mean()), 3),
        "content_recall_by_class": {c: round(float((df.content_pred[df.true_content == c] == c).mean()), 3) for c in CLASSES if (df.true_content == c).any()},
        "actor_accuracy": round(float((df.actor_pred == df.true_actor).mean()), 3),
        "human_kept_as_human": round(float((df.actor_pred[df.true_actor == "human"] == "human").mean()), 3) if (df.true_actor == "human").any() else None,
        "agent_caught": round(float((df.actor_pred[df.true_actor == "agent"] == "agent").mean()), 3) if (df.true_actor == "agent").any() else None,
        "category_accuracy_3way": round(float((df.pred_category == df.true_category).mean()), 3),
        "flag_content_only": prf(df.content_pred != "Allow", truth_flag),
        "flag_actor_only": prf(df.actor_pred == "agent", truth_flag),
        "flag_fused": prf(df.pred_category != "Allow", truth_flag)}
    print("current models:", json.dumps(rep["current_models"], indent=1))

    # 2. honest estimates for refined models
    from sklearn.model_selection import GroupKFold
    import xgboost as xgb
    sim = pd.concat([pd.read_csv(p).rename(columns={"true_actor": "label"})[HARD + ["label"]] for p in ["results/sessions_features.csv", "results/fusion_sessions.csv"] if Path(p).exists()], ignore_index=True)
    Xs = sim[HARD].astype(float).replace([np.inf, -np.inf], np.nan); ys = (sim.label == "agent").astype(int).values
    Xl = df[HARD].astype(float); yl = (df.true_actor == "agent").astype(int).values
    if df.true_actor.nunique() == 2 and df.group_actor.nunique() >= 5:
        hit = np.zeros(len(df), bool)
        for tr, te in GroupKFold(5).split(Xl, yl, df.group_actor):
            m = xgb.XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.1, subsample=0.9, colsample_bytree=0.9, eval_metric="logloss", random_state=1, base_score=0.5)
            m.fit(pd.concat([Xs, Xl.iloc[tr]]), np.concatenate([ys, yl[tr]]), sample_weight=np.concatenate([np.full(len(ys), 0.5), np.ones(len(tr))]))
            hit[te] = m.predict(Xl.iloc[te]) == yl[te]
        rep["refined_actor_leave_participants_out"] = {"accuracy": round(float(hit.mean()), 3),
            "human_kept_as_human": round(float(hit[yl == 0].mean()), 3), "agent_caught": round(float(hit[yl == 1].mean()), 3)}
        print("refined actor (leave-participants-out):", rep["refined_actor_leave_participants_out"])
    # content: unique (prompt_id) texts; leave-prompts-out on top of the base corpus is run by the trainer's bank holdout,
    # so here we report how adding OTHER bank prompts helps held-out bank prompts.
    Path("refine_tmp").mkdir(exist_ok=True)
    uniq = df.drop_duplicates("prompt_id")
    if uniq.prompt_id.nunique() >= 10:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        base = {}
        P2 = Path(a.p2)
        for s in [P2 / "data/labeled/wildchat48m_full_10k_fable_v3_judged.jsonl", P2 / "data/labeled/synthetic_shadow_v1.jsonl", P2 / "data/gold/gold_consolidated_v1_text.jsonl"]:
            if s.exists():
                for l in open(s, encoding="utf-8"):
                    d = json.loads(l)
                    if d.get("label") in CLASSES and len((d.get("prompt") or "")) >= 15: base[d["prompt"].strip()[:4000]] = (d["label"], d.get("id"))
        held_ids = {p["source_id"] for p in bank["prompts"]}
        bt = [t for t, (l, i) in base.items() if i not in held_ids]; bl = [base[t][0] for t in bt]
        ok = np.zeros(len(uniq), bool); U = uniq.reset_index(drop=True)
        for tr, te in GroupKFold(5).split(U, U.true_content, U.prompt_id):
            vec = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=2, max_features=30000)
            X = vec.fit_transform(bt + list(U.prompt.iloc[tr])); w = np.concatenate([np.ones(len(bt)), np.full(len(tr), 5.0)])
            clf = LogisticRegression(max_iter=3000, class_weight="balanced", C=4.0).fit(X, bl + list(U.true_content.iloc[tr]), sample_weight=w)
            ok[te] = clf.predict(vec.transform(U.prompt.iloc[te])) == U.true_content.iloc[te].values
        rep["refined_content_leave_prompts_out"] = {"accuracy": round(float(ok.mean()), 3),
            "recall_by_class": {c: round(float(ok[(U.true_content == c).values].mean()), 3) for c in CLASSES if (U.true_content == c).any()}}
        print("refined content (leave-prompts-out):", rep["refined_content_leave_prompts_out"])

    # 3. final refit on everything + export
    extra_c = Path("refine_tmp/live_content.jsonl")
    with open(extra_c, "w", encoding="utf-8") as f:
        for _, r in df.drop_duplicates("prompt").iterrows():
            f.write(json.dumps({"id": "live:" + r.prompt_id + ":" + r.token, "prompt": r.prompt, "label": r.true_content}) + "\n")
    extra_a = Path("refine_tmp/live_actor.csv"); d2 = df[HARD].copy(); d2["label"] = df.true_actor.values; d2.to_csv(extra_a, index=False)
    df.drop(columns=["prompt"]).to_csv("refine_tmp/live_rows_scored.csv", index=False)
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "train_and_export.py"), "--p2", a.p2, "--bank", a.bank,
                    "--extra-content", str(extra_c), "--extra-actor", str(extra_a), "--include-bank", "--out", a.out, "--tag", "v4_live"], check=True)
    json.dump(rep, open("refine_report.json", "w"), indent=1)
    print(f"\nwrote refine_report.json and {a.out}/content_model.json + actor_model.json (tag v4_live)")
    print("next: copy those two model files to the server's honeypot/models/ - the Live Detector picks them up automatically")


if __name__ == "__main__":
    main()
