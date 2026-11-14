#!/usr/bin/env python3
"""Train the two PromptGate models and export them as plain JSON for the stdlib-only server.

  content  TF-IDF (word 1-2 grams) + logistic regression, 3 classes
           (Allow / Shadow AI / Automated AI Pipelines)
  actor    XGBoost on 7 style-invariant behavior features (human vs automated agent)

Training text comes from --corpus (the compact private file made by build_base_corpus.py) or,
on a machine that has the Paper 2 folder, from --p2. Prompt-bank items are held out of content
training unless --include-bank is given (used for the final refined model). With --reuse-content
the content model is copied from an existing file instead of retrained (no corpus needed).

  python train_and_export.py --corpus base_corpus.jsonl.gz --out models --tag v3
"""
import argparse, gzip, json, re, shutil, sys, time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARD = ["inter_key_cv", "dwell_cv", "mouse_straightness", "prog_fill_ratio", "paste_to_type_ratio", "has_mouse", "has_typing"]
KEEP = {"Allow", "Shadow AI", "Automated AI Pipelines"}
norm = lambda t: re.sub(r"\s+", " ", t.strip())


def say(*a):
    print(*a, flush=True)


def read_jsonl(path):
    op = gzip.open if str(path).endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def corpus_rows(corpus, p2):
    """Yield (id, text, label) in the order later rows override earlier ones. With --p2 the rows are
    built exactly as build_base_corpus.py builds the corpus file, so the sealed Paper 2 test sets
    (Shadow test rows, the audit holdout and its near-duplicates) are left out either way."""
    if corpus:
        for d in read_jsonl(corpus):
            yield d.get("id"), (d.get("prompt") or "").strip(), d.get("label")
        return
    sys.path.insert(0, str(HERE))
    from build_base_corpus import corpus_from_p2
    rows, _ = corpus_from_p2(p2, log=say)
    for d in rows:
        yield d["id"], d["prompt"], d["label"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", help="compact training corpus (.jsonl or .jsonl.gz) from build_base_corpus.py")
    ap.add_argument("--p2", help="paper2-three-class folder (used when --corpus is not given)")
    ap.add_argument("--bank", default=str(HERE / "prompt_bank.json"))
    ap.add_argument("--actor-csv", nargs="+", default=[str(HERE / "results/sessions_features.csv"), str(HERE / "results/fusion_sessions.csv")])
    ap.add_argument("--extra-content", nargs="*", default=[], help="jsonl with prompt,label (e.g. live captures)")
    ap.add_argument("--extra-actor", nargs="*", default=[], help="csv with the 7 behavior features + label (human/agent)")
    ap.add_argument("--include-bank", action="store_true", help="do not hold the prompt bank out (final refined model)")
    ap.add_argument("--reuse-content", help="copy this content_model.json instead of retraining the content model")
    ap.add_argument("--out", default="models"); ap.add_argument("--tag", default="v3")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    import numpy as np, pandas as pd
    from sklearn.model_selection import cross_val_score, StratifiedKFold

    # ---------------- content ----------------
    if a.reuse_content:
        shutil.copyfile(a.reuse_content, out / "content_model.json")
        say(f"content: reused {a.reuse_content} (not retrained)")
    else:
        if not a.corpus and not a.p2:
            sys.exit("need --corpus or --p2 to train the content model (or --reuse-content)")
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        bank = json.load(open(a.bank))
        full = lambda b: b["type_text"] + (("\n\n" + b["paste_text"]) if b.get("paste_text") else "")
        held = set() if a.include_bank else {b["source_id"] for b in bank["prompts"]}
        heldtxt = set() if a.include_bank else {norm(full(b)) for b in bank["prompts"]}
        rows = {}
        for i, t, lab in corpus_rows(a.corpus, a.p2):
            if lab in KEEP and len(t) >= 15 and i not in held and norm(t) not in heldtxt:
                rows[t[:4000]] = lab
        for extra in a.extra_content:
            for d in read_jsonl(extra):
                t = (d.get("prompt") or "").strip()
                if d.get("label") in KEEP and len(t) >= 15:
                    rows[t[:4000]] = d["label"]
        texts = list(rows); labels = list(rows.values())
        say(f"content: training on {len(texts)} prompts {dict(Counter(labels))}")
        vec = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=2, max_features=30000)
        X = vec.fit_transform(texts); clf = LogisticRegression(max_iter=3000, class_weight="balanced", C=4.0)
        cv = cross_val_score(clf, X, labels, cv=StratifiedKFold(5, shuffle=True, random_state=7), scoring="f1_macro").mean()
        clf.fit(X, labels)
        bp = clf.predict(vec.transform([full(b) for b in bank["prompts"]])); by = {}
        for b, p in zip(bank["prompts"], bp):
            by.setdefault(b["class"], []).append(p == b["class"])
        bank_acc = {k: round(float(np.mean(v)), 3) for k, v in by.items()}
        terms = vec.get_feature_names_out(); idf = vec.idf_; coef = clf.coef_
        cj = {"type": "tfidf_lr", "tag": a.tag, "created_at": created, "classes": [str(c) for c in clf.classes_],
              "intercept": [round(float(x), 5) for x in clf.intercept_],
              "terms": {str(t): [round(float(idf[i]), 4)] + [round(float(c), 4) for c in coef[:, i]] for i, t in enumerate(terms)},
              "n_train": len(texts), "train_counts": dict(Counter(labels)), "cv5_macro_f1": round(float(cv), 4),
              "bank_held_out": not a.include_bank, "bank_acc": bank_acc}
        json.dump(cj, open(out / "content_model.json", "w"))
        say(f"content: cv macro-F1 {cv:.3f} | accuracy on the prompt bank ({'held out' if not a.include_bank else 'included in training'}) {bank_acc}")

    # ---------------- actor ----------------
    import xgboost as xgb
    fr = []
    for p in list(a.actor_csv) + list(a.extra_actor):
        if not Path(p).exists():
            continue
        d = pd.read_csv(p); lab = d["label"] if "label" in d else d["true_actor"]
        x = d[HARD].copy(); x["y"] = (lab == "agent").astype(int).values; fr.append(x)
    if not fr:
        sys.exit("no behavior feature files found for the actor model")
    D = pd.concat(fr, ignore_index=True); Xa = D[HARD].astype(float).replace([np.inf, -np.inf], np.nan); ya = D["y"].values
    m = xgb.XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.1, subsample=0.9, colsample_bytree=0.9,
                          eval_metric="logloss", random_state=20261107, base_score=0.5)
    acv = cross_val_score(m, Xa, ya, cv=StratifiedKFold(5, shuffle=True, random_state=7)).mean(); m.fit(Xa, ya)
    trees = [json.loads(t) for t in m.get_booster().get_dump(dump_format="json")]
    aj = {"type": "xgb_trees", "tag": a.tag, "created_at": created, "features": HARD, "base_margin": 0.0, "trees": trees,
          "n_train": int(len(D)), "n_agent": int(ya.sum()), "cv5_acc": round(float(acv), 4)}
    json.dump(aj, open(out / "actor_model.json", "w"))
    say(f"actor: trained on {len(D)} sessions ({int(ya.sum())} agent, {int(len(D) - ya.sum())} human), cv accuracy {acv:.3f}")
    say(f"wrote {out}/content_model.json and {out}/actor_model.json (tag {a.tag})")


if __name__ == "__main__":
    main()
