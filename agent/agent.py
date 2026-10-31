"""Run one browsing-agent session against the honeypot.

The agent (LLM backend + framework) and the task are chosen by name from
config.yaml; the task prompt is read from prompts/<task>.txt.

Examples
    python agent.py --list-bots
    python agent.py --bot my_llm --scenario forums
    python agent.py --bot my_llm --scenario careers --version TRIAL0042 --headless
    python agent.py --bot skyvern_local --scenario shopping --dry-run

--version is the capture token used in the honeypot URL; one is generated if
omitted. --dry-run prints the resolved configuration and prompt and exits
without starting a browser or calling a model.
"""

import argparse
import asyncio
import os
import random
import re
import string
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_version(scenario_name: str) -> str:
    prefix = re.sub(r"[^A-Z0-9]", "", scenario_name.upper())[:10] or "TRIAL"
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}{suffix}"[:32]


def load_prompt(prompt_file: str, start_url: str) -> str:
    return (HERE / prompt_file).read_text(encoding="utf-8").format(start_url=start_url)


def resolve_upload_files(scenario: dict) -> list[str]:
    resolved = []
    for rel_path in scenario.get("upload_files") or []:
        path = (HERE / rel_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"upload file not found: {path}")
        resolved.append(str(path))
    return resolved


def resolve_bot(config: dict, name: str) -> dict:
    bots = config.get("bots", {})
    if name not in bots:
        raise ValueError(f"unknown bot '{name}'; available: {', '.join(sorted(bots))}")
    bot = dict(bots[name])
    key_env = bot.get("api_key_env")
    if not key_env or not os.environ.get(key_env):
        raise EnvironmentError(f"bot '{name}' needs the environment variable {key_env} (see .env.example)")
    bot["api_key"] = os.environ[key_env]
    return bot


def resolve_scenario(config: dict, name: str) -> dict:
    scenarios = config.get("scenarios", {})
    if name not in scenarios:
        raise ValueError(f"unknown scenario '{name}'; available: {', '.join(sorted(scenarios))}")
    return scenarios[name]


async def run_skyvern(bot: dict, prompt: str, start_url: str, timeout: int) -> None:
    """Submit the task to a self-hosted Skyvern server and wait for the result."""
    from skyvern import Skyvern

    api_url = os.environ.get("SKYVERN_API_URL", bot.get("api_url", "http://localhost:8000"))
    task_url = start_url
    if bot.get("skyvern_docker", False):
        # A Skyvern server inside Docker reaches the host's honeypot via host.docker.internal.
        for host in ("127.0.0.1", "localhost"):
            task_url = task_url.replace(f"://{host}", "://host.docker.internal")
    print(f"[agent] engine   : skyvern ({api_url})")
    print(f"[agent] task url : {task_url}")

    client = Skyvern(base_url=api_url, api_key=bot["api_key"])
    try:
        result = await asyncio.wait_for(
            client.run_task(prompt=prompt, url=task_url, wait_for_completion=True), timeout=timeout)
    except asyncio.TimeoutError:
        sys.exit(f"[agent] skyvern run exceeded {timeout}s")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"[agent] skyvern run_task failed: {e}")

    status = getattr(result, "status", None)
    if status is None and isinstance(result, dict):
        status = result.get("status")
    print(f"[agent] result: {result}")
    if status != "completed":
        sys.exit(f"[agent] skyvern run did not complete (status={status})")


async def run_browser_use(bot: dict, prompt: str, upload_files: list[str], args) -> None:
    from browser_use import Agent, BrowserProfile, ChatOpenAI

    llm = ChatOpenAI(model=bot["model"], base_url=bot["base_url"], api_key=bot["api_key"],
                     add_schema_to_system_prompt=True)
    profile = {"headless": args.headless}
    if args.headless:
        profile["args"] = ["--no-sandbox", "--disable-dev-shm-usage"]
    executable_path = args.executable_path or bot.get("executable_path")
    if executable_path:
        profile["executable_path"] = executable_path

    agent_kwargs = dict(task=prompt, llm=llm, use_vision=bot.get("vision", True),
                        browser_profile=BrowserProfile(**profile), llm_timeout=bot.get("llm_timeout", 180))
    if upload_files:
        agent_kwargs["available_file_paths"] = upload_files

    history = await Agent(**agent_kwargs).run(max_steps=args.max_steps)
    print(f"[agent] result: {history.final_result()}")
    if not history.is_successful():
        sys.exit("[agent] agent did not complete the task")


def main():
    p = argparse.ArgumentParser(description="Run one browsing-agent session against the honeypot")
    p.add_argument("--bot", help="bot name from config.yaml")
    p.add_argument("--scenario", help="scenario name from config.yaml")
    p.add_argument("--version", help="capture token used in the URL (generated if omitted)")
    p.add_argument("--headless", action="store_true", help="run the browser headless (Browser Use only)")
    p.add_argument("--executable-path", help="Chromium executable to use (Browser Use only)")
    p.add_argument("--max-steps", type=int, default=50, help="Browser Use step limit (default: 50)")
    p.add_argument("--skyvern-timeout", type=int, default=540, help="seconds to wait for a Skyvern run")
    p.add_argument("--dry-run", action="store_true", help="print the resolved run and exit")
    p.add_argument("--list-bots", action="store_true")
    p.add_argument("--list-scenarios", action="store_true")
    args = p.parse_args()

    config = load_config()
    if args.list_bots:
        for name, cfg in config.get("bots", {}).items():
            print(f"  {name:20s} engine={cfg.get('engine', 'browser_use')}")
        return
    if args.list_scenarios:
        for name, cfg in config.get("scenarios", {}).items():
            print(f"  {name:16s} path={cfg['path']}")
        return
    if not args.bot or not args.scenario:
        p.error("--bot and --scenario are required")

    bot = resolve_bot(config, args.bot)
    scenario = resolve_scenario(config, args.scenario)
    version = args.version or generate_version(args.scenario)
    start_url = f"{os.environ.get('HONEYPOT_URL', 'http://127.0.0.1:8781')}/{version}{scenario['path']}"
    prompt = load_prompt(scenario["prompt_file"], start_url)
    upload_files = resolve_upload_files(scenario)
    engine = bot.get("engine", "browser_use")

    print(f"[agent] bot      : {args.bot} ({engine})")
    print(f"[agent] scenario : {args.scenario}")
    print(f"[agent] version  : {version}")
    print(f"[agent] start url: {start_url}")
    if upload_files:
        print(f"[agent] uploads  : {upload_files}")
    print(f"[agent] prompt   :\n{prompt}")
    if args.dry_run:
        return

    if engine == "skyvern":
        asyncio.run(run_skyvern(bot, prompt, start_url, args.skyvern_timeout))
    else:
        asyncio.run(run_browser_use(bot, prompt, upload_files, args))


if __name__ == "__main__":
    main()
