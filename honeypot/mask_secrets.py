#!/usr/bin/env python3
"""Mask secrets and personal identifiers in prompt text with typed placeholders.

    from mask_secrets import mask
    masked, counts = mask(text)      # counts: {"EMAIL": 2, "AWS_KEY": 1, ...}

This is a redaction step, run before a prompt is stored, shown to a rater, used for
training, or scored by the live gateway. Train and serve must use the same function so
the content model learns the context around a secret ("here is our prod key: [AWS_KEY]")
and never the secret's format.

Design rules:
  * Standard library only (re), so it runs inside the stdlib-only gateway server.
  * Output is the masked text and a count per placeholder type. No function in this
    module returns, logs, or stores a matched value.
  * Precision over recall on numbers: card numbers must pass the Luhn check and SSNs
    must have a valid area/group/serial, so ordinary IDs, dates and amounts survive.
  * Key=value secrets keep the key name and lose only the value
    ("password: [PASSWORD]"), so the model still sees that a password was pasted.

Placeholders: PRIVATE_KEY, AWS_KEY, API_KEY, GITHUB_TOKEN, SLACK_TOKEN, JWT, DB_URL,
PASSWORD, SECRET, CARD, SSN, EMAIL, PHONE, IP_ADDR.
"""
import re
from collections import Counter

MASK_VERSION = "mask_v1"
PLACEHOLDERS = ("PRIVATE_KEY", "AWS_KEY", "API_KEY", "GITHUB_TOKEN", "SLACK_TOKEN", "JWT", "DB_URL",
                "PASSWORD", "SECRET", "CARD", "SSN", "EMAIL", "PHONE", "IP_ADDR")


def _luhn_ok(digits):
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def _card_ok(raw):
    # card numbers start with 3, 4, 5 or 6 (Amex/Diners/JCB, Visa, Mastercard, Discover/UnionPay),
    # which keeps 13-digit millisecond timestamps and order numbers out; when written with
    # separators they come in groups of 4 (or Amex 4-6-5), which keeps lists of small numbers
    # ("61 62 63 64 ...") out
    d = re.sub(r"\D", "", raw)
    if not (13 <= len(d) <= 19 and d[0] in "3456" and _luhn_ok(d)):
        return False
    groups = [g for g in re.split(r"[ -]", raw) if g]
    if len(groups) == 1:
        return True
    lens = [len(g) for g in groups]
    return lens == [4, 6, 5] or (all(n == 4 for n in lens[:-1]) and 1 <= lens[-1] <= 4)


def _ssn_ok(area, group, serial):
    return not (area in ("000", "666") or area[0] == "9" or group == "00" or serial == "0000")


# Each rule: (placeholder, compiled pattern, how to replace). Order matters: whole blocks and
# URLs first, then tokens with a fixed shape, then key=value pairs, then numbers, then contact details.
_RULES = []


def _rule(name, pattern, flags=0, group=None, check=None):
    _RULES.append((name, re.compile(pattern, flags), group, check))


# full PEM private-key block (also a truncated one with no END line)
_rule("PRIVATE_KEY", r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----(?:.*?-----END (?:[A-Z]+ )?PRIVATE KEY-----|[\s\S]{0,4000})", re.S)
# database / broker URLs with an embedded password: keep the scheme, mask user:pass@host
_rule("DB_URL", r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|rediss|amqp|amqps|mssql|sqlserver)://[^\s:/@]+:[^\s@/]+@[^\s/'\"]+", re.I)
_rule("JWT", r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
_rule("AWS_KEY", r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA)[0-9A-Z]{16}\b")
_rule("GITHUB_TOKEN", r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})")
_rule("SLACK_TOKEN", r"\bxox[abprs]-[A-Za-z0-9-]{10,}")
_rule("API_KEY", r"\b(?:sk-(?:ant-|proj-|live-|test-)?[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{35}|(?:rk|pk|sk)_(?:live|test)_[A-Za-z0-9]{16,})")
# key = value secrets: mask only the value (group 1)
_rule("PASSWORD", r"\b(?:password|passwd|pwd|pass)\b[\"']?\s*[:=]\s*[\"']?([^\s\"',;]{4,})", re.I, group=1)
_rule("SECRET", r"\b(?:aws_secret_access_key|secret(?:_key)?|client_secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9/+_.=-]{12,})", re.I, group=1)
_rule("SECRET", r"\bBearer\s+([A-Za-z0-9/+_.=-]{16,})", group=1)
_rule("CARD", r"\b(?:\d[ -]?){12,18}\d\b", check=lambda m: _card_ok(m.group(0)))
_rule("SSN", r"\b(\d{3})-(\d{2})-(\d{4})\b", check=lambda m: _ssn_ok(m.group(1), m.group(2), m.group(3)))
_rule("EMAIL", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
_rule("PHONE", r"(?<![\w.])(?:\+\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?![\w.])")
_rule("IP_ADDR", r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b",
      check=lambda m: not m.group(0).startswith(("0.", "127.", "255.")))


def mask(text):
    """Return (masked_text, counts). counts maps placeholder type -> number of spans masked."""
    if not text:
        return text or "", {}
    counts = Counter()
    for name, rx, group, check in _RULES:
        def _sub(m, name=name, group=group, check=check):
            if check is not None and not check(m):
                return m.group(0)
            counts[name] += 1
            if group is None:
                return f"[{name}]"
            s, e = m.span(group)
            base = m.start(0)
            whole = m.group(0)
            return whole[: s - base] + f"[{name}]" + whole[e - base:]
        text = rx.sub(_sub, text)
    return text, dict(counts)


def mask_text(text):
    """Masked text only (for vectorizers and the gateway)."""
    return mask(text)[0]


if __name__ == "__main__":
    import sys
    data = sys.stdin.read()
    out, c = mask(data)
    sys.stdout.write(out)
    sys.stderr.write(f"\n{MASK_VERSION} masked: {c}\n")
