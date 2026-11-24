#!/usr/bin/env python3
"""Tests for mask_secrets.py. All values are public documentation examples or invented.
Run: python -m pytest code/test_mask_secrets.py   (or: python code/test_mask_secrets.py)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mask_secrets import mask, mask_text

CASES = [
    # (input, expected output, expected counts)
    ("my key is AKIAIOSFODNN7EXAMPLE ok", "my key is [AWS_KEY] ok", {"AWS_KEY": 1}),
    ("aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
     "aws_secret_access_key = [SECRET]", {"SECRET": 1}),
    ("use sk-proj-abcdefghijklmnopqrstuvwxyz0123 here", "use [API_KEY] here", {"API_KEY": 1}),
    ("token ghp_abcdefghijklmnopqrstuvwxyz0123456789AB", "token [GITHUB_TOKEN]", {"GITHUB_TOKEN": 1}),
    ("slack xoxb-1234567890-abcdefghij", "slack [SLACK_TOKEN]", {"SLACK_TOKEN": 1}),
    ("DATABASE_URL=postgres://admin:hunter2pass@db.internal.example:5432/app",
     "DATABASE_URL=[DB_URL]/app", {"DB_URL": 1}),
    ("password: Tr0ub4dor&3", "password: [PASSWORD]", {"PASSWORD": 1}),
    ('{"password": "correcthorse"}', '{"password": "[PASSWORD]"}', {"PASSWORD": 1}),
    ("Authorization: Bearer abcdefghijklmnop1234567890", "Authorization: Bearer [SECRET]", {"SECRET": 1}),
    ("card 4111 1111 1111 1111 exp 12/29", "card [CARD] exp 12/29", {"CARD": 1}),
    ("card 4242-4242-4242-4242", "card [CARD]", {"CARD": 1}),
    ("amex 3782 822463 10005 ok", "amex [CARD] ok", {"CARD": 1}),
    ("ssn 123-45-6789", "ssn [SSN]", {"SSN": 1}),
    ("mail jane.doe@example.com now", "mail [EMAIL] now", {"EMAIL": 1}),
    ("call (303) 555-0142 or +1 303-555-0199", "call [PHONE] or [PHONE]", {"PHONE": 2}),
    ("server at 10.0.12.7", "server at [IP_ADDR]", {"IP_ADDR": 1}),
    ("-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAKj34GkxFhD90vcNLYLInFEX\n-----END RSA PRIVATE KEY-----\nthanks",
     "[PRIVATE_KEY]\nthanks", {"PRIVATE_KEY": 1}),
]

# things that must NOT be masked
CLEAN = [
    "write a birthday poem for my mom",
    "explain a SQL LEFT JOIN",
    "what does a DLP system do",
    "order 1234567890123 shipped",            # 13 digits, starts with 1: not a card
    "card 4111 1111 1111 1112",                # fails Luhn
    "numbers 61 62 63 64 65 66 67 68 bonus",   # list of small numbers, not a card
    "SSN format is 000-12-3456",               # invalid area
    "the meeting is on 2026-11-20 at 14:30",
    "localhost is 127.0.0.1",
    "a secret relationship that lasted years",  # 'secret' without key=value
]


def test_cases():
    for text, want, wantc in CASES:
        got, c = mask(text)
        assert got == want, f"\n in:   {text!r}\n got:  {got!r}\n want: {want!r}"
        assert c == wantc, f"counts for {text!r}: {c} != {wantc}"


def test_clean():
    for text in CLEAN:
        got, c = mask(text)
        assert got == text and c == {}, f"false positive on {text!r}: {got!r} {c}"


def test_idempotent():
    for text, _, _ in CASES:
        once = mask_text(text)
        assert mask_text(once) == once, f"not idempotent: {once!r}"


def test_no_values_returned():
    _, c = mask("AKIAIOSFODNN7EXAMPLE jane.doe@example.com")
    assert all(isinstance(k, str) and isinstance(v, int) for k, v in c.items())
    assert "AKIA" not in repr(c) and "example.com" not in repr(c)


def test_empty():
    assert mask("") == ("", {}) and mask(None) == ("", {})


if __name__ == "__main__":
    for f in (test_cases, test_clean, test_idempotent, test_no_values_returned, test_empty):
        f(); print("ok", f.__name__)
