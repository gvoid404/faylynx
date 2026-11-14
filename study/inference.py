#!/usr/bin/env python3
"""Stdlib-only inference for the live detector: content class from prompt text (TF-IDF + LR
exported to JSON), actor (human vs automated) from the typing/mouse events (XGBoost trees exported
to JSON), and the fused gateway category. No numpy/sklearn needed on the server."""
import json, math, os, re, struct, tempfile
from pathlib import Path
import behavioral_features as bf

HERE = Path(__file__).resolve().parent
MODELS = HERE / "models"
TOKEN_RE = re.compile(r"(?u)\b\w\w+\b")
_cache = {}


def _load(name):
    p = MODELS / name
    mt = p.stat().st_mtime
    if name not in _cache or _cache[name][0] != mt:      # hot-reload when the file is replaced
        _cache[name] = (mt, json.load(open(p, encoding="utf-8")))
    return _cache[name][1]


def classify_content(text):
    m = _load("content_model.json")
    toks = TOKEN_RE.findall(text.lower())
    grams = toks + [a + " " + b for a, b in zip(toks, toks[1:])]
    tf = {}
    for g in grams:
        if g in m["terms"]:
            tf[g] = tf.get(g, 0) + 1
    vals = {g: (1.0 + math.log(c)) * m["terms"][g][0] for g, c in tf.items()}
    nrm = math.sqrt(sum(v * v for v in vals.values())) or 1.0
    scores = list(m["intercept"])
    for g, v in vals.items():
        w = m["terms"][g]
        for k in range(len(scores)):
            scores[k] += (v / nrm) * w[1 + k]
    mx = max(scores); ex = [math.exp(s - mx) for s in scores]; z = sum(ex)
    probs = {c: e / z for c, e in zip(m["classes"], ex)}
    best = max(probs, key=probs.get)
    return best, probs


def _f32(v):
    return struct.unpack("f", struct.pack("f", v))[0]      # XGBoost compares in float32


def _tree(node, x):
    while "leaf" not in node:
        v = x.get(node["split"])
        if v is None or (isinstance(v, float) and math.isnan(v)):
            nxt = node["missing"]
        else:
            nxt = node["yes"] if _f32(v) < _f32(node["split_condition"]) else node["no"]
        node = next(ch for ch in node["children"] if ch["nodeid"] == nxt)
    return node["leaf"]


def behavior_features(events):
    """7 style-invariant features from tracker-format events (same code path as training)."""
    fd, tmp = tempfile.mkstemp(suffix="_mm.jsonl")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps({"body": json.dumps({"eventFrames": events}), "ua": ""}) + "\n")
        feats = bf.session_features(tmp)
    finally:
        try: os.unlink(tmp)
        except OSError: pass
    if feats is None:
        return None
    x = {}
    for k in ("inter_key_cv", "dwell_cv", "mouse_straightness", "prog_fill_ratio", "paste_to_type_ratio"):
        v = feats.get(k)
        x[k] = None if (v is None or (isinstance(v, float) and math.isinf(v))) else float(v)
    x["has_mouse"] = 1.0 if (feats.get("n_mousemove") or 0) > 0 else 0.0
    x["has_typing"] = 1.0 if (feats.get("n_keydown") or 0) > 0 else 0.0
    x["_n_events"] = feats.get("n_events", 0); x["_n_keydown"] = feats.get("n_keydown", 0)
    x["_n_paste"] = feats.get("n_paste", 0)
    return x


def actor_prob(x):
    m = _load("actor_model.json")
    margin = m.get("base_margin", 0.0) + sum(_tree(t, x) for t in m["trees"])
    return 1.0 / (1.0 + math.exp(-margin))


def analyze(prompt, events):
    content, probs = classify_content(prompt or "")
    x = behavior_features(events or [])
    p_agent = actor_prob(x) if x else None
    actor = None if p_agent is None else ("automated" if p_agent > 0.5 else "human")
    # rubric precedence: Shadow AI outranks Automated; automated behavior alone => Automated
    if content == "Shadow AI":
        category = "Shadow AI"
    elif content == "Automated AI Pipelines" or actor == "automated":
        category = "Automated AI Pipelines"
    else:
        category = "Allow"
    return {"category": category, "content_class": content,
            "content_probs": {k: round(v, 3) for k, v in probs.items()},
            "actor": actor, "p_automated": None if p_agent is None else round(p_agent, 3),
            "behavior": None if not x else {k: (None if v is None else round(v, 3)) for k, v in x.items()},
            "models": {"content": _load("content_model.json").get("tag"), "actor": _load("actor_model.json").get("tag")}}
