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
       both    - the final category from those two held-out predictions
  3. retrain on everything and write <out>/content_model.json + <out>/actor_model.json

The Admin page runs this on the server (Admin > Model updates). By hand:
  python refine_models.py --captures ../captures --corpus ../runtime/base_corpus.jsonl.gz \
      --verified ../runtime/verified_train_masked.jsonl.gz --out new_models
The verified file (Paper 2's 734 human-confirmed training rows, secrets masked) is required to retrain
the content model, so an update never drops real Shadow AI. The new content model is trained on masked
text and the gateway masks prompts before scoring them with it. Step 2b scores the update's recipe on
verified rows held out by near-duplicate group; the Admin page activates the new version only if that
real Shadow AI check passes.
Without a training corpus use --actor-only: the behavior model is retrained and the content model
is carried over unchanged.
Exit code 3 means there is not enough collected data yet.
"""
import argparse, json, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if not (HERE.parent / "honeypot" / "accuracy.py").is_file():
    sys.exit("refine_models.py runs from a full copy of the repository: it needs the honeypot/ folder next to study/.")
sys.path.insert(0, str(HERE.parent / "honeypot"))
import inference as inf                      # noqa: E402  (stdlib-only scorer + feature extraction)
import accuracy as acc                       # noqa: E402  (stdlib-only reader of the collected entries)

HARD = ["inter_key_cv", "dwell_cv", "mouse_straightness", "prog_fill_ratio", "paste_to_type_ratio", "has_mouse", "has_typing"]
CLASSES = ["Allow", "Shadow AI", "Automated AI Pipelines"]


def say(*a):
    print(*a, flush=True)


category = acc.category                       # the gateway's category rule, shared with the Admin page


def load_rows(cap, bank):
    """The collected entries as a table (same reader as Admin > Model accuracy)."""
    import pandas as pd
    rows = acc.collected_rows(cap, bank)
    for r in rows:
        r["group_actor"] = r["token"] if r["true_actor"] == "human" else "AG:" + r["prompt_id"]
    df = pd.DataFrame(rows)
    if len(df):
        df[HARD] = df[HARD].astype(float)       # a missing feature becomes NaN
    return df


def prf(pred, truth):
    tp = int((pred & truth).sum()); fp = int((pred & ~truth).sum()); fn = int((~pred & truth).sum())
    p = tp / (tp + fp) if tp + fp else 0.0; r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0}


def base_rows(a, bank, verified, mask_text):
    """Base corpus (+ verified rows), masked, with prompt-bank items left out: (texts, labels)."""
    sys.path.insert(0, str(HERE))
    from train_and_export import corpus_rows, norm
    held = {p["source_id"] for p in bank["prompts"]}
    heldtxt = {norm(p["type_text"] + (("\n\n" + p["paste_text"]) if p.get("paste_text") else "")) for p in bank["prompts"]}
    base = {}
    for i, t, lab in corpus_rows(a.corpus, a.p2):
        if lab in CLASSES and len(t) >= 15 and i not in held and norm(t) not in heldtxt:
            base[t[:4000]] = lab
    for d in verified:
        base[d["prompt"][:4000]] = d["label"]
    base = {mask_text(t): l for t, l in base.items()}           # the update trains on masked text
    return list(base), list(base.values())


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
    ap.add_argument("--verified", help="private masked file of the Paper 2 verified training rows (real Shadow AI). "
                    "Always included in content training, and used for the real Shadow AI check before activation")
    ap.add_argument("--floor-data-handling", type=float, default=None,
                    help="lowest acceptable held-out recall on real data-handling Shadow AI (the check fails below it)")
    ap.add_argument("--max-allow-false-alarm", type=float, default=None,
                    help="highest acceptable held-out false-alarm rate on real look-alike Allow prompts")
    ap.add_argument("--min-rows", type=int, default=20, help="fewest usable prompt entries needed to refine")
    ap.add_argument("--min-text-match", type=float, default=0.6, help="drop rows whose text is far from the assigned prompt")
    a = ap.parse_args()
    if not a.actor_only and not a.corpus and not a.p2:
        sys.exit("give --corpus or --p2 to retrain the content model, or use --actor-only")
    if not a.actor_only and not a.verified:
        sys.exit("retraining the content model needs --verified (the real Shadow AI rows); without them the update "
                 "loses real Shadow AI recall. Use --actor-only to update only the behavior model.")
    sys.path.insert(0, str(HERE.parent / "honeypot"))
    from mask_secrets import mask_text
    verified = []
    if a.verified:
        from train_and_export import read_jsonl
        verified = [d for d in read_jsonl(a.verified) if d.get("label") in CLASSES and (d.get("prompt") or "").strip()]
        say(f"verified real rows: {len(verified)}")

    import numpy as np, pandas as pd
    work = Path(a.work); work.mkdir(parents=True, exist_ok=True)
    bank = json.load(open(a.bank, encoding="utf-8"))
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

    bt, bl = base_rows(a, bank, verified, mask_text) if not a.actor_only else ([], [])
    # 2. honest estimates for the refined models
    say("step 2/3: estimating the refined models with participants and prompts held out")
    from sklearn.model_selection import GroupKFold
    import xgboost as xgb
    sim_files = [p for p in [HERE / "results/sessions_features.csv", HERE / "results/fusion_sessions.csv"] if p.exists()]
    sim = pd.concat([pd.read_csv(p).rename(columns={"true_actor": "label"})[HARD + ["label"]] for p in sim_files], ignore_index=True)
    Xs = sim[HARD].astype(float).replace([np.inf, -np.inf], np.nan); ys = (sim.label == "agent").astype(int).values
    Xl = df[HARD].astype(float); yl = (df.true_actor == "agent").astype(int).values
    actor_oof = content_oof = None               # held-out predictions, one per collected entry
    if df.true_actor.nunique() == 2 and df.group_actor.nunique() >= 5:
        hit = np.zeros(len(df), bool); actor_oof = np.empty(len(df), dtype=object)
        for tr, te in GroupKFold(5).split(Xl, yl, df.group_actor):
            m = xgb.XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.1, subsample=0.9, colsample_bytree=0.9,
                                  eval_metric="logloss", random_state=1, base_score=0.5)
            m.fit(pd.concat([Xs, Xl.iloc[tr]]), np.concatenate([ys, yl[tr]]),
                  sample_weight=np.concatenate([np.full(len(ys), 0.5), np.ones(len(tr))]))
            pred = m.predict(Xl.iloc[te])
            hit[te] = pred == yl[te]; actor_oof[te] = np.where(pred == 1, "agent", "human")
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
        ok = np.zeros(len(uniq), bool); pred_u = np.empty(len(uniq), dtype=object)
        for k, (tr, te) in enumerate(GroupKFold(5).split(uniq, uniq.true_content, uniq.prompt_id), 1):
            vec = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=2, max_features=30000)
            X = vec.fit_transform(bt + [mask_text(t) for t in uniq.prompt.iloc[tr]]); w = np.concatenate([np.ones(len(bt)), np.full(len(tr), 5.0)])
            clf = LogisticRegression(max_iter=3000, class_weight="balanced", C=4.0).fit(X, bl + list(uniq.true_content.iloc[tr]), sample_weight=w)
            pred_u[te] = clf.predict(vec.transform([mask_text(t) for t in uniq.prompt.iloc[te]]))
            ok[te] = pred_u[te] == uniq.true_content.iloc[te].values
            say(f"  content fold {k}/5 done")
        content_oof = df.prompt_id.map(dict(zip(uniq.prompt_id, pred_u))).values
        rep["refined_content_leave_prompts_out"] = {"accuracy": round(float(ok.mean()), 3),
            "accuracy_by_entry": round(float((content_oof == df.true_content.values).mean()), 3),
            "recall_by_class_by_entry": {c: round(float((content_oof[(df.true_content == c).values] == c).mean()), 3)
                                         for c in CLASSES if (df.true_content == c).any()},
            "recall_by_class": {c: round(float(ok[(uniq.true_content == c).values].mean()), 3) for c in CLASSES if (uniq.true_content == c).any()}}
        say("  refined content (prompts held out):", rep["refined_content_leave_prompts_out"])
    else:
        rep["refined_content_leave_prompts_out"] = None
    # both together: the final category from the two held-out predictions. When the content model is
    # carried over (behavior-only update) its current predictions are used.
    content_used = content_oof if content_oof is not None else (df.content_pred.values if a.actor_only else None)
    if actor_oof is not None and content_used is not None:
        cat = np.array([category(c, x) for c, x in zip(content_used, actor_oof)], dtype=object)
        rep["refined_category_heldout"] = {"accuracy": round(float((cat == df.true_category.values).mean()), 3),
                                           "content": "held out" if content_oof is not None else "carried over"}
        say("  refined final category (held out):", rep["refined_category_heldout"])
    else:
        rep["refined_category_heldout"] = None

    # 2b. real Shadow AI check: the update's recipe, scored on verified rows it did not train on
    #     (5 folds grouped by near-duplicate cluster). The Admin page activates the new version only if it passes.
    rep["real_shadow_check"] = None
    if not a.actor_only and verified:
        say("step 2b: real Shadow AI check (verified rows held out by near-duplicate group)")
        from sklearn.model_selection import StratifiedGroupKFold
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        real = [d for d in verified if d.get("kind") != "invented"]     # invented rows only ever train
        vtxt = [mask_text(d["prompt"][:4000]) for d in real]; vlab = [d["label"] for d in real]
        vkind = np.array([d.get("kind") or d["label"] for d in real]); vgrp = [d.get("group") or str(i) for i, d in enumerate(real)]
        vset = set(vtxt)
        other = {t: l for t, l in zip(bt, bl) if t not in vset}           # base corpus without the verified rows
        for t, l in zip(df.prompt, df.true_content):
            other[mask_text(t[:4000])] = l
        ot, ol = list(other), list(other.values())
        pred_v = np.empty(len(real), dtype=object)
        for k, (tr, te) in enumerate(StratifiedGroupKFold(5, shuffle=True, random_state=20261120).split(vtxt, vkind, vgrp), 1):
            vec = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=2, max_features=30000)
            X = vec.fit_transform(ot + [vtxt[i] for i in tr])
            clf = LogisticRegression(max_iter=3000, class_weight="balanced", C=4.0).fit(X, ol + [vlab[i] for i in tr])
            pred_v[te] = clf.predict(vec.transform([vtxt[i] for i in te]))
            say(f"  check fold {k}/5 done")
        def rate(mask_, want_shadow=True):
            n = int(mask_.sum()); k = int(((pred_v[mask_] == "Shadow AI") == want_shadow).sum())
            return {"k": k, "n": n, "rate": round(k / n, 4) if n else None}
        chk = {"data_handling_recall": rate(vkind == "data_handling"), "evasion_recall": rate(vkind == "evasion"),
               "allow_false_alarm": rate(vkind == "Allow")}
        dh = chk["data_handling_recall"]["rate"]; fa = chk["allow_false_alarm"]["rate"]
        reasons = []
        if a.floor_data_handling is not None and dh is not None and dh < a.floor_data_handling:
            reasons.append(f"real data-handling recall {dh:.3f} is below the floor {a.floor_data_handling:.3f}")
        if a.max_allow_false_alarm is not None and fa is not None and fa > a.max_allow_false_alarm:
            reasons.append(f"false alarms on real look-alike Allow prompts {fa:.3f} exceed {a.max_allow_false_alarm:.3f}")
        chk.update(passed=not reasons, reasons=reasons, floor_data_handling=a.floor_data_handling,
                   max_allow_false_alarm=a.max_allow_false_alarm)
        rep["real_shadow_check"] = chk
        say("  real Shadow AI check:", json.dumps(chk))

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
        cmd += ["--extra-content", str(extra_c), "--include-bank", "--verified", a.verified, "--mask"] + (["--corpus", a.corpus] if a.corpus else ["--p2", a.p2])
    subprocess.run(cmd, check=True)
    rep["tag"] = tag
    json.dump(rep, open(a.report, "w"), indent=1)
    shutil.rmtree(work, ignore_errors=True) if a.work != "refine_tmp" else None
    say(f"DONE: wrote {a.out}/content_model.json and {a.out}/actor_model.json, report {a.report}")


if __name__ == "__main__":
    main()
