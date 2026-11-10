#!/usr/bin/env python3
"""
sim_sessions.py  —  Phase 3 behavioral-capture generator for the browsing-agent honeypot.

Drives the REAL honeypot pages with a REAL Chromium (Playwright) so the site's own passive
tracker (honeypot/site/js/script.js) records genuine mouse/keyboard/scroll/input events and POSTs
them to captures/<TOKEN>_mm.jsonl, exactly as it would for Browser Use or Skyvern. The only thing
simulated is the *driver's behavior profile*, chosen to span the regimes that separate automated
browsing agents from a human:

  AGENT profiles (label = agent):
    fill_bot     programmatic DOM fill() for every field, element clicks; no typing, no mouse path.
                 ~ Skyvern's default (single fill() per field).
    type_bot     types every character at a fixed, machine-uniform cadence; element clicks.
                 ~ Skyvern patched to type every char / Browser Use typing.
    evasive_bot  types with mild random jitter and moves the mouse in near-straight hops between
                 fields — an agent trying to look human but still regular.

  HUMAN profile (label = human) — SIMULATED stand-in until real human control sessions are collected:
    sim_human    curved, jittery mouse paths; keystrokes with log-normal dwell and gap, think-time
                 pauses, and occasional typo+backspace corrections; wheel scrolling with pauses.

Each session is one fresh browser context (fresh cookies) on one scenario page. We write our OWN
manifest (token -> profile, class, scenario) as the source of truth for labels; the training
notebook joins it onto the features by token and ignores behavioral_features.py's own label guess.

  python sim_sessions.py --base http://127.0.0.1:8781 --manifest captures/sim_manifest.jsonl \
      --repeats-agent 6 --repeats-human 18 --shard 0 --nshards 1
"""
import argparse, json, math, os, random, string, time
from pathlib import Path
from playwright.sync_api import sync_playwright

SCENARIOS = ["forums", "flights", "shop", "careers", "sort", "game"]
PATHS = {s: f"/{s}" for s in SCENARIOS}

AGENT_PROFILES = ["fill_bot", "type_bot", "evasive_bot"]
HUMAN_PROFILES = ["sim_human"]

FIRST = ["Jane", "Marcus", "Priya", "Tom", "Aisha", "Daniel", "Mei", "Carlos", "Nadia", "Erik"]
LAST = ["Doe", "Ortiz", "Patel", "Nguyen", "Okafor", "Schmidt", "Chen", "Rivera", "Brooks", "Tan"]
SENTENCES = [
    "I have several years of relevant experience and I work well on a team.",
    "I am excited about this role and I learn new tools quickly.",
    "Thanks for the thread, this was really helpful to read through.",
    "I reliable and detail oriented and I enjoy solving hard problems.",
    "Happy to share more about my background if that would help.",
]
WORDS = "the quick brown fox jumps over a lazy dog while the sun sets slowly".split()


def tok(profile, scenario, trial):
    pa = "".join(c for c in profile.upper() if c.isalnum())[:8]
    sa = "".join(c for c in scenario.upper() if c.isalnum())[:6]
    sfx = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{pa}-{sa}-T{trial:03d}-{sfx}"[:32]


# ----------------------- behavior primitives -----------------------
def human_mouse(page, x0, y0, x1, y1, rng):
    """Curved, jittery path from (x0,y0) to (x1,y1) via a jittered quadratic Bezier."""
    dist = math.hypot(x1 - x0, y1 - y0)
    steps = max(8, int(dist / rng.uniform(6, 14)))
    mx = (x0 + x1) / 2 + rng.uniform(-0.35, 0.35) * dist
    my = (y0 + y1) / 2 + rng.uniform(-0.35, 0.35) * dist
    for i in range(1, steps + 1):
        t = i / steps
        bx = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * mx + t * t * x1 + rng.uniform(-2, 2)
        by = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * my + t * t * y1 + rng.uniform(-2, 2)
        page.mouse.move(bx, by, steps=1)
        if rng.random() < 0.15:
            page.wait_for_timeout(rng.randint(5, 25))
    return x1, y1


def straight_mouse(page, x0, y0, x1, y1, steps=2):
    page.mouse.move(x1, y1, steps=steps)
    return x1, y1


def center(page, selector):
    try:
        bb = page.locator(selector).first.bounding_box()
        if bb:
            return bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
    except Exception:
        pass
    return None


ASCII_OK = set(string.ascii_letters + string.digits + " .,!?@'-")


def type_human(page, text, rng):
    for ch in text:
        # occasional typo then correction
        if rng.random() < 0.06 and ch != " ":
            wrong = rng.choice(string.ascii_lowercase)
            _press(page, wrong, dwell=rng.uniform(0.04, 0.12))
            page.wait_for_timeout(int(rng.uniform(40, 160)))
            _press(page, "Backspace", dwell=rng.uniform(0.03, 0.08))
            page.wait_for_timeout(int(rng.uniform(30, 120)))
        _press(page, ch, dwell=max(0.02, rng.lognormvariate(math.log(0.075), 0.5)))
        gap = max(0.02, rng.lognormvariate(math.log(0.12), 0.6))
        if rng.random() < 0.08:          # think-time pause
            gap += rng.uniform(0.3, 1.1)
        page.wait_for_timeout(int(gap * 1000))


def type_uniform(page, text, dwell=0.03, gap=0.05, jitter=0.0, rng=None):
    for ch in text:
        d = dwell * (1 + (rng.uniform(-jitter, jitter) if (jitter and rng) else 0))
        g = gap * (1 + (rng.uniform(-jitter, jitter) if (jitter and rng) else 0))
        _press(page, ch, dwell=max(0.005, d))
        page.wait_for_timeout(int(max(0.005, g) * 1000))


def _press(page, ch, dwell=0.03):
    key = ch
    if ch == " ":
        key = " "
    try:
        if ch in ASCII_OK or ch == "Backspace":
            page.keyboard.down(key)
            time.sleep(dwell)
            page.keyboard.up(key)
        else:
            page.keyboard.insert_text(ch)
    except Exception:
        try:
            page.keyboard.insert_text(ch)
        except Exception:
            pass


def value_for(el_type, name, rng):
    name = (name or "").lower()
    if el_type == "email" or "email" in name:
        return f"{rng.choice(FIRST).lower()}.{rng.choice(LAST).lower()}@example.com"
    if el_type == "tel" or "phone" in name:
        return f"555{rng.randint(1000000,9999999)}"
    if el_type == "number":
        return str(rng.randint(1, 9))
    if "name" in name or "user" in name:
        return f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    if "title" in name:
        return " ".join(rng.sample(WORDS, 4)).capitalize()
    if "search" in name or el_type == "search":
        return rng.choice(["shirt", "mug", "lamp", "shoes", "bag"])
    return rng.choice(SENTENCES)


# ----------------------- one session -----------------------
def run_session(browser, base, token, scenario, profile, rng):
    is_human = profile in HUMAN_PROFILES
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    completed = False
    mx, my = 640, 450
    try:
        page.goto(f"{base}/{token}{PATHS[scenario]}", wait_until="networkidle", timeout=20000)
        page.wait_for_timeout(rng.randint(400, 900) if is_human else rng.randint(120, 300))

        # reveal hidden application form (careers) by clicking the first primary action
        for sel in [".apply-btn", "#start-btn", ".start-btn", "button#unlock", ".unlock-btn"]:
            if page.locator(sel).count() > 0:
                c = center(page, sel)
                if c:
                    if is_human:
                        mx, my = human_mouse(page, mx, my, c[0], c[1], rng)
                    else:
                        mx, my = straight_mouse(page, mx, my, c[0], c[1])
                try:
                    page.locator(sel).first.click(timeout=2000)
                except Exception:
                    pass
                page.wait_for_timeout(rng.randint(250, 600) if is_human else 150)
                break

        # human scrolls to read; agents mostly don't
        if is_human:
            for _ in range(rng.randint(2, 5)):
                page.mouse.wheel(0, rng.randint(150, 420))
                page.wait_for_timeout(rng.randint(200, 700))
        elif rng.random() < 0.3:
            page.mouse.wheel(0, rng.randint(200, 500))

        # collect visible fillable controls
        controls = page.locator(
            "input[type=text], input[type=email], input[type=tel], input[type=search], "
            "input[type=number], input:not([type]), textarea, select"
        )
        n = min(controls.count(), 8)
        for i in range(n):
            el = controls.nth(i)
            try:
                if not el.is_visible():
                    continue
            except Exception:
                continue
            tag = el.evaluate("e => e.tagName.toLowerCase()")
            etype = (el.get_attribute("type") or "text")
            ename = el.get_attribute("name") or el.get_attribute("id") or ""

            if tag == "select":
                try:
                    opts = el.locator("option")
                    k = opts.count()
                    if k > 1:
                        el.select_option(index=rng.randint(1, k - 1))
                except Exception:
                    pass
                continue

            val = value_for(etype, ename, rng)
            c = center(page, f"#{el.get_attribute('id')}") if el.get_attribute("id") else None
            if c:
                if is_human:
                    mx, my = human_mouse(page, mx, my, c[0], c[1], rng)
                    page.wait_for_timeout(rng.randint(80, 300))
                elif profile == "evasive_bot":
                    mx, my = straight_mouse(page, mx, my, c[0], c[1], steps=rng.randint(2, 4))

            if profile == "fill_bot":
                try:
                    el.fill(val, timeout=2000)
                except Exception:
                    pass
            else:
                try:
                    el.click(timeout=2000)
                except Exception:
                    continue
                if profile == "type_bot":
                    type_uniform(page, val, dwell=0.028, gap=0.045, rng=rng)
                elif profile == "evasive_bot":
                    type_uniform(page, val, dwell=0.05, gap=0.07, jitter=0.35, rng=rng)
                else:  # sim_human
                    type_human(page, val, rng)

        # click a couple of buttons (submit / add-to-cart / tiles) to generate click events
        btns = page.locator("button, .tile, .add-to-cart, input[type=submit]")
        bn = btns.count()
        for _ in range(min(bn, 3 if scenario in ("game", "shop") else 1)):
            j = rng.randint(0, bn - 1)
            try:
                b = btns.nth(j)
                if not b.is_visible():
                    continue
                bb = b.bounding_box()
                if bb:
                    tx, ty = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
                    if is_human:
                        mx, my = human_mouse(page, mx, my, tx, ty, rng)
                    else:
                        mx, my = straight_mouse(page, mx, my, tx, ty)
                b.click(timeout=1500)
                page.wait_for_timeout(rng.randint(150, 500) if is_human else 120)
            except Exception:
                pass

        # was a completion recorded?
        completed = page.locator("#careers-confirmation:not([hidden]), .completion, #completion").count() > 0

        # let the 500ms interval flush, then force a flush via visibility change
        page.wait_for_timeout(900)
        try:
            page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        except Exception:
            pass
        page.wait_for_timeout(300)
    finally:
        try: page.close()
        except Exception: pass
        try: ctx.close()
        except Exception: pass
    return completed


def build_jobs(ra, rh):
    jobs = []
    for prof in AGENT_PROFILES:
        for s in SCENARIOS:
            for t in range(1, ra + 1):
                jobs.append((prof, s, t))
    for prof in HUMAN_PROFILES:
        for s in SCENARIOS:
            for t in range(1, rh + 1):
                jobs.append((prof, s, t))
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8781")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--repeats-agent", type=int, default=6)
    ap.add_argument("--repeats-human", type=int, default=18)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--seed", type=int, default=20261107)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    jobs = build_jobs(args.repeats_agent, args.repeats_human)
    jobs = [j for idx, j in enumerate(jobs) if idx % args.nshards == args.shard]
    mpath = Path(args.manifest)
    mpath.parent.mkdir(parents=True, exist_ok=True)
    shard_manifest = mpath.with_suffix(f".shard{args.shard}.jsonl")

    rng = random.Random(args.seed + args.shard * 101)
    done = 0
    with sync_playwright() as pw, open(shard_manifest, "w", encoding="utf-8") as mf:
        browser = pw.chromium.launch(headless=not args.headed,
                                     args=["--no-sandbox", "--disable-dev-shm-usage"])
        for prof, scen, trial in jobs:
            token = tok(prof, scen, trial)
            cls = "human" if prof in HUMAN_PROFILES else "agent"
            t0 = time.time()
            try:
                completed = run_session(browser, args.base, token, scen, prof, rng)
                status = "ok"
            except Exception as e:
                completed = False
                status = f"error:{type(e).__name__}"
            rec = {"token": token, "version_token": token, "profile": prof, "bot": prof,
                   "framework_class": cls, "label": cls, "scenario": scen, "trial": trial,
                   "status": status, "completed": completed, "dur_s": round(time.time() - t0, 2)}
            mf.write(json.dumps(rec) + "\n"); mf.flush()
            done += 1
            print(f"[shard{args.shard}] {done}/{len(jobs)} {token} {prof}/{scen} {status} {rec['dur_s']}s")
        try: browser.close()
        except Exception: pass
    print(f"[shard{args.shard}] wrote {shard_manifest}")


if __name__ == "__main__":
    main()
