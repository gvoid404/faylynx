#!/usr/bin/env python3
"""Refine the PromptGate models with collected study data, and report how the current models did.

Reads every captures/<TOKEN>_prompt.jsonl. One row per submitted prompt: the entered text, the
prompt id and class (from the prompt bank), and that prompt's keystroke/mouse events. Who entered
it comes from the link token: P01..P99 = human participant, AG-... = agent driver. Other tokens
(tests) are ignored.

Steps
  1. score the CURRENT (active) models on the collected rows: content, actor, fused 3-way category
  2. honest estimates for the refined models
       actor   - leave-participants-out (humans grouped by participant, agents by prompt id)
       content - leave-prompts-out (a prompt is never in both train and test)
  3. retrain on everything and write <out>/content_model.json + <out>/actor_model.json

The Admin page runs this on the server (Admin > Model updates). By hand:
  python refine_models.py --captures ../captures --corpus ../runtime/base_corpus.jsonl.gz --out new_models
Without a training corpus use --actor-only: the behavior model is retrained and the content model
is carried over unchanged.
Exit code 3 means there is not enough collected data yet.
"""
import argparse, difflib, json, re, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
for cand in (HERE.parent / "honeypot", HERE):
    if (cand / "inference.py").is_file():
        sys.path.insert(0, str(cand)); break
import inference as inf                      # noqa: E402  (stdlib-only scorer + feature extraction)

HARD = ["inter_key_cv", "dwell_cv", "mouse_straightness", "prog_fill_ratio", "paste_to_type_ratio", "has_mouse", "has_typing"]
CLASSES = ["Allow", "Shadow AI", "Automated AI Pipelines"]


def say(*a):
    print(*a, flush=True)


def category(content, actor):
    if content == "Shadow AI": return "Shadow AI"
    if content == "Automated AI Pipelines" or actor == "agent": return "Automated AI Pipelines"
    return "Allow"


def actor_of(token):
    if re.fullmatch(r"P\d{2}", token): return "human"
    if token.startswith("AG-"): return "agent"
    return None


def load_rows(cap, bank):
    import numpy as np, pandas as pd
    byid = {p["id"]: p for p in bank["prompts"]}
    rows = []
    for fp in sorted(Path(cap).glob("*_prompt.jsonl")):
        token = fp.name[:-len("_prompt.jsonl")]; actor = actor_of(token)
        if actor is None:
            continue
        for line in open(fp, encoding="utf-8"):
            if not line.strip(): continue
            try:
                rec = json.loads(line); b = json.loads(rec["body"])
            except Exception:
                continue
            if b.get("skipped") or not (b.get("prompt") or "").strip(): continue
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
                         **{k: (np.nan if x[k] is None else x[k]) for k in HARD}})
    return pd.DataFrame(rows)


def prf(pred, truth):
    tp = int((pred & truth).sum()); fp = int((pred & ~truth).sum()); fn = int((~pred & truth).sum())
    p = tp / (tp + fp) if tp + fp else 0.0; r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--captures", required=True)
    ap.add_argument("--corpus", help="private training corpus (base_corpus.jsonl.gz)")
    ap.add_argument("--p2", help="paper2-three-class folder (alternative to --corpus on the laptop)")
    ap.add_argument("--actor-only", action="store_true", help="retrain only the behavior model; carry the content model over")
    ap.add_argument("--bank", default=str(HERE / "prompt_bank.json"))
    ap.add_argument("--out", default="models_refined")
    ap.add_argument("--report", default="refine_report.json")
    ap.add_argument("--work", default="refine_tmp")
    ap.add_argument("--min-rows", type=int, default=20, help="fewest usable prompt entries needed to refine")
    ap.add_argument("--min-text-match", type=float, default=0.6, help="drop rows whose text is far from the assigned prompt")
    a = ap.parse_args()
    if not a.actor_only and not a.corpus and not a.p2:
        sys.exit("give --corpus or --p2 to retrain the content model, or use --actor-only")

    import numpy as np, pandas as pd
    work = Path(a.work); work.mkdir(parents=True, exist_ok=True)
    bank = json.load(open(a.bank))
    say("reading collected prompts from", a.captures)
    df = load_rows(a.captures, bank)
    n0 = len(df)
    if n0:
        df = df[df.text_match >= a.min_text_match].reset_index(drop=True)
    rep = {"created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "n_rows": int(len(df)),
           "dropped_low_text_match": int(n0 - len(df)), "content_retrained": not a.actor_only,
           "by_actor": df.true_actor.value_counts().to_dict() if len(df) else {},
           "by_content": df.true_content.value_counts().to_dict() if len(df) else {},
           "participants": int(df[df.true_actor == "human"].token.nunique()) if len(df) else 0}
    say(f"usable entries: {len(df)} (dropped {n0 - len(df)} that did not match their assigned prompt) | "
        f"by actor {rep['by_actor']} | by class {rep['by_content']} | participants {rep['participants']}")
    if len(df) < a.min_rows:
        rep["error"] = f"Not enough collected data: {len(df)} usable prompt entries, need at least {a.min_rows}."
        json.dump(rep, open(a.report, "w"), indent=1)
        say("NOT ENOUGH DATA:", rep["error"]); sys.exit(3)

    # 1. current models on the collected rows
    say("step 1/3: scoring the current models on the collected data")
    df["content_pred"] = [inf.classify_content(t)[0] for t in df.prompt]
    df["p_agent"] = np.round([inf.actor_prob({k: (None if pd.isna(r[k]) else float(r[k])) for k in HARD}) for _, r in df.iterrows()], 3)
    df["actor_pred"] = np.where(df.p_agent > 0.5, "agent", "human")
    df["true_category"] = [category(c, x) for c, x in zip(df.true_content, df.true_actor)]
    df["pred_category"] = [category(c, x) for c, x in zip(df.content_pred, df.actor_pred)]
    truth_flag = df.true_category != "Allow"
    hum, agt = df.true_actor == "human", df.true_actor == "agent"
    rep["current_models"] = {
        "version": inf.registry.active_id(),
        "content_accuracy": round(float((df.content_pred == df.true_content).mean()), 3),
        "content_recall_by_class": {c: round(float((df.content_pred[df.true_content == c] == c).mean()), 3) for c in CLASSES if (df.true_content == c).any()},
        "actor_accuracy": round(float((df.actor_pred == df.true_actor).mean()), 3),
        "human_kept_as_human": round(float((df.actor_pred[hum] == "human").mean()), 3) if hum.any() else None,
        "agent_caught": round(float((df.actor_pred[agt] == "agent").mean()), 3) if agt.any() else None,
        "category_accuracy_3way": round(float((df.pred_category == df.true_category).mean()), 3),
        "flag_content_only": prf(df.content_pred != "Allow", truth_flag),
        "flag_actor_only": prf(df.actor_pred == "agent", truth_flag),
        "flag_fused": prf(df.pred_category != "Allow", truth_flag)}
    cm = rep["current_models"]
    say(f"  current models: content accuracy {cm['content_accuracy']}, actor accuracy {cm['actor_accuracy']}, "
        f"3-way category accuracy {cm['category_accuracy_3way']}")

    # 2. honest estimates for the refined models
    say("step 2/3: estimating the refined models with participants and prompts held out")
    from sklearn.model_selection import GroupKFold
    import xgboost as xgb
    sim_files = [p for p in [HERE / "results/sessions_features.csv", HERE / "results/fusion_sessions.csv"] if p.exists()]
    sim = pd.concat([pd.read_csv(p).rename(columns={"true_actor": "label"})[HARD + ["label"]] for p in sim_files], ignore_index=True)
    Xs = sim[HARD].astype(float).replace([np.inf, -np.inf], np.nan); ys = (sim.label == "agent").astype(int).values
    Xl = df[HARD].astype(float); yl = (df.true_actor == "agent").astype(int).values
    if df.true_actor.nunique() == 2 and df.group_actor.nunique() >= 5:
        hit = np.zeros(len(df), bool)
        for tr, te in GroupKFold(5).split(Xl, yl, df.group_actor):
            m = xgb.XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.1, subsample=0.9, colsample_bytree=0.9,
                                  eval_metric="logloss", random_state=1, base_score=0.5)
            m.fit(pd.concat([Xs, Xl.iloc[tr]]), np.concatenate([ys, yl[tr]]),
                  sample_weight=np.concatenate([np.full(len(ys), 0.5), np.ones(len(tr))]))
            hit[te] = m.predict(Xl.iloc[te]) == yl[te]
        rep["refined_actor_leave_participants_out"] = {"accuracy": round(float(hit.mean()), 3),
            "human_kept_as_human": round(float(hit[yl == 0].mean()), 3), "agent_caught": round(float(hit[yl == 1].mean()), 3)}
        say("  refined actor (participants held out):", rep["refined_actor_leave_participants_out"])
    else:
        rep["refined_actor_leave_participants_out"] = None
        say("  refined actor: not estimated (needs both humans and agents, and at least 5 groups)")
    uniq = df.drop_duplicates("prompt_id").reset_index(drop=True)
    if not a.actor_only and uniq.prompt_id.nunique() >= 10:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        sys.path.insert(0, str(HERE))
        from train_and_export import corpus_rows, norm
        held = {p["source_id"] for p in bank["prompts"]}
        heldtxt = {norm(p["type_text"] + (("\n\n" + p["paste_text"]) if p.get("paste_text") else "")) for p in bank["prompts"]}
        base = {}
        for i, t, lab in corpus_rows(a.corpus, a.p2):
            if lab in CLASSES and len(t) >= 15 and i not in held and norm(t) not in heldtxt:
                base[t[:4000]] = lab
        bt = list(base); bl = list(base.values())
        ok = np.zeros(len(uniq), bool)
        for k, (tr, te) in enumerate(GroupKFold(5).split(uniq, uniq.true_content, uniq.prompt_id), 1):
            vec = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=2, max_features=30000)
            X = vec.fit_transform(bt + list(uniq.prompt.iloc[tr])); w = np.concatenate([np.ones(len(bt)), np.full(len(tr), 5.0)])
            clf = LogisticRegression(max_iter=3000, class_weight="balanced", C=4.0).fit(X, bl + list(uniq.true_content.iloc[tr]), sample_weight=w)
            ok[te] = clf.predict(vec.transform(uniq.prompt.iloc[te])) == uniq.true_content.iloc[te].values
            say(f"  content fold {k}/5 done")
        rep["refined_content_leave_prompts_out"] = {"accuracy": round(float(ok.mean()), 3),
            "recall_by_class": {c: round(float(ok[(uniq.true_content == c).values].mean()), 3) for c in CLASSES if (uniq.true_content == c).any()}}
        say("  refined content (prompts held out):", rep["refined_content_leave_prompts_out"])
    else:
        rep["refined_content_leave_prompts_out"] = None

    # 3. final refit on everything + export
    say("step 3/3: retraining on all data and exporting the new model files")
    extra_c = work / "live_content.jsonl"
    with open(extra_c, "w", encoding="utf-8") as f:
        for _, r in df.drop_duplicates("prompt").iterrows():
            f.write(json.dumps({"id": "live:" + r.prompt_id + ":" + r.token, "prompt": r.prompt, "label": r.true_content}) + "\n")
    extra_a = work / "live_actor.csv"; d2 = df[HARD].copy(); d2["label"] = df.true_actor.values; d2.to_csv(extra_a, index=False)
    df.drop(columns=["prompt"]).to_csv(work / "live_rows_scored.csv", index=False)
    tag = "live-" + time.strftime("%Y%m%d", time.gmtime())
    cmd = [sys.executable, str(HERE / "train_and_export.py"), "--bank", a.bank, "--extra-actor", str(extra_a),
           "--out", a.out, "--tag", tag]
    if a.actor_only:
        cmd += ["--reuse-content", str(inf.registry.active_dir() / "content_model.json")]
    else:
        cmd += ["--extra-content", str(extra_c), "--include-bank"] + (["--corpus", a.corpus] if a.corpus else ["--p2", a.p2])
    subprocess.run(cmd, check=True)
    rep["tag"] = tag
    json.dump(rep, open(a.report, "w"), indent=1)
    shutil.rmtree(work, ignore_errors=True) if a.work != "refine_tmp" else None
    say(f"DONE: wrote {a.out}/content_model.json and {a.out}/actor_model.json, report {a.report}")


if __name__ == "__main__":
    main()
