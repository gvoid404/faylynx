#!/usr/bin/env python3
"""Pack the labeled Paper 2 training prompts into one compact file for model training.

  python build_base_corpus.py --p2 <paper2-three-class folder> --out base_corpus.jsonl.gz

One line per unique prompt: {"id", "prompt", "label", "src"}; the first line is a short note on how
the file was built. Later sources win when the same text appears twice (same order the models were
first trained with).

Left out, so the Paper 2 test sets stay untouched by every model trained from this file:
  * the sealed Shadow test rows of the gold set (gold_split = shadow_test)
  * the sealed holdout of the human audit (data/gold/sealed/human_labeling_1k_key.json, split =
    holdout), every prompt that is a near-duplicate of a holdout prompt (same rule as
    code/refine_classifier.py: MinHash, 3-word shingles, similarity 0.85), and the synthetic Shadow
    rows that were built on one of those prompts
Only prompt ids and the split are read from the sealed key, never the labels in it. Near-duplicate
matching needs the datasketch package (pip install datasketch); without it only exact matches are
dropped and a warning is printed.

The file holds third-party dataset text (WildChat, LMSYS-Chat-1M): keep it private. Copy it to the
server's runtime/ folder; do not commit it.
"""
import argparse, gzip, json, re, sys, time
from collections import Counter
from pathlib import Path

KEEP = {"Allow", "Shadow AI", "Automated AI Pipelines"}
SOURCES = [("judge_v3_10k", "data/labeled/wildchat48m_full_10k_fable_v3_judged.jsonl"),
           ("synthetic_shadow_v1", "data/labeled/synthetic_shadow_v1.jsonl"),
           ("human_gold_v1", "data/gold/gold_consolidated_v1_text.jsonl"),
           ("train_refined", "results/refine/train_refined.jsonl")]
HOLDOUT_KEY = "data/gold/sealed/human_labeling_1k_key.json"


def _norm(t):
    return re.sub(r"\s+", " ", (t or "").strip().lower())


def _read(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def near_duplicate_ids(rows, texts, log=print):
    """ids of rows whose prompt is an exact or MinHash near-duplicate (0.85) of any of `texts`."""
    exact = {_norm(t) for t in texts}
    out = {r.get("id") for r in rows if _norm(r.get("prompt")) in exact}
    try:
        from datasketch import MinHash, MinHashLSH
    except ImportError:
        log("WARNING: datasketch is not installed, so only exact copies of holdout prompts are dropped, "
            "not near-duplicates. Run: pip install datasketch")
        return out

    def shingles(t, k=3):
        w = (t or "").lower().split()
        return {" ".join(w[i:i + k]) for i in range(max(1, len(w) - k + 1))} or {(t or "").lower()[:32]}

    def sketch(t):
        m = MinHash(num_perm=64); m.update_batch([s.encode() for s in shingles(t)]); return m

    lsh = MinHashLSH(threshold=0.85, num_perm=64)
    for i, t in enumerate(texts):
        lsh.insert(f"x{i}", sketch(t))
    for r in rows:
        if lsh.query(sketch(r.get("prompt"))):
            out.add(r.get("id"))
    return out


def corpus_from_p2(p2, holdout_key=None, allow_missing_key=False, log=print):
    """Returns (rows, note). rows: list of {"id", "prompt", "label", "src"}, one per unique prompt."""
    P2 = Path(p2)
    data = {}
    for name, rel in SOURCES:
        path = P2 / rel
        if path.exists():
            data[name] = _read(path)
        else:
            log("missing, skipped:", path)
    key_path = Path(holdout_key) if holdout_key else P2 / HOLDOUT_KEY
    holdout, dropped = set(), set()
    if key_path.exists():
        holdout = {str(k["prompt_id"]) for k in json.load(open(key_path, encoding="utf-8"))["key"] if k.get("split") == "holdout"}
        judged = data.get("judge_v3_10k", [])
        hold_texts = [r.get("prompt") or "" for r in judged if str(r.get("id")) in holdout]
        dropped = holdout | {str(i) for i in near_duplicate_ids(judged, hold_texts, log)}
    elif not allow_missing_key:
        sys.exit(f"The sealed holdout key was not found ({key_path}). Without it the audit holdout cannot be kept out of "
                 "training. Point --holdout-key at it, or pass --allow-missing-holdout-key if this data has no holdout.")
    else:
        log("WARNING: no holdout key; nothing was left out for the audit holdout")
    rows, n_syn = {}, 0
    for name, _ in SOURCES:
        for d in data.get(name, []):
            lab = d.get("label"); t = (d.get("prompt") or "").strip()
            if lab not in KEEP or len(t) < 15 or d.get("gold_split") == "shadow_test":
                continue
            if str(d.get("id")) in dropped:
                continue
            if d.get("base_prompt_id") is not None and str(d["base_prompt_id"]) in dropped:
                n_syn += 1; continue                       # synthetic Shadow row built on a holdout prompt
            rows[t[:4000]] = {"id": d.get("id"), "label": lab, "src": name}
    out = [{"id": r["id"], "prompt": t, "label": r["label"], "src": r["src"]} for t, r in rows.items()]
    note = {"built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "prompts": len(out),
            "by_label": dict(Counter(r["label"] for r in out)), "by_source": dict(Counter(r["src"] for r in out)),
            "audit_holdout_prompts_left_out": len(holdout),
            "near_duplicates_of_holdout_left_out": len(dropped) - len(holdout),
            "synthetic_rows_on_holdout_left_out": n_syn, "sealed_shadow_test_left_out": True}
    return out, note


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--p2", required=True, help="the paper2-three-class folder")
    ap.add_argument("--out", default="base_corpus.jsonl.gz")
    ap.add_argument("--holdout-key", help="sealed audit key (default: <p2>/" + HOLDOUT_KEY + ")")
    ap.add_argument("--allow-missing-holdout-key", action="store_true")
    a = ap.parse_args()
    rows, note = corpus_from_p2(a.p2, a.holdout_key, a.allow_missing_holdout_key)
    with gzip.open(a.out, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"_note": note}) + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {a.out}: {note['prompts']} prompts", note["by_label"], note["by_source"])
    print(f"left out: {note['audit_holdout_prompts_left_out']} audit-holdout prompts, "
          f"{note['near_duplicates_of_holdout_left_out']} near-duplicates of them, "
          f"{note['synthetic_rows_on_holdout_left_out']} synthetic rows built on them, and the sealed Shadow test rows")


if __name__ == "__main__":
    main()
