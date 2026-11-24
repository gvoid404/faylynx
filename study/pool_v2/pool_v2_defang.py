#!/usr/bin/env python3
"""Make the invented credentials in the v2 prompt pool read as examples to secret scanners.

The invented Shadow AI prompts (make_pool_v2_shadow.py) carry random keys in real provider formats,
which GitHub push protection blocks as leaked secrets. This rewrites only those strings, the way
providers' own documentation does, and leaves every other character of every prompt unchanged:

  AWS access key id   AKIA + 16           -> AKIA + first 9 + EXAMPLE       (still 20 characters)
  40-character secret (AWS secret, token)  -> first 30 + EXAMPLEKEY          (still 40 characters)
  Stripe-style key    sk_live_ + 24        -> sk_live_ + first 16            (below real Stripe length)

mask_secrets.py still masks every rewritten value with the same placeholder as before, so training
and the live gateway see the same text after masking.

  python code/pool_v2_defang.py IN.json OUT.json      (a prompt bank or the Shadow part)
"""
import json, re, sys

_AWS_ID = re.compile(r"\bAKIA([0-9A-Z]{16})\b")
_SECRET40 = re.compile(r"(?<![A-Za-z0-9/+])([A-Za-z0-9/+]{40})(?![A-Za-z0-9/+])")
_STRIPE = re.compile(r"\b((?:sk|rk|pk)_(?:live|test)_)([A-Za-z0-9]{17,})")


def defang(text):
    if not text:
        return text
    text = _AWS_ID.sub(lambda m: "AKIA" + m.group(1)[:9] + "EXAMPLE", text)
    text = _SECRET40.sub(lambda m: m.group(1)[:30] + "EXAMPLEKEY", text)
    text = _STRIPE.sub(lambda m: m.group(1) + m.group(2)[:16], text)
    return text


def defang_bank(doc, only_source="invented_v2"):
    changed = 0
    for p in doc["prompts"]:
        if only_source and p.get("source") != only_source:
            continue                        # real WildChat prompts are never touched
        for f in ("type_text", "paste_text"):
            new = defang(p.get(f) or "")
            if new != (p.get(f) or ""):
                p[f] = new; changed += 1
    doc.setdefault("meta", {})["example_style_keys"] = True
    return changed


if __name__ == "__main__":
    doc = json.load(open(sys.argv[1], encoding="utf-8"))
    n = defang_bank(doc)
    json.dump(doc, open(sys.argv[2], "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"rewrote key strings in {n} text fields -> {sys.argv[2]}")
