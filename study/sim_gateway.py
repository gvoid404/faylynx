#!/usr/bin/env python3
"""Agent driver for the live Prompt Study page. Each session enters ONE prompt from the prompt bank
(?scenario=<id>) under an agent behavior profile, so the server logs prompt + class + per-prompt
behavior + network for it. Plan (default): every Automated prompt under all 3 profiles, plus every
Allow/Shadow prompt once (profile rotates), so content and actor are not confounded.

  python sim_gateway.py --base https://clemons.us --user study
"""
import argparse, getpass, json, os, random, string, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim_sessions import straight_mouse, type_uniform, center  # noqa

PROFILES = ["fill_bot", "type_bot", "evasive_bot"]
CODE = {"Allow": "A", "Shadow AI": "S", "Automated AI Pipelines": "M"}


def tok(profile, pid):
    sfx = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"AG-{profile.split('_')[0].upper()}-{pid}-{sfx}"[:32]


def full_text(p):
    return p["type_text"] + (("\n\n" + p["paste_text"]) if p.get("paste_text") else "")


def paste(page, text):
    page.evaluate("""([text]) => { const el=document.querySelector('#gw-prompt'); el.focus();
      try { const dt=new DataTransfer(); dt.setData('text', text);
            el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true})); } catch(e){}
      el.value = el.value + text; el.dispatchEvent(new Event('input',{bubbles:true})); }""", [text])


def run(browser, base, token, p, profile, rng, insecure, creds=None):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, ignore_https_errors=insecure,
                              http_credentials=creds)
    page = ctx.new_page()
    try:
        page.goto(f"{base}/{token}/gateway?scenario={p['id']}", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(250)
        page.check("#gw-agree"); page.click("#gw-start"); page.wait_for_timeout(200)
        text = full_text(p)
        if profile == "fill_bot":
            page.fill("#gw-prompt", text)
        else:
            c = center(page, "#gw-prompt")
            if c and profile == "evasive_bot":
                straight_mouse(page, 400, 300, c[0], c[1], steps=3)
            page.click("#gw-prompt")
            head, tail = (text, "") if len(text) <= 400 else (text[:300], text[300:])
            if profile == "type_bot":
                type_uniform(page, head, dwell=0.008, gap=0.012, rng=rng)
            else:
                type_uniform(page, head, dwell=0.03, gap=0.045, jitter=0.35, rng=rng)
            if tail:
                paste(page, tail)
        page.wait_for_timeout(150)
        page.click("#gw-send"); page.wait_for_timeout(400)
    finally:
        ctx.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--bank", default=str(Path(__file__).resolve().parent / "prompt_bank.json"))
    ap.add_argument("--manifest", default="agent_manifest.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="run only the first N jobs (smoke test)")
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--user", help="site login username (the password is read from the PROMPTGATE_PASSWORD\n                    environment variable, or asked for; it is never put on the command line)")
    ap.add_argument("--seed", type=int, default=20261109)
    a = ap.parse_args(); rng = random.Random(a.seed)
    creds = None
    if a.user:
        pw = os.environ.get("PROMPTGATE_PASSWORD") or getpass.getpass(f"Site password for {a.user}: ")
        creds = {"username": a.user, "password": pw}
    bank = json.load(open(a.bank))["prompts"]
    jobs = [(pr, p) for p in bank if p["class"] == "Automated AI Pipelines" for pr in PROFILES]
    jobs += [(PROFILES[i % 3], p) for i, p in enumerate(q for q in bank if q["class"] != "Automated AI Pipelines")]
    rng.shuffle(jobs)
    if a.limit: jobs = jobs[:a.limit]
    print(f"{len(jobs)} agent sessions -> {a.base}")
    with sync_playwright() as pw, open(a.manifest, "a", encoding="utf-8") as mf:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        for i, (profile, p) in enumerate(jobs, 1):
            token = tok(profile, p["id"]); t0 = time.time()
            try: run(browser, a.base, token, p, profile, rng, a.insecure, creds); status = "ok"
            except Exception as e: status = f"error:{type(e).__name__}"
            mf.write(json.dumps({"token": token, "label": "agent", "profile": profile, "prompt_id": p["id"],
                                 "target_class": p["class"], "status": status}) + "\n"); mf.flush()
            print(f"{i}/{len(jobs)} {token} {status} {time.time()-t0:.1f}s")
        browser.close()


if __name__ == "__main__":
    main()
