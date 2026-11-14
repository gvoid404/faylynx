#!/usr/bin/env python3
"""Build the study's fixed prompt bank from the Paper 2 labeled data, and record how big each
source pool was at every screening step (prompt_pool.json, shown on the Admin page).

  python build_prompt_bank.py --p2 <paper2-three-class folder>

Sources
  Allow      human gold set (human_gold_v1): real user prompts hand-labeled Allow
  Shadow AI  synthetic_shadow_v1: fictional payloads (records, credentials, financials, contracts,
             code, control-bypass requests). Human-verified Shadow prompts are NOT used because
             they contain jailbreak text that should not be handed to volunteers.
  Automated  human gold set first, then the judge-labeled 10k WildChat-4.8M sample (confidence
             >= 0.9, not flagged toxic); at most 3 fills of any one template.
Screening is deliberately conservative: short, single-line, ASCII, and a keyword screen for
sexual, violent, drug-related and similar content; Allow prompts were then picked by hand.
"""
import argparse, json, random, re
from collections import Counter
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--p2", required=True)
ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "prompt_bank.json"))
ap.add_argument("--pool-out", default=str(Path(__file__).resolve().parent.parent / "honeypot" / "prompt_pool.json"))
a = ap.parse_args()
P2 = Path(a.p2); rng = random.Random(20261109)
norm = lambda t: re.sub(r"\s+", " ", t.strip())

BLOCK = re.compile(r"toxic|sex|nsfw|nude|naked|kill|murder|suicid|rape|porn|fetish|erotic|racis|nazi|slur|drug|weapon|bomb|gore|blood|kink|breast|diaper|messy|fart|feet|tickl|bdsm|lewd|horny|seduc|black person|white person|jew|muslim|christian|gay|trans|[^\x00-\x7f]", re.I)
BLOCK2 = re.compile(BLOCK.pattern + r"|weed|chastity|slave|rich woman|hot comment|pee|satanic|yelps|obedient|SmartGPT|sentient|NAME_|https?://|chemical industry|chemical company|dark rap|cena|cage|fuck|shit|damn|hell\b|die\b|dead|death|war\b|gun|alcohol|beer|wine|bet\b|gambl|casino|crypto|hack|password|exploit", re.I)
AUTO_BLOCK = re.compile(r"toxic|sex|nsfw|nude|naked|kill|murder|suicid|rape|porn|fetish|erotic|racis|nazi|slur|drug|weapon|bomb|gore|kink|lewd|seduc|obedient|SmartGPT|sentient|jailbreak|DAN\b|no special filtering|unfiltered|uncensored|girlfriend|waifu|roleplay|black person|1girl|superheroine|safety problems|[^\x00-\x7f]", re.I)
AUTO_SKIP = ("what is the latest data", "does the common stock", "october 3,", "<#if spacing")
# positions (in the screened Allow pool, file order) of the prompts picked by hand
ALLOW_PICKS = [2,3,5,8,9,12,13,19,24,26,28,31,32,33,35,38,41,43,45,46,47,48,50,51,53,55,56,60,61,62,63,65,69,71,74,77,79,81,83,85,86,89,90,91,92,94,95,96,97,98,99,101,102,104,108,110,113,114,115,117,118,119,121,124,125,126,127,129,130,134]
TASKS = ["summarize this", "find the main risks in this", "clean this up and put it in a table", "draft an email to the team about this", "what stands out here", "turn this into bullet points for a slide", "check this for mistakes", "translate this to Spanish", "write a short memo based on this", "explain what this means"]

gold_all = [json.loads(l) for l in open(P2 / "data/gold/gold_consolidated_v1_text.jsonl", encoding="utf-8")]
gold = [r for r in gold_all if r.get("gold_split") != "shadow_test"]
judged = [json.loads(l) for l in open(P2 / "data/labeled/wildchat48m_full_10k_fable_v3_judged.jsonl", encoding="utf-8")]
syn = [json.loads(l) for l in open(P2 / "data/labeled/synthetic_shadow_v1.jsonl", encoding="utf-8")]

# ---------------- Allow ----------------
allow_src = [r for r in gold if r["label"] == "Allow"]
allow_pool = [r for r in allow_src if 40 <= len(norm(r["prompt"])) <= 130 and "\n" not in r["prompt"].strip() and not BLOCK2.search(r["prompt"])]
allow = [allow_pool[i] for i in ALLOW_PICKS][:60]

# ---------------- Automated ----------------
auto_gold_src = [r for r in gold if r["label"] == "Automated AI Pipelines"]
auto_judged_src = [r for r in judged if r["label"] == "Automated AI Pipelines"]
cands = [("human_gold_v1", r) for r in auto_gold_src if 40 <= len(r["prompt"]) <= 1200 and not AUTO_BLOCK.search(r["prompt"])]
n_gold_elig = len(cands)
cands += [("judge_v3", r) for r in auto_judged_src if (r.get("confidence") or 0) >= 0.9 and not r.get("toxic") and 60 <= len(r["prompt"]) <= 1200 and not AUTO_BLOCK.search(r["prompt"])]
n_judged_elig = len(cands) - n_gold_elig
groups, full = {}, set()
for s, r in cands:
    t = norm(r["prompt"]); k = t[:40].lower()
    if any(k.startswith(x) for x in AUTO_SKIP) or t in full:
        continue
    full.add(t); groups.setdefault(k, []).append((s, r))
auto = []
for rnd in range(3):
    for k, v in groups.items():
        if len(v) > rnd and len(auto) < 60:
            auto.append(v[rnd])

# ---------------- Shadow AI ----------------
bykind = {}
for r in syn:
    t = r["prompt"]
    if r["synthetic_kind"] == "control_bypass":
        if "\n" not in t.strip() and len(t) <= 190:
            bykind.setdefault("control_bypass", {}).setdefault(t.strip(), (r, t.strip(), ""))
    else:
        head, _, rest = t.partition(":\n\n")
        if head in TASKS and rest and len(rest) <= 900:
            bykind.setdefault(r["synthetic_kind"], {})[r["id"]] = (r, head + ":", rest)
bykind = {k: list(v.values()) for k, v in bykind.items()}
shadow_elig = {k: len(v) for k, v in bykind.items()}
for v in bykind.values():
    rng.shuffle(v)
pick, kinds, i = [], sorted(bykind), 0
while len(pick) < 60 and i < 5000:
    k = kinds[i % len(kinds)]; i += 1
    if bykind[k]:
        pick.append(bykind[k].pop())

# ---------------- bank + participant sets ----------------
bank = []
def add(cls, pid, ty, pa, src, sid, kind=""):
    bank.append({"id": pid, "class": cls, "type_text": ty, "paste_text": pa, "source": src, "source_id": sid, "kind": kind})
for n, r in enumerate(allow, 1): add("Allow", f"A{n:02d}", norm(r["prompt"]), "", "human_gold_v1", r["id"])
for n, (r, ty, pa) in enumerate(pick, 1): add("Shadow AI", f"S{n:02d}", ty, pa, "synthetic_shadow_v1", r["id"], r["synthetic_kind"])
for n, (s, r) in enumerate(auto, 1): add("Automated AI Pipelines", f"M{n:02d}", r["prompt"].strip(), "", s, r["id"])
A = [b["id"] for b in bank if b["class"] == "Allow"]; S = [b["id"] for b in bank if b["class"] == "Shadow AI"]
sets = {}
for p in range(20):
    x = [A[(p * 6 + q) % 60] for q in range(3)] + [A[(p * 6 + 33 + q) % 60] for q in range(3)]
    y = [S[(p * 6 + q) % 60] for q in range(3)] + [S[(p * 6 + 33 + q) % 60] for q in range(3)]
    sets[f"P{p + 1:02d}"] = [z for pr in zip(x, y) for z in pr]
json.dump({"version": "bank_v1", "n_per_participant": 12, "prompts": bank, "sets": sets}, open(a.out, "w"), indent=1)

# ---------------- pool report ----------------
gid = {r["id"]: r for r in gold_all}
def corpus_of(b):
    if b["source"] == "human_gold_v1": return gid[b["source_id"]].get("corpus", "?")
    if b["source"] == "judge_v3": return "WildChat-4.8M"
    return "synthetic"
pool = {
  "bank_version": "bank_v1",
  "classes": [
    {"class": "Allow", "in_bank": len(allow),
     "source": "Paper 2 human gold set (human_gold_v1): real user prompts hand-labeled by a human rater",
     "source_size": len(allow_src), "source_breakdown": dict(Counter(r.get("corpus", "?") for r in allow_src)),
     "screened_pool": len(allow_pool), "screening": "40-130 characters, single line, ASCII, keyword content screen",
     "selection": f"{len(ALLOW_PICKS)} picked by hand from the screened pool; the first 60 are in the bank",
     "bank_by_corpus": dict(Counter(corpus_of(b) for b in bank if b["class"] == "Allow"))},
    {"class": "Shadow AI", "in_bank": len(pick),
     "source": "Synthetic Shadow set (synthetic_shadow_v1): Allow prompts with a fictional sensitive payload injected; no real data",
     "source_size": len(syn), "source_breakdown": dict(Counter(r["synthetic_kind"] for r in syn)),
     "screened_pool": sum(shadow_elig.values()), "screened_by_kind": shadow_elig,
     "screening": "short instruction + payload of at most 900 characters; the 5 distinct control-bypass requests",
     "selection": "round-robin across the 6 payload kinds",
     "bank_by_corpus": {"synthetic": len(pick)}, "bank_by_kind": dict(Counter(b["kind"] for b in bank if b["class"] == "Shadow AI"))},
    {"class": "Automated AI Pipelines", "in_bank": len(auto),
     "source": "Paper 2 human gold set first, then the judge-labeled 10k WildChat-4.8M sample (confidence >= 0.9, not flagged toxic)",
     "source_size": len(auto_gold_src) + len(auto_judged_src),
     "source_breakdown": {"human gold set": len(auto_gold_src), "judge-labeled 10k sample": len(auto_judged_src)},
     "screened_pool": n_gold_elig + n_judged_elig, "screened_breakdown": {"human gold set": n_gold_elig, "judge-labeled 10k sample": n_judged_elig},
     "distinct_templates": len(groups),
     "screening": "40-1200 characters, ASCII, keyword content screen; duplicates and 4 mislabeled-looking items removed",
     "selection": f"every distinct template once ({len(groups)} templates), then second and third fills of repeated templates",
     "bank_by_corpus": dict(Counter(corpus_of(b) for b in bank if b["class"] == "Automated AI Pipelines"))},
  ],
  "participant_sets": {"participants": len(sets), "prompts_each": 12, "each_prompt_assigned_to": 2},
  "licenses": {"WildChat": "ODC-BY 1.0, attribution required (WildChat-1M dataset card; confirm on the WildChat-4.8M card)",
               "LMSYS": "LMSYS-Chat-1M Dataset License Agreement: the data may not be redistributed or hosted",
               "synthetic": "generated for this project"},
}
json.dump(pool, open(a.pool_out, "w"), indent=1)
print("bank:", dict(Counter(b["class"] for b in bank)), "| allow pool", len(allow_pool), "of", len(allow_src),
      "| shadow pool", sum(shadow_elig.values()), "of", len(syn), "| auto pool", n_gold_elig + n_judged_elig, "templates", len(groups))
