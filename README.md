# Browsing-Agent Honeypot

A small web site with six browser tasks, a passive tracker that records
mouse, keyboard, and scroll events, and a runner that sends LLM browsing
agents (Browser Use or Skyvern) to complete the tasks. It is the data
collection platform used in our study of behavioral fingerprinting of LLM
browsing agents.

The site, tracker, and server are adapted from the `honey_website` of the
FP-Agent project [1]. Our changes:

- **New tasks.** A job application with a resume upload (`careers`) and a
  sliding-tile puzzle (`game`).
- **Reworked task.** The drag-and-drop board (`sort`) now asks the agent to
  sort animal and tree names into two columns, Animals and Trees, instead of
  four open-ended columns (Natural, Man-Made, Both, Unclear).
- **Unchanged task logic.** The forum, flight-booking, and shopping tasks keep
  the original pages and scripts; only the styling changed.
- **Behavior only.** Browser fingerprinting (FingerprintJS/CreepJS) and its
  capture endpoint were removed; only behavioral events are recorded.
- **Server.** The server was rewritten to lock each capture file, so
  concurrent sessions cannot corrupt a line.

Please also cite FP-Agent if you use this platform.

## Layout

```
honeypot/
  server.py            static server + capture endpoint
  site/                single-page site (tasks, tracker in js/script.js)
agent/
  agent.py             runs one session
  run_batch.py         runs many sessions and writes captures/manifest.jsonl
  config.yaml          agents ("bots") and tasks ("scenarios")
  prompts/             task prompts
  assets/              placeholder resume for the careers task
patches/
  skyvern-1.0.56.patch makes Skyvern type every character (see below)
captures/              created at run time
```

## Tasks

| Scenario | Path | Task | Origin |
|---|---|---|---|
| `forums` | `/forums` | read a thread and post a typed summary as a reply | FP-Agent |
| `flight_booking` | `/flights` | four-page booking form with date picker and drop-downs | FP-Agent |
| `shopping` | `/shop` | search, filter by price, add three items, open the cart | FP-Agent |
| `careers` | `/careers` | fill in a job application and upload a resume | new |
| `sort` | `/sort` | unlock the board, drag 8 cards into Animals or Trees, save | reworked |
| `game` | `/game` | solve a 3×2 sliding-tile puzzle by clicking tiles | new |

The tasks exercise different input types: typing long text (`forums`),
multi-page forms with pickers and drop-downs (`flight_booking`), search and
filtering (`shopping`), file upload (`careers`), drag and drop (`sort`), and
repeated clicking under a goal state (`game`). Our study used `forums`,
`flight_booking`, `shopping`, and `careers`. All personal data in the prompts
(names, e-mail addresses, phone and card numbers) is fictional.

## Setup

Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then fill in the keys you need
```

Browser Use 0.13.1 drives a locally installed Chrome or Chromium through the
DevTools protocol; install one if none is present.

## Run

Start the honeypot:

```bash
python honeypot/server.py 8781 127.0.0.1
```

Every session uses its own token in the URL, `http://127.0.0.1:8781/<VERSION>/forums`.
Tokens match `[A-Z0-9_-]{1,32}`.

Run one session, or a batch:

```bash
cd agent
python agent.py --list-bots
python agent.py --bot openai_gpt --scenario forums --dry-run
python agent.py --bot openai_gpt --scenario forums
python run_batch.py --bots openai_gpt --scenarios forums,flight_booking,shopping --repeats 15 --parallel 4 --headless
```

`HONEYPOT_URL` (default `http://127.0.0.1:8781`) points the runner at another host.
Browser Use runs stop after 50 steps (`--max-steps`).

### Skyvern

Skyvern bots submit the task to a self-hosted Skyvern server (we used Skyvern
1.0.56). The LLM is configured on the Skyvern server, not in `config.yaml`, so
run one server per model and add one bot entry per server.

By default Skyvern fills many fields with a single `fill()` call, or types only
the last ten characters, so the page sees few or no key events. We patched it
to type every character:

```bash
pip install skyvern==1.0.56
cd "$(python -c 'import skyvern, os; print(os.path.dirname(os.path.dirname(skyvern.__file__)))')"
patch -p1 < /path/to/patches/skyvern-1.0.56.patch    # or: git apply /path/to/patches/skyvern-1.0.56.patch
```

The patch also replaces `os.path.exists(path=...)` with `os.path.exists(...)`
in the recording code, which fails on some Python versions.

If the Skyvern server runs in Docker, start the honeypot with bind address
`0.0.0.0` and set `skyvern_docker: true` for the bot, so that the task URL uses
`host.docker.internal`.

## Capture format

The tracker posts to `/<VERSION>/mm` every 500 ms (and when 50 events are
buffered or the page is hidden). The server appends one JSON line per request
to `captures/<VERSION>_mm.jsonl`:

```json
{"ts": "...", "remote": "127.0.0.1", "endpoint": "mm", "version": "<VERSION>",
 "ua": "...", "x_source": "eventFrames",
 "body": "{\"visitorId\": \"...\", \"sourcePage\": \"...\", \"eventFrames\": [...]}"}
```

`eventFrames` is a list of events; the last element is always the
`performance.now()` timestamp in milliseconds and the second is the CSS
selector of the target.

| Code | Event | Fields |
|---|---|---|
| `mm` | mouse move | selector, x, y, t |
| `md` / `mu` | button press / release | selector, button, x, y, t |
| `kd` / `ku` | key down / up | selector, key, repeat, t |
| `i` | input | selector, inputType, value, t |
| `c` | change | selector, value, [checked], t |
| `p` | paste | selector, text, t |
| `sc` / `se` | scroll / scroll end | target (`document` or selector), scrollX, scrollY, t |

When a task is finished, the page posts `{"webpage": "<task>"}` to
`/<VERSION>/end`, so `captures/<VERSION>_end.jsonl` exists only for completed
sessions. `run_batch.py` records each token with its bot, scenario, trial
number, exit status, and duration in `captures/manifest.jsonl`.

The tracker records the text typed into form fields: key events carry the key,
and input and change events carry the full field value. Do not expose the site
to people without changing this. `PRIVACY = true` in
`honeypot/site/js/script.js` masks printable keys in key events only.

## Authors

Daniel Perez Fiadzeawu and Jielun Zhang

IC3 Lab (https://labic3.org), School of Electrical Engineering & Computer Science,
University of North Dakota, Grand Forks, ND 58202, USA

## Reference

[1] E. Wang, Z. Shafiq, and Y. Vekaria, "FP-Agent: Fingerprinting AI browsing
agents," arXiv:2605.01247, 2026. Code: <https://github.com/ethanbwang/fp-agent>.
