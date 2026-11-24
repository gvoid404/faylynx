#!/usr/bin/env python3
"""Retrain and rescore the gateway content model with and without secret masking.

Question: with real human-confirmed Shadow AI prompts added to training, how much real
Shadow AI does the content model catch, and does masking secrets (mask_secrets.py, applied
the same way in training and scoring) change that?

Data
  base     deploy/base_corpus.jsonl.gz: the clean training corpus (sealed audit holdout,
           its near-duplicates and the sealed shadow_test already left out when it was
           built). Rows that duplicate or near-duplicate a verified prompt are dropped here.
  verified data/gold/shadow_verified_v1.jsonl, rows with verify_split == "train" ONLY.
           Rows with verify_split == "shadow_test" are skipped at load time and never read.
           Data handling = Shadow rows with no evasion pre-filter reason; evasion = the rest.

Evaluation
  Repeated stratified group 5-fold CV on the verified train rows. Groups are near-duplicate
  clusters (MinHash, word 3-grams, Jaccard >= 0.85) so a prompt and its near-copies are
  always in the same fold. In each fold the model trains on base + the other four folds and
  scores the held-out fold. Same folds for both conditions, so they are compared pair by pair.

  condition unmasked: raw text everywhere
  condition masked:   mask_text() on every training and scored prompt (train/serve consistent)
  plus "base only" (no verified prompts in training), scored on all verified train rows.

Model: the deployed content model's recipe (deploy/train_and_export.py): TF-IDF word
1-2 grams, min_df 2, 30,000 terms, sublinear tf; logistic regression, balanced classes, C=4.

Outputs (--out): metrics.json, report.md, cv_predictions.jsonl (ids, labels, predictions;
no prompt text).

Run:  python code/paper2_retrain_masked.py --p2 . --out results/retrain_masked
"""
import argparse, gzip, json, math, os, re, sys, time
from collections import Counter, defaultdict
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from scipy.stats import binomtest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mask_secrets import mask, mask_text, MASK_VERSION

ap = argparse.ArgumentParser()
ap.add_argument("--p2", default=".", help="paper2-three-class folder")
ap.add_argument("--base", default="deploy/base_corpus.jsonl.gz")
ap.add_argument("--verified", default="data/gold/shadow_verified_v1.jsonl")
ap.add_argument("--out", default="results/retrain_masked")
ap.add_argument("--seeds", default="20261120,1,2,3,4", help="one CV repeat per seed; the first is the primary run")
ap.add_argument("--folds", type=int, default=5)
a = ap.parse_args()
P = lambda rel: os.path.join(a.p2, rel)
os.makedirs(P(a.out), exist_ok=True)
SEEDS = [int(s) for s in a.seeds.split(",")]
CLASSES = ["Allow", "Shadow AI", "Automated AI Pipelines"]
EVASION = {"persona_override", "detector_evasion", "license_cheat"}
norm = lambda t: re.sub(r"\s+", " ", (t or "").strip().lower())


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 4), round(c + h, 4))


# ---------- load ----------
verified = []
with open(P(a.verified), encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("verify_split") != "train":
            continue                      # sealed shadow_test: skipped, never read further
        verified.append(r)
for r in verified:
    r["kind"] = ("evasion" if set(r.get("prefilter") or []) & EVASION else "data_handling") if r["label"] == "Shadow AI" else "-"
print(f"verified train rows: {len(verified)} | {dict(Counter((r['label'], r['kind']) for r in verified))}")

base = []
with gzip.open(P(a.base), "rt", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            r = json.loads(line)
            if r.get("label") in CLASSES and (r.get("prompt") or "").strip():
                base.append(r)
print(f"base corpus rows: {len(base)} | {dict(Counter(r['label'] for r in base))}")

# ---------- near-duplicate clusters (on raw text, so groups are identical in both conditions) ----------
from datasketch import MinHash, MinHashLSH
def shingles(t, k=3):
    w = norm(t).split()
    return {" ".join(w[i:i + k]) for i in range(max(1, len(w) - k + 1))} or {norm(t)[:32]}
def minhash(t):
    m = MinHash(num_perm=128, seed=7); m.update_batch([s.encode() for s in shingles(t)]); return m

vm = [minhash(r["prompt"]) for r in verified]
lsh = MinHashLSH(threshold=0.85, num_perm=128)
for i, m in enumerate(vm):
    lsh.insert(str(i), m)
parent = list(range(len(verified)))
def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
for i, m in enumerate(vm):
    for j in lsh.query(m):
        a_, b_ = find(i), find(int(j))
        if a_ != b_:
            parent[a_] = b_
groups = np.array([find(i) for i in range(len(verified))])
gsize = Counter(groups)
print(f"near-duplicate groups: {len(gsize)} for {len(verified)} rows | largest {max(gsize.values())} | rows in multi-row groups {sum(v for v in gsize.values() if v > 1)}")

# drop base rows that duplicate or near-duplicate a verified train prompt
vt = {norm(r["prompt"]) for r in verified}
dropped_base = 0; kept = []
for r in base:
    if norm(r["prompt"]) in vt or lsh.query(minhash(r["prompt"])):
        dropped_base += 1; continue
    kept.append(r)
base = kept
print(f"base rows dropped as (near-)duplicates of verified prompts: {dropped_base} -> base {len(base)}")

# ---------- masking coverage (counts only) ----------
cover = {"verified_rows_with_placeholder": Counter(), "verified_placeholders": Counter(), "base_rows_with_placeholder": Counter(), "base_placeholders": Counter()}
v_masked, b_masked = [], []
for r in verified:
    t, c = mask(r["prompt"]); v_masked.append(t); cover["verified_placeholders"].update(c)
    if c: cover["verified_rows_with_placeholder"][f"{r['label']}|{r['kind']}"] += 1
for r in base:
    t, c = mask(r["prompt"]); b_masked.append(t); cover["base_placeholders"].update(c)
    if c: cover["base_rows_with_placeholder"][r["label"]] += 1
cover = {k: dict(v) for k, v in cover.items()}
print("masking coverage:", json.dumps(cover))

texts = {"unmasked": ([r["prompt"] for r in verified], [r["prompt"] for r in base]), "masked": (v_masked, b_masked)}
y_v = np.array([r["label"] for r in verified]); y_b = [r["label"] for r in base]
strata = np.array([f"{r['label']}|{r['kind']}" for r in verified])


def fit_predict(train_texts, train_labels, test_texts):
    vec = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=2, max_features=30000)
    X = vec.fit_transform([t[:4000] for t in train_texts])
    clf = LogisticRegression(max_iter=3000, class_weight="balanced", C=4.0)
    clf.fit(X, train_labels)
    return clf.predict(vec.transform([t[:4000] for t in test_texts]))


def score(pred):
    out = {}
    for name, mask_ in (("shadow_all", y_v == "Shadow AI"),
                        ("shadow_data_handling", strata == "Shadow AI|data_handling"),
                        ("shadow_evasion", strata == "Shadow AI|evasion")):
        n = int(mask_.sum()); k = int((pred[mask_] == "Shadow AI").sum())
        out[name] = {"caught": k, "n": n, "recall": round(k / n, 4), "ci95": wilson(k, n)}
    al = y_v == "Allow"; n = int(al.sum()); k = int((pred[al] == "Shadow AI").sum())
    out["allow_false_alarm"] = {"flagged_shadow": k, "n": n, "rate": round(k / n, 4), "ci95": wilson(k, n)}
    return out


results = {"base_only": {}, "cv": {c: {} for c in texts}}
t0 = time.time()
# base only (no verified prompts in training)
for cond, (vt_, bt_) in texts.items():
    results["base_only"][cond] = score(fit_predict(bt_, y_b, vt_))
    print(f"base only, {cond}: {json.dumps(results['base_only'][cond])}")

# repeated stratified group k-fold, same folds for both conditions
preds = {c: {} for c in texts}
for seed in SEEDS:
    sgkf = StratifiedGroupKFold(n_splits=a.folds, shuffle=True, random_state=seed)
    folds = list(sgkf.split(np.zeros(len(verified)), strata, groups))
    for cond, (vt_, bt_) in texts.items():
        pred = np.empty(len(verified), dtype=object)
        for tr_i, te_i in folds:
            pred[te_i] = fit_predict(bt_ + [vt_[i] for i in tr_i], y_b + [y_v[i] for i in tr_i], [vt_[i] for i in te_i])
        preds[cond][seed] = pred
        results["cv"][cond][str(seed)] = score(pred)
        s = results["cv"][cond][str(seed)]
        print(f"seed {seed} {cond:<8s} Shadow {s['shadow_all']['caught']}/{s['shadow_all']['n']} | data {s['shadow_data_handling']['caught']}/{s['shadow_data_handling']['n']} "
              f"| evasion {s['shadow_evasion']['caught']}/{s['shadow_evasion']['n']} | Allow false alarm {s['allow_false_alarm']['flagged_shadow']}/{s['allow_false_alarm']['n']} | {time.time()-t0:.0f}s", flush=True)

# summaries across seeds and paired masked-vs-unmasked tests
summary = {}
for cond in texts:
    summary[cond] = {}
    for m in ("shadow_all", "shadow_data_handling", "shadow_evasion", "allow_false_alarm"):
        vals = [results["cv"][cond][str(s)][m]["recall" if m != "allow_false_alarm" else "rate"] for s in SEEDS]
        summary[cond][m] = {"mean": round(float(np.mean(vals)), 4), "min": round(float(min(vals)), 4), "max": round(float(max(vals)), 4)}
paired = {}
for seed in SEEDS:
    pu, pm = preds["unmasked"][seed], preds["masked"][seed]
    paired[str(seed)] = {}
    for name, sel, good in (("shadow_data_handling", strata == "Shadow AI|data_handling", "Shadow AI"),
                            ("shadow_all", y_v == "Shadow AI", "Shadow AI")):
        hu = pu[sel] == good; hm = pm[sel] == good
        only_m = int((hm & ~hu).sum()); only_u = int((hu & ~hm).sum())
        p = binomtest(only_m, only_m + only_u, 0.5).pvalue if only_m + only_u else 1.0
        paired[str(seed)][name] = {"caught_only_masked": only_m, "caught_only_unmasked": only_u, "mcnemar_exact_p": round(float(p), 4)}

primary = str(SEEDS[0])
meta = {"mask_version": MASK_VERSION, "seeds": SEEDS, "primary_seed": SEEDS[0], "folds": a.folds,
        "n_verified_train": len(verified), "n_base": len(base), "base_dropped_as_dups": dropped_base,
        "n_groups": len(gsize), "model": "tfidf word1-2 min_df2 30k sublinear + LR balanced C=4 (deploy recipe)",
        "sealed_shadow_test_read": False, "sealed_audit_holdout_in_training": False}
out = {"meta": meta, "masking_coverage": cover, "base_only": results["base_only"], "cv_by_seed": results["cv"],
       "cv_summary_across_seeds": summary, "paired_masked_vs_unmasked": paired}
json.dump(out, open(P(f"{a.out}/metrics.json"), "w"), indent=2)
with open(P(f"{a.out}/cv_predictions.jsonl"), "w", encoding="utf-8") as f:
    for i, r in enumerate(verified):
        f.write(json.dumps({"prompt_id": r["prompt_id"], "label": r["label"], "kind": r["kind"], "group": int(groups[i]),
                            "pred_unmasked": preds["unmasked"][SEEDS[0]][i], "pred_masked": preds["masked"][SEEDS[0]][i]}) + "\n")


# ---------- report ----------
def line(s, m):
    d = s[m]
    if m == "allow_false_alarm":
        return f"{d['flagged_shadow']} / {d['n']} = {100*d['rate']:.1f}% (95% CI {100*d['ci95'][0]:.1f}–{100*d['ci95'][1]:.1f})"
    return f"{d['caught']} / {d['n']} = {100*d['recall']:.1f}% (95% CI {100*d['ci95'][0]:.1f}–{100*d['ci95'][1]:.1f})"
names = {"shadow_all": "Shadow AI, all", "shadow_data_handling": "Data handling", "shadow_evasion": "Evasion", "allow_false_alarm": "False alarm on look-alike Allow"}
R = ["# Retrain and rescore with secret masking", "",
     f"Mask version `{MASK_VERSION}`. Verified train split only ({len(verified)} rows; sealed `shadow_test` not read). "
     f"Base corpus {len(base):,} rows (sealed audit holdout excluded; {dropped_base} rows dropped as near-duplicates of verified prompts). "
     f"{a.folds}-fold stratified group CV, {len(gsize)} near-duplicate groups, {len(SEEDS)} repeats; primary seed {SEEDS[0]}.", "",
     f"## Primary run (seed {primary})", "", "| | Base only, unmasked | Base only, masked | + real prompts, unmasked | + real prompts, masked |", "|---|---|---|---|---|"]
for m in names:
    R.append(f"| {names[m]} | {line(results['base_only']['unmasked'], m)} | {line(results['base_only']['masked'], m)} | {line(results['cv']['unmasked'][primary], m)} | {line(results['cv']['masked'][primary], m)} |")
R += ["", f"## Across {len(SEEDS)} CV repeats (mean, min–max)", "", "| | Unmasked | Masked |", "|---|---|---|"]
for m in names:
    u, k = summary["unmasked"][m], summary["masked"][m]
    R.append(f"| {names[m]} | {100*u['mean']:.1f}% ({100*u['min']:.1f}–{100*u['max']:.1f}) | {100*k['mean']:.1f}% ({100*k['min']:.1f}–{100*k['max']:.1f}) |")
R += ["", "## Masked vs unmasked, paired on the same folds (exact McNemar)", "", "| Seed | Data handling: only masked / only unmasked (p) | All Shadow: only masked / only unmasked (p) |", "|---|---|---|"]
for s in SEEDS:
    d, al = paired[str(s)]["shadow_data_handling"], paired[str(s)]["shadow_all"]
    R.append(f"| {s} | {d['caught_only_masked']} / {d['caught_only_unmasked']} (p={d['mcnemar_exact_p']}) | {al['caught_only_masked']} / {al['caught_only_unmasked']} (p={al['mcnemar_exact_p']}) |")
R += ["", "## Masking coverage", "", f"Verified rows with at least one placeholder: {cover['verified_rows_with_placeholder']}", "",
      f"Placeholders in verified rows: {cover['verified_placeholders']}", "", f"Base rows with at least one placeholder: {cover['base_rows_with_placeholder']}", ""]
open(P(f"{a.out}/report.md"), "w").write("\n".join(R) + "\n")
print("\n".join(R))
