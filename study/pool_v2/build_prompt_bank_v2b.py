#!/usr/bin/env python3
"""Assemble the v2 website prompt pool, deploy/prompt_bank_v2.json, after review.

Inputs
  deploy/prompt_bank_v2_shadow_part.json        700 invented Shadow AI prompts + 70 reserves (make_pool_v2_shadow.py)
  audit/pool_v2_review.xlsx (+ _key.json)       reviewed real prompts and the invented-Shadow check (paper2_pool_v2_real.ipynb cell 7)
  data/labeled/pool_v2_real_fable_v3_1.jsonl    judge labels and the exact text of the real prompts

Rules (v2b: quotas come from the review key written by notebook cell 7, and Allow is filled to its total from either group)
  * Real prompts: rows marked use = Y on "Real prompts". Text comes from the labeled file, not the
    workbook, so an accidental edit in Excel cannot change a prompt. Quotas: 150 work-style Allow,
    50 general Allow, 100 Automated. Each real prompt is re-checked with mask_secrets: nothing maskable.
  * Invented prompts: rows marked use = N on "Invented Shadow check" are dropped and replaced by a
    reserve of the same kind.
  * Sets: P01-P20 each get 40 different prompts (28 Shadow AI, 8 Allow, 4 Automated), ordered so
    every block of 10 is 7/2/1, so a participant who is given fewer than 40 still sees about 70/20/10.
    No prompt is in two participant sets. The other 200 are listed in agent_reserve.
  * The format follows deploy/prompt_bank.json; prompt_bank.json itself is never touched, and an
    existing prompt_bank_v2.json is not overwritten unless --force is given.

Run:  python code/build_prompt_bank_v2b.py --p2 .
"""
import argparse, json, os, random, re, sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mask_secrets import mask, MASK_VERSION

ap = argparse.ArgumentParser()
ap.add_argument("--p2", default=".")
ap.add_argument("--shadow", default="deploy/prompt_bank_v2_shadow_part.json")
ap.add_argument("--review", default="audit/pool_v2_review.xlsx")
ap.add_argument("--labels", default="data/labeled/pool_v2_real_fable_v3_1.jsonl")
ap.add_argument("--out", default="deploy/prompt_bank_v2.json")
ap.add_argument("--participants", type=int, default=20)
ap.add_argument("--per-participant", type=int, default=40)
ap.add_argument("--seed", type=int, default=20261120)
ap.add_argument("--force", action="store_true", help="overwrite an existing output file")
a = ap.parse_args()
P = lambda rel: rel if os.path.isabs(rel) else os.path.join(a.p2, rel)
R = random.Random(a.seed)
QUOTA = {"Allow_work": 150, "Allow_general": 50, "Automated AI Pipelines": 100}
N_SHADOW = 700
BLOCK = ["S", "S", "A", "S", "S", "S", "M", "S", "A", "S"]          # 7 Shadow, 2 Allow, 1 Automated per 10
assert a.per_participant % len(BLOCK) == 0
per = {c: BLOCK.count(c) * a.per_participant // len(BLOCK) for c in "SAM"}

out_path = P(a.out)
if os.path.exists(out_path) and not a.force:
    sys.exit(f"{a.out} already exists; rerun with --force to replace it (prompt_bank.json is never touched)")
if os.path.basename(out_path) == "prompt_bank.json":
    sys.exit("refusing to write over prompt_bank.json; choose another --out")

from openpyxl import load_workbook
wb = load_workbook(P(a.review), data_only=True)
_k = json.load(open(P(a.review).replace(".xlsx", "_key.json")))
key = {k["ref"]: k for k in _k["items"]}
QUOTA = _k.get("quota", QUOTA)            # quotas as cell 7 set them (a short group's places move to the other Allow group)
ALLOW_TOTAL = QUOTA["Allow_work"] + QUOTA["Allow_general"]
print("quotas:", QUOTA)


def sheet_rows(ws, id_col, use_col):
    for row in ws.iter_rows(min_row=4, values_only=True):
        if row and row[id_col]:
            yield str(row[id_col]).strip(), (str(row[use_col]).strip().upper() if row[use_col] is not None else "")


problems = []

# ---------------- invented Shadow AI
part = json.load(open(P(a.shadow), encoding="utf-8"))["prompts"]
drop = {i for i, u in sheet_rows(wb["Invented Shadow check"], 0, 6) if u == "N"}
pool = [p for p in part if p["role"] == "pool" and p["id"] not in drop]
reserve = defaultdict(list)
for p in part:
    if p["role"] == "reserve" and p["id"] not in drop:
        reserve[p["kind"]].append(p)
dropped_by_kind = Counter(p["kind"] for p in part if p["role"] == "pool" and p["id"] in drop)
filled = Counter()
for kind, n in dropped_by_kind.items():
    take = reserve[kind][:n]; pool += take; filled[kind] = len(take)
    if len(take) < n:
        problems.append(f"only {len(take)} reserves left for {n} dropped {kind} prompts")
shadow = pool
print(f"invented Shadow AI: {len(shadow)} (dropped in review {sum(dropped_by_kind.values())}, replaced from reserve {sum(filled.values())})")

# ---------------- real Allow / Automated
labels = {}
with open(P(a.labels), encoding="utf-8") as f:
    for l in f:
        if l.strip():
            r = json.loads(l); labels[r["prompt_id"]] = r
chosen = defaultdict(list)
for ref, use in sheet_rows(wb["Real prompts"], 0, 5):
    if use != "Y":
        continue
    k = key.get(ref)
    if k is None:
        problems.append(f"{ref} is marked Y but is not in the review key"); continue
    chosen[k["group"]].append(labels[k["prompt_id"]])
# Allow: take work-style rows up to its quota, then general rows up to the Allow total (so a dropped row in one group can be replaced from the other)
work = chosen["Allow_work"][:QUOTA["Allow_work"]]
gen = chosen["Allow_general"][:max(0, ALLOW_TOTAL - len(work))]
if len(chosen["Allow_work"]) > len(work): print(f"note: {len(chosen['Allow_work'])} work-style rows marked Y; using the first {len(work)} in sheet order")
if len(chosen["Allow_general"]) > len(gen): print(f"note: {len(chosen['Allow_general'])} general rows marked Y; using the first {len(gen)} in sheet order")
if len(work) + len(gen) < ALLOW_TOTAL: print(f"note: only {len(work) + len(gen)} Allow rows marked Y (target {ALLOW_TOTAL}); mark more reserves Y for a full pool")
q_auto = QUOTA["Automated AI Pipelines"]
if len(chosen["Automated AI Pipelines"]) > q_auto: print(f"note: {len(chosen['Automated AI Pipelines'])} Automated rows marked Y; using the first {q_auto} in sheet order")
elif len(chosen["Automated AI Pipelines"]) < q_auto: print(f"note: only {len(chosen['Automated AI Pipelines'])} Automated rows marked Y (quota {q_auto}); mark more reserves Y for a full pool")
chosen["Allow_work"] = work
allow = work + gen; auto = chosen["Automated AI Pipelines"][:q_auto]
for r in allow + auto:
    if mask(r["prompt"])[1]:
        problems.append(f"{r['prompt_id']} contains something mask_secrets would mask; drop it")
need = {"S": per["S"] * a.participants, "A": per["A"] * a.participants, "M": per["M"] * a.participants}
for c, lst in (("S", shadow), ("A", allow), ("M", auto)):
    if len(lst) < need[c]:
        problems.append(f"{len(lst)} {c} prompts is fewer than the {need[c]} the participant sets need")
if problems:
    sys.exit("cannot build the pool:\n  " + "\n  ".join(problems))


def real_item(r, cls, i, kind):
    return {"id": f"V2{'A' if cls == 'Allow' else 'M'}{i:04d}", "class": cls, "type_text": r["prompt"], "paste_text": "",
            "source": "wildchat48m_v2", "source_id": r["prompt_id"], "kind": kind, "license": "ODC-BY",
            "judge_label": r["label"], "judge_confidence": r.get("confidence")}


A = [real_item(r, "Allow", i, "work_style" if i <= len(chosen["Allow_work"]) else "general") for i, r in enumerate(allow, 1)]
M = [real_item(r, "Automated AI Pipelines", i, "") for i, r in enumerate(auto, 1)]
S = [{k_: p[k_] for k_ in ("id", "class", "type_text", "paste_text", "source", "source_id", "kind", "subkind")} for p in shadow]


# ---------------- participant sets
def interleave_by(items, field):
    groups = defaultdict(list)
    for it in items:
        groups[it[field]].append(it)
    for g in groups.values():
        R.shuffle(g)
    order = sorted(groups, key=lambda g: -len(groups[g])); outl = []
    while any(groups.values()):
        for g in order:
            if groups[g]:
                outl.append(groups[g].pop())
    return outl


queues = {"S": interleave_by(S, "kind"), "A": interleave_by(A, "kind"), "M": interleave_by(M, "kind")}
dealt = {c: [[] for _ in range(a.participants)] for c in "SAM"}
for c in "SAM":
    for j in range(per[c] * a.participants):
        dealt[c][j % a.participants].append(queues[c][j])
sets = {}
for p in range(a.participants):
    it = {c: iter(dealt[c][p]) for c in "SAM"}
    sets[f"P{p + 1:02d}"] = [next(it[c])["id"] for c in BLOCK * (a.per_participant // len(BLOCK))]
used = {i for v in sets.values() for i in v}
prompts = S + A + M
agent_reserve = [p["id"] for p in interleave_by([p for p in prompts if p["id"] not in used], "class")]

# ---------------- checks
ids = [p["id"] for p in prompts]
texts = [(p["type_text"].strip().lower(), p["paste_text"].strip().lower()) for p in prompts]
assert len(ids) == len(set(ids)), "duplicate ids"
assert len(texts) == len(set(texts)), "duplicate prompt texts"
assert len(used) == sum(len(v) for v in sets.values()), "a prompt is in two participant sets"
assert used.isdisjoint(agent_reserve) and used | set(agent_reserve) == set(ids), "sets + reserve must cover every prompt exactly once"
cls = {p["id"]: p["class"] for p in prompts}
for name, v in sets.items():
    c = Counter(cls[i] for i in v)
    assert c == Counter({"Shadow AI": per["S"], "Allow": per["A"], "Automated AI Pipelines": per["M"]}), (name, c)
    for b in range(0, len(v), len(BLOCK)):
        assert [{"Shadow AI": "S", "Allow": "A", "Automated AI Pipelines": "M"}[cls[i]] for i in v[b:b + len(BLOCK)]] == BLOCK

mix = Counter(p["class"] for p in prompts)
bank = {"version": "bank_v2", "n_per_participant": 12, "max_per_participant": a.per_participant,
        "prompts": prompts, "sets": sets, "agent_reserve": agent_reserve,
        "meta": {"n": len(prompts), "by_class": dict(mix), "shadow_by_kind": dict(Counter(p["kind"] for p in S)),
                 "allow_by_kind": dict(Counter(p["kind"] for p in A)), "mask_version": MASK_VERSION, "seed": a.seed,
                 "block_order": "".join(BLOCK), "invented_dropped_in_review": sum(dropped_by_kind.values()),
                 "note": "Shadow AI prompts are invented (all data fake). Allow and Automated are real WildChat-4.8M (non-toxic, ODC-BY) prompts, "
                         "randomly sampled, kept only when mask_secrets found nothing in them, judge-labeled under rubric v3.1, and hand-reviewed. "
                         "Every prompt here must stay out of content-model training and evaluation."}}
os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
json.dump(bank, open(out_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"wrote {a.out}: {len(prompts)} prompts {dict(mix)} | {len(sets)} participant sets x {a.per_participant} | agent reserve {len(agent_reserve)}")
print("checks passed: unique ids and texts, disjoint sets, 7/2/1 in every block of 10, sets + reserve cover every prompt once")
