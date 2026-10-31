#!/usr/bin/env python3
"""Run many agent sessions against the honeypot and log them to a manifest.

Calls agent.py once per (bot, scenario, trial), gives every run a unique capture
token, and appends one JSON line per run to captures/manifest.jsonl, mapping
the token to its bot, scenario, trial index, and outcome.

Examples
    python run_batch.py --repeats 5
    python run_batch.py --bots my_llm,skyvern_local --scenarios forums,shopping --repeats 3
    python run_batch.py --repeats 10 --parallel 3 --headless
    python run_batch.py --dry-run --repeats 2
"""

import argparse
import concurrent.futures
import json
import random
import string
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config.yaml"
AGENT_SCRIPT = SCRIPT_DIR / "agent.py"
DEFAULT_MANIFEST = SCRIPT_DIR.parent / "captures" / "manifest.jsonl"

TOKEN_CHARS = string.ascii_uppercase + string.digits
MAX_TOKEN_LEN = 32

_manifest_lock = threading.Lock()
_token_lock = threading.Lock()
_used_tokens = set()


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        sys.exit(f"ERROR: config file not found: {config_path}")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_existing_tokens(manifest_path: Path) -> set:
    """Pre-seed the used-token set from a prior manifest so reruns never collide."""
    tokens = set()
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    tokens.add(json.loads(line)["version_token"])
                except (json.JSONDecodeError, KeyError):
                    continue
    return tokens


def load_existing_trial_counts(manifest_path: Path) -> dict:
    """Return {(bot, scenario): highest trial_index already recorded}."""
    counts = {}
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    key = (rec["bot"], rec["scenario"])
                    counts[key] = max(counts.get(key, 0), rec["trial_index"])
                except (json.JSONDecodeError, KeyError):
                    continue
    return counts


def abbreviate(name: str, max_len: int) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in name.upper())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned[:max_len].strip("_") or "X"


def make_version_token(bot: str, scenario: str, trial_index: int) -> str:
    """Format: <BOT_ABBR>-<SCEN_ABBR>-T<trial>-<random_suffix>, fit to 32 chars."""
    trial_part = f"T{trial_index:03d}"
    with _token_lock:
        for _ in range(50):
            suffix = "".join(random.choices(TOKEN_CHARS, k=4))
            reserved = len(trial_part) + len(suffix) + 3  # separators
            budget = max(2, MAX_TOKEN_LEN - reserved)
            bot_budget = max(1, budget // 2)
            scen_budget = max(1, budget - bot_budget)
            bot_abbr = abbreviate(bot, bot_budget)
            scen_abbr = abbreviate(scenario, scen_budget)
            token = f"{bot_abbr}-{scen_abbr}-{trial_part}-{suffix}"[:MAX_TOKEN_LEN]
            token = token.strip("-") or f"RUN-{suffix}"
            if token not in _used_tokens:
                _used_tokens.add(token)
                return token
    raise RuntimeError("Could not generate a unique version token after 50 attempts")


def append_manifest(manifest_path: Path, record: dict) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with _manifest_lock:
        with open(manifest_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def run_single(bot: str, scenario: str, trial_index: int, version_token: str, args) -> dict:
    cmd = [
        sys.executable, str(AGENT_SCRIPT),
        "--bot", bot,
        "--scenario", scenario,
        "--version", version_token,
    ]
    if args.headless:
        cmd.append("--headless")
    if args.dry_run:
        cmd.append("--dry-run")

    record = {
        "version_token": version_token,
        "bot": bot,
        "scenario": scenario,
        "trial_index": trial_index,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "is_dry_run": bool(args.dry_run),
    }

    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(SCRIPT_DIR),
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
        duration = time.monotonic() - start
        record.update({
            "status": "success" if proc.returncode == 0 else "failed",
            "return_code": proc.returncode,
            "duration_sec": round(duration, 2),
            "stderr_tail": proc.stderr[-2000:] if proc.returncode != 0 else "",
        })
        tag = "OK" if proc.returncode == 0 else f"FAIL(rc={proc.returncode})"
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        record.update({
            "status": "timeout",
            "return_code": None,
            "duration_sec": round(duration, 2),
            "stderr_tail": f"Timed out after {args.timeout}s",
        })
        tag = "TIMEOUT"
    except Exception as e:  # noqa: BLE001  (log any failure and continue the batch)
        duration = time.monotonic() - start
        record.update({
            "status": "error",
            "return_code": None,
            "duration_sec": round(duration, 2),
            "stderr_tail": str(e),
        })
        tag = f"ERROR({e})"

    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    print(f"[{tag}] bot={bot} scenario={scenario} trial={trial_index} "
          f"version={version_token} ({record['duration_sec']}s)")
    append_manifest(args.manifest, record)
    return record


def build_job_list(bots, scenarios, repeats, existing_counts):
    """(bot, scenario, trial_index) jobs; trial numbering continues from the manifest."""
    jobs = []
    for bot in bots:
        for scenario in scenarios:
            start = existing_counts.get((bot, scenario), 0) + 1
            jobs.extend(
                (bot, scenario, trial)
                for trial in range(start, start + repeats)
            )
    return jobs


def parse_args():
    p = argparse.ArgumentParser(description="Batch-run browser agents against the honeypot site.")
    p.add_argument("--bots", type=str, default=None,
                    help="Comma-separated bot names (default: all bots in config.yaml)")
    p.add_argument("--scenarios", type=str, default=None,
                    help="Comma-separated scenario names (default: all scenarios in config.yaml)")
    p.add_argument("--repeats", type=int, default=5, help="Trials per bot/scenario combo (default: 5)")
    p.add_argument("--parallel", type=int, default=1, help="Max concurrent runs (default: 1 = sequential)")
    p.add_argument("--headless", action="store_true", help="Pass --headless to agent.py")
    p.add_argument("--dry-run", action="store_true", help="Pass --dry-run to agent.py (no browser launch)")
    p.add_argument("--timeout", type=int, default=600, help="Per-run timeout in seconds (default: 600)")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to config.yaml")
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to manifest.jsonl")
    p.add_argument("--shuffle", action="store_true", help="Shuffle job order (spreads load, avoids order bias)")
    p.add_argument("--list-bots", action="store_true", help="List configured bots and exit")
    p.add_argument("--list-scenarios", action="store_true", help="List configured scenarios and exit")
    p.add_argument("--fail-fast", type=int, default=0, metavar="N",
                    help="Abort the batch after N consecutive non-success runs (0 = disabled, default)")
    return p.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)

    all_bots = list(config.get("bots", {}).keys())
    all_scenarios = list(config.get("scenarios", {}).keys())

    if args.list_bots:
        print("\n".join(all_bots))
        return
    if args.list_scenarios:
        print("\n".join(all_scenarios))
        return

    bots = [b.strip() for b in args.bots.split(",")] if args.bots else all_bots
    scenarios = [s.strip() for s in args.scenarios.split(",")] if args.scenarios else all_scenarios

    unknown_bots = [b for b in bots if b not in all_bots]
    unknown_scenarios = [s for s in scenarios if s not in all_scenarios]
    if unknown_bots:
        sys.exit(f"ERROR: unknown bot(s) not in config: {unknown_bots}")
    if unknown_scenarios:
        sys.exit(f"ERROR: unknown scenario(s) not in config: {unknown_scenarios}")

    if not AGENT_SCRIPT.exists():
        sys.exit(f"ERROR: agent.py not found at {AGENT_SCRIPT}")

    # Continue token de-duplication and trial numbering from an existing manifest.
    _used_tokens.update(load_existing_tokens(args.manifest))
    existing_counts = load_existing_trial_counts(args.manifest)

    jobs = build_job_list(bots, scenarios, args.repeats, existing_counts)
    if args.shuffle:
        random.shuffle(jobs)

    print(f"Batch run: {len(bots)} bots x {len(scenarios)} scenarios x {args.repeats} trials "
          f"= {len(jobs)} total runs")
    print(f"Parallelism: {args.parallel} | Timeout: {args.timeout}s | Manifest: {args.manifest}")
    if args.dry_run:
        print("(dry-run mode: agent.py will resolve config but not launch a browser)")
    print("-" * 70)

    results = []
    aborted = False

    if args.parallel <= 1:
        consecutive_failures = 0
        for bot, scenario, trial in jobs:
            token = make_version_token(bot, scenario, trial)
            record = run_single(bot, scenario, trial, token, args)
            results.append(record)
            if record["status"] == "success":
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if args.fail_fast and consecutive_failures >= args.fail_fast:
                    print(f"\n!! --fail-fast triggered: {consecutive_failures} consecutive "
                          f"non-success runs. Aborting remaining {len(jobs) - len(results)} run(s). "
                          f"Check stderr_tail in the manifest for the root cause.")
                    aborted = True
                    break
    else:
        # With parallel runs, --fail-fast stops submitting new jobs once the last N
        # finished runs all failed; runs already started are allowed to finish.
        stop_event = threading.Event()
        recent_statuses = []
        recent_lock = threading.Lock()

        def tracked_run(bot, scenario, trial, token):
            record = run_single(bot, scenario, trial, token, args)
            with recent_lock:
                recent_statuses.append(record["status"])
                del recent_statuses[:-max(args.fail_fast, 1)]  # keep only last N
                if (args.fail_fast and len(recent_statuses) >= args.fail_fast
                        and all(s != "success" for s in recent_statuses)):
                    stop_event.set()
            return record

        with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = []
            for bot, scenario, trial in jobs:
                if stop_event.is_set():
                    aborted = True
                    break
                token = make_version_token(bot, scenario, trial)
                futures.append(executor.submit(tracked_run, bot, scenario, trial, token))
            for fut in concurrent.futures.as_completed(futures):
                results.append(fut.result())

        if aborted:
            print(f"\n!! --fail-fast triggered: {args.fail_fast} consecutive non-success runs "
                  f"in-flight. Stopped submitting new jobs ({len(jobs) - len(futures)} skipped). "
                  f"Check stderr_tail in the manifest for the root cause.")

    succeeded = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failed")
    timed_out = sum(1 for r in results if r["status"] == "timeout")
    errored = sum(1 for r in results if r["status"] == "error")

    print("-" * 70)
    status_line = f"Done. {succeeded} succeeded, {failed} failed, {timed_out} timed out, {errored} errored "
    status_line += f"out of {len(results)}/{len(jobs)} total runs."
    if aborted:
        status_line += " (batch aborted early via --fail-fast)"
    print(status_line)
    print(f"Manifest written to: {args.manifest}")

    if aborted or failed or timed_out or errored:
        sys.exit(1)


if __name__ == "__main__":
    main()