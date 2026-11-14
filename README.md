# PromptGate AI

PromptGate AI is a research gateway that sorts prompts sent to an AI assistant into three
categories by looking at two things at once: **what the prompt says** and **how it was entered**
(typing rhythm, mouse movement, paste).

| Category | Meaning |
|---|---|
| **Allow** | An ordinary prompt entered by a person, with nothing sensitive in it. |
| **Shadow AI** | The prompt carries material that should not go to an outside AI service (customer or staff records, credentials, internal financials, contracts, unreleased code) or asks how to get around a company control. |
| **Automated AI Pipeline** | The prompt comes from software rather than a person: the text reads like a pipeline or template prompt, or the way it was entered looks automated. |

It is the data-collection and demonstration site for a University of North Dakota dissertation
project on Shadow AI (George Clemons; advisor Dr. Jielun Zhang). It is built on the IC3 Lab's
browsing-agent honeypot, which is kept in this repository and credited
[below](#the-original-browsing-agent-honeypot-ic3-lab).

## Status

**In place now**

- The site: a home page, a **Prompt Study** page and a **Live Detector** page, with a study login
  in front of the last two.
- A fixed pool of 160 prompts, and a participant workbook with each participant's link and 12
  assigned prompts.
- An agent driver that enters prompts into the site from a laptop.
- Two models, one for content and one for behavior, trained before any study data was collected,
  and a script that scores and retrains them once data has been collected.

**Planned, coming later**

- A security fix for the web server.
- An admin page with its own password, added to the menu, with drop-down menus where needed.
- A link in the admin menu to run the model update on the AWS server instead of a laptop.
- Admin controls to roll back model updates by date, or all the way back to the beginning.
- A prompt quantity that the user can select. Today every participant enters 12.
- A further update of this README when those changes are in.

## Contents

- [What the site has](#what-the-site-has)
- [Repository layout](#repository-layout)
- [Run it on your own computer](#run-it-on-your-own-computer)
- [Prompt Study page](#prompt-study-page)
- [Live Detector page](#live-detector-page)
- [Prompt pool: size and source](#prompt-pool-size-and-source)
- [Run the agents from a laptop](#run-the-agents-from-a-laptop)
- [What is recorded](#what-is-recorded)
- [Refine the models after collecting data](#refine-the-models-after-collecting-data)
- [The models](#the-models)
- [The server](#the-server)
- [Login and privacy](#login-and-privacy)
- [The original browsing-agent honeypot (IC3 Lab)](#the-original-browsing-agent-honeypot-ic3-lab)
- [Authors and credit](#authors-and-credit)

## What the site has

Every address starts with a link token: `https://<site>/<TOKEN>/<page>`. The token says who is
visiting. `P01` to `P20` are participant links, the agent driver uses tokens that start with `AG-`,
and anything else (for example `HOME`) is a test link. Tokens are 1 to 32 characters from `A-Z`,
`0-9`, `_` and `-`.

| Page | Address | Who can open it | What it does |
|---|---|---|---|
| Home | `/HOME/` | anyone | Two cards that lead to the study and the detector. |
| Prompt Study | `/<TOKEN>/gateway` | study login | A participant types 12 prompts from the prompt pool; each one is recorded with its typing and mouse behavior. |
| Live Detector | `/<TOKEN>/detector` | study login | Type or paste any prompt and see the category the gateway assigns, with the two parts of the decision shown separately. |

The top menu is: Prompt Study, Live Detector, Log out.

## Repository layout

```
honeypot/
  server_plus.py          the PromptGate web server (Python standard library only)
  inference.py            scores both models in plain Python and applies the category rule
  behavioral_features.py  turns key and mouse events into behavior features
  models/                 the models the Live Detector uses (content_model.json, actor_model.json)
  server.py               the lab's original server (six-task honeypot only)
  site/                   the single-page site
    index.html, js/app.js, js/script.js (site-wide tracker), js/recorder.js (per-prompt recorder)
    pages/home.html, gateway.html, detector.html and js/pages/*.js
    pages/forums, flights, shop, careers, sort, game    the six original honeypot tasks
    prompt_bank.json      the prompt pool the study page reads
study/
  STUDY_GUIDE.md              step-by-step notes for collecting data and refining the models
  prompt_bank.json            the prompt pool (same file as honeypot/site/prompt_bank.json)
  PromptGate_prompt_sheet.xlsx  participant workbook: links, assigned prompts, progress
  sim_gateway.py              agent driver (run on a laptop)
  refine_models.py            scores the models on collected data and retrains them (run on a laptop)
  train_and_export.py         trains both models and writes them as JSON
  inference.py, behavioral_features.py, models/    copies used by the study scripts
  protect_site.sh             sets, changes or removes the study login
  sim_sessions.py, results/   scripted sessions and their features (training data of the behavior model)
agent/, patches/              the lab's LLM browsing-agent runner and Skyvern patch
captures/                     collected data, created at run time (never committed)
```

## Run it on your own computer

Needs Python 3.11 or newer. The web server uses only the standard library.

```bash
git clone https://github.com/gvoid404/faylynx.git
cd faylynx
python3 honeypot/server_plus.py 8781 127.0.0.1
```

Open <http://127.0.0.1:8781/HOME/>. There is no study login on a local copy; that login is added
by the web front end on the server (see [The server](#the-server)).

## Prompt Study page

1. The participant opens their link, for example `https://<site>/P07/gateway`, and signs in with
   the study username and password.
2. The consent card explains what is recorded. The participant ticks the box and presses Start.
3. Each of the 12 prompts is shown on screen. The participant types it by hand. Shadow AI prompts
   also come with made-up data to paste in after the typed part. Send, then Next.
4. On a participant link, reloading the page continues where the participant left off.

Participants `P01` to `P20` get their 12 assigned prompts: 6 Allow and 6 Shadow AI, alternating.
Every Allow and Shadow AI prompt is assigned to exactly 2 people. Any other link token gets a
random 6 Allow and 6 Shadow AI prompts.

`study/PromptGate_prompt_sheet.xlsx` lists each participant's link and assigned prompts and tracks
progress.

## Live Detector page

Enter any prompt and press Analyze. The page shows the gateway category, the content result with
its three probabilities, and the behavior result (person or automated) with the features behind
it. Three buttons let the visitor say what the prompt really was. Every use is recorded.

The category rule, applied in this order:

1. Content model says Shadow AI: **Shadow AI**.
2. Content model says Automated, or the behavior model says automated: **Automated AI Pipeline**.
3. Otherwise: **Allow**.

## Prompt pool: size and source

The pool (`bank_v1`, in `study/prompt_bank.json`) holds **160 prompts**. People type the 120 Allow
and Shadow AI prompts; agents enter all 160.

| Category | In the pool | Passed screening | In the source | Source |
|---|---:|---:|---:|---|
| Allow | 60 | 169 | 779 | Human gold set of this project: real user prompts labeled by hand. 403 are from WildChat, 376 from LMSYS-Chat-1M. |
| Shadow AI | 60 | 337 | 600 | Synthetic Shadow set: ordinary prompts with a made-up sensitive payload added. No real data. |
| Automated | 40 | 60 | 5,309 | The human gold set first (160 prompts), then the project's WildChat-4.8M sample labeled by an LLM judge (5,149 of its 10,776 labeled prompts: those marked Automated with confidence of at least 0.9 and not flagged toxic). |
| Total | 160 | 566 | 6,688 | |

How they were chosen:

- **Allow**: 40 to 130 characters, one line, plain ASCII, and a keyword screen for unsuitable
  content left 169; 70 were picked by hand and the first 60 are in the pool. By origin: 39
  WildChat, 21 LMSYS-Chat-1M.
- **Shadow AI**: a short instruction plus a payload of at most 900 characters, and the 5 distinct
  control-bypass requests, left 337. The pool takes them in turn across the six payload kinds: 11
  each of customer and staff records, credentials, internal financials, contracts and proprietary
  code, and the 5 control-bypass requests.
- **Automated**: 40 to 1,200 characters, plain ASCII and the keyword screen, with duplicates and 4
  items that looked mislabeled removed, left 60 prompts from 33 distinct templates. The pool takes
  every template once, then second and third fills of repeated templates. By origin: 10 WildChat
  and 16 LMSYS-Chat-1M (both from the gold set), 14 WildChat-4.8M.

The 160 pool prompts were held out when the content model was trained.

Dataset licenses: WildChat is released under ODC-BY 1.0; LMSYS-Chat-1M under the LMSYS-Chat-1M
Dataset License Agreement. Check each license before reusing the prompts. The Shadow AI prompts
were generated for this project.

## Run the agents from a laptop

The agent driver opens a real Chromium browser on your computer and enters prompts into the site
the way an automated tool would. It runs on a laptop, not on the server. The commands below are
for Windows PowerShell and need Python 3.11 or newer and Git. If `python` is not found, use `py`.

One-time setup:

```powershell
git clone https://github.com/gvoid404/faylynx.git
cd faylynx\study
python -m pip install playwright
python -m playwright install chromium
```

Before each run, get the latest version:

```powershell
cd faylynx
git pull
cd study
```

Try 6 sessions first, then the full run:

```powershell
python sim_gateway.py --base https://YOUR-SITE --user YOUR-STUDY-USERNAME --limit 6
python sim_gateway.py --base https://YOUR-SITE --user YOUR-STUDY-USERNAME
```

The driver asks for the study password when it starts. The password is never typed on the command
line. (For unattended runs it can be read from the `PROMPTGATE_PASSWORD` environment variable.)
Leave out `--user` if the site has no study login.

Each session prints one line that says `ok` or `error`. If the first sessions all say `error`,
the username or password is probably wrong: stop with Ctrl+C and start again.

The full run is 240 sessions and takes about an hour. Leave the window open. `--limit N` runs only
N sessions.

What it sends: each of the 40 Automated prompts under three agent styles (120 sessions), plus each
of the 120 Allow and Shadow AI prompts once (120 sessions), so that prompt category and typist are
not tied together.

| Agent style | How it enters the prompt |
|---|---|
| `fill_bot` | fills the box in one step: no typing, no mouse path |
| `type_bot` | types every character at a fast, even pace |
| `evasive_bot` | types with random variation and moves the mouse, trying to look like a person |

Each session is also listed in `agent_manifest.jsonl` in the folder the driver was started from.

## What is recorded

Everything is written on the server as JSON Lines files in `captures/`, one line per request, one
set of files per link token:

| File | One line per | Holds |
|---|---|---|
| `<TOKEN>_prompt.jsonl` | prompt sent | entered text, prompt id and category, the key and mouse events for that prompt, time taken |
| `<TOKEN>_consent.jsonl` | consent click | time |
| `<TOKEN>_classify.jsonl` | Live Detector use | prompt, events, and the answer the models gave |
| `<TOKEN>_feedback.jsonl` | detector feedback click | what the visitor said the prompt really was |
| `<TOKEN>_end.jsonl` | finished session | which page was completed |
| `<TOKEN>_mm.jsonl` | half-second batch | the site-wide event stream (backup) |

Every line also holds the time, the client address and a light network fingerprint: User-Agent,
Accept headers, Client Hints, and the TLS version and cipher passed on by the web front end.

Copy the data to a laptop for analysis or backup:

```powershell
scp -r -i YOUR-KEY ubuntu@YOUR-SERVER:browsing-agent-honeypot/captures captures_live
```

## Refine the models after collecting data

For now this is done on a laptop. It needs the project's labeled data folder
(`paper2-three-class`), which is not in this repository because it contains third-party dataset
text. Work in the `study` folder: copy the captures into it with the command above, then run:

```powershell
python -m pip install scikit-learn xgboost pandas
python refine_models.py --captures captures_live --p2 PATH\paper2-three-class --out new_models
scp -i YOUR-KEY new_models\content_model.json new_models\actor_model.json ubuntu@YOUR-SERVER:browsing-agent-honeypot/honeypot/models/
```

`refine_models.py`:

1. scores the current models on everything participants and agents have entered,
2. estimates how the retrained models will do, with participants held out for the behavior model
   and prompts held out for the content model,
3. retrains on all of it and writes the two model files, plus `refine_report.json`.

The Live Detector picks up the new model files on its own; no restart is needed. Keep a copy of
the two files in `honeypot/models/` before replacing them, so that an update can be undone.

## The models

Both models are stored as JSON and scored in plain Python (`honeypot/inference.py`), so the server
needs no machine-learning libraries to run the detector.

**Content model.** TF-IDF on words and word pairs (30,000 terms) with logistic regression, three
classes. It was trained on 11,732 labeled prompts: 5,978 Allow, 5,152 Automated, 602 Shadow AI.
Five-fold cross-validated macro-F1 is 0.946. On the 160 held-out pool prompts it gets Allow 60 of
60, Shadow AI 60 of 60 and Automated 9 of 40.

**Behavior model.** Gradient-boosted trees (XGBoost, 200 trees) on seven features: variation in the
time between keys, variation in key hold time, straightness of mouse paths, share of text that
appeared without key presses, paste-to-typing ratio, and whether there was any mouse movement or
any typing. It was trained on 324 scripted browser sessions (186 agent, 138 human-like);
five-fold cross-validated accuracy is 0.929.

### Known limits

- **No real people yet in the behavior model.** Its "human" sessions are a scripted stand-in
  (curved mouse paths, uneven typing, pauses, typos). How well it separates real people from agents
  is what the pilot is for.
- **The content model is weak on Automated prompts it has not seen**: 9 of 40 on the held-out
  pool. The gateway leans on the behavior path for that category. The cross-validation score is
  flattering because the training data contains many near-identical pipeline templates.
- **The Shadow AI score is optimistic.** The pool's Shadow AI prompts come from the same generator
  as the Shadow AI training data.

## The server

The live site runs on one Ubuntu 24.04 server: the Python server listens on `127.0.0.1:8781` as a
systemd service called `honeypot`, and Caddy in front of it provides HTTPS and the study login.
The repository is in `~/browsing-agent-honeypot` on the server.

Update the server after a change in this repository:

```bash
cd ~/browsing-agent-honeypot && git pull --ff-only && sudo systemctl restart honeypot && systemctl is-active honeypot
```

It should print `active`. Collected data is in `captures/`, which `git pull` does not touch.

The service definition (`/etc/systemd/system/honeypot.service`):

```ini
[Unit]
Description=PromptGate AI
After=network.target
[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/browsing-agent-honeypot
ExecStart=/usr/bin/python3 /home/ubuntu/browsing-agent-honeypot/honeypot/server_plus.py 8781 127.0.0.1
Restart=always
[Install]
WantedBy=multi-user.target
```

The Caddy configuration (`/etc/caddy/Caddyfile`), before the study login is added:

```
your.host.name {
    encode gzip
    redir / /HOME/ 302
    reverse_proxy 127.0.0.1:8781 {
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
        header_up X-TLS-Version {http.request.tls.version}
        header_up X-TLS-Cipher {http.request.tls.cipher_suite}
    }
}
```

## Login and privacy

- **Study login.** The Prompt Study and Live Detector pages, the prompt pool file and the
  addresses they send data to need a username and password. The home page is open. Set or change
  the login on the server with `bash study/protect_site.sh`; `bash study/protect_site.sh --remove`
  takes it off. The Log out link in the menu makes the browser forget the login.
- **What is recorded.** The site records what visitors type on the study and detector pages, their
  typing and mouse behavior, and their network address. The study page shows a consent notice
  first, uses only made-up sensitive data, and asks participants not to enter real personal or
  confidential information. Do not invite participants before the approvals your institution
  requires are in place.
- **Keep the data private.** `captures/` is listed in `.gitignore`. Keep it, and the project's
  labeled data, out of any public place.

## The original browsing-agent honeypot (IC3 Lab)

PromptGate AI is built on the browsing-agent honeypot by Daniel Perez Fiadzeawu and Jielun Zhang
(IC3 Lab, University of North Dakota): a small web site with six browser tasks, a passive tracker
that records mouse, keyboard and scroll events, and a runner that sends LLM browsing agents
(Browser Use or Skyvern) to complete the tasks. It is the data-collection platform of the lab's
study of behavioral fingerprinting of LLM browsing agents. All of it is still in this repository
and still works; the six task pages are served but no longer linked from the menu.

The site, tracker and server of that honeypot are adapted from the `honey_website` of the FP-Agent
project [1]. The lab's changes to FP-Agent:

- **New tasks.** A job application with a resume upload (`careers`) and a sliding-tile puzzle (`game`).
- **Reworked task.** The drag-and-drop board (`sort`) asks the agent to sort animal and tree names
  into two columns, Animals and Trees, instead of four open-ended columns.
- **Unchanged task logic.** The forum, flight-booking and shopping tasks keep the original pages
  and scripts; only the styling changed.
- **Behavior only.** Browser fingerprinting (FingerprintJS/CreepJS) and its capture endpoint were
  removed; only behavioral events are recorded.
- **Server.** The server was rewritten to lock each capture file, so concurrent sessions cannot
  corrupt a line.

Please also cite FP-Agent if you use this platform.

### Tasks

| Scenario | Path | Task | Origin |
|---|---|---|---|
| `forums` | `/forums` | read a thread and post a typed summary as a reply | FP-Agent |
| `flight_booking` | `/flights` | four-page booking form with date picker and drop-downs | FP-Agent |
| `shopping` | `/shop` | search, filter by price, add three items, open the cart | FP-Agent |
| `careers` | `/careers` | fill in a job application and upload a resume | new |
| `sort` | `/sort` | unlock the board, drag 8 cards into Animals or Trees, save | reworked |
| `game` | `/game` | solve a 3×2 sliding-tile puzzle by clicking tiles | new |

The tasks exercise different input types: typing long text (`forums`), multi-page forms with
pickers and drop-downs (`flight_booking`), search and filtering (`shopping`), file upload
(`careers`), drag and drop (`sort`), and repeated clicking under a goal state (`game`). The lab's
study used `forums`, `flight_booking`, `shopping` and `careers`. All personal data in the task
prompts (names, e-mail addresses, phone and card numbers) is fictional.

### Running LLM agents on the six tasks

Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Put the API keys the agents need in a `.env` file in the repository root; `agent/config.yaml` names
the variable each agent reads (for example `OPENAI_API_KEY`). Browser Use 0.13.1 drives a locally
installed Chrome or Chromium through the DevTools protocol; install one if none is present.

Start either server (`honeypot/server.py` is the lab's original, `honeypot/server_plus.py` adds
the PromptGate pages), then run one session or a batch:

```bash
python honeypot/server.py 8781 127.0.0.1

cd agent
python agent.py --list-bots
python agent.py --bot openai_gpt --scenario forums --dry-run
python agent.py --bot openai_gpt --scenario forums
python run_batch.py --bots openai_gpt --scenarios forums,flight_booking,shopping --repeats 15 --parallel 4 --headless
```

Every session uses its own token in the address, `http://127.0.0.1:8781/<TOKEN>/forums`.
`HONEYPOT_URL` (default `http://127.0.0.1:8781`) points the runner at another host. Browser Use
runs stop after 50 steps (`--max-steps`).

**Skyvern.** Skyvern bots submit the task to a self-hosted Skyvern server (the lab used Skyvern
1.0.56). The LLM is configured on the Skyvern server, not in `config.yaml`, so run one server per
model and add one bot entry per server. By default Skyvern fills many fields with a single
`fill()` call, or types only the last ten characters, so the page sees few or no key events. The
lab's patch makes it type every character:

```bash
pip install skyvern==1.0.56
cd "$(python -c 'import skyvern, os; print(os.path.dirname(os.path.dirname(skyvern.__file__)))')"
patch -p1 < /path/to/patches/skyvern-1.0.56.patch    # or: git apply /path/to/patches/skyvern-1.0.56.patch
```

The patch also replaces `os.path.exists(path=...)` with `os.path.exists(...)` in the recording
code, which fails on some Python versions. If the Skyvern server runs in Docker, start the
honeypot with bind address `0.0.0.0` and set `skyvern_docker: true` for the bot, so that the task
URL uses `host.docker.internal`.

### Tracker format

The site-wide tracker posts to `/<TOKEN>/mm` every 500 ms (and when 50 events are buffered or the
page is hidden). The server appends one JSON line per request to `captures/<TOKEN>_mm.jsonl`:

```json
{"ts": "...", "remote": "127.0.0.1", "endpoint": "mm", "version": "<TOKEN>",
 "ua": "...", "x_source": "eventFrames",
 "body": "{\"visitorId\": \"...\", \"sourcePage\": \"...\", \"eventFrames\": [...]}"}
```

`eventFrames` is a list of events; the last element is always the `performance.now()` timestamp
in milliseconds and the second is the CSS selector of the target.

| Code | Event | Fields |
|---|---|---|
| `mm` | mouse move | selector, x, y, t |
| `md` / `mu` | button press / release | selector, button, x, y, t |
| `kd` / `ku` | key down / up | selector, key, repeat, t |
| `i` | input | selector, inputType, value, t |
| `c` | change | selector, value, [checked], t |
| `p` | paste | selector, text, t |
| `sc` / `se` | scroll / scroll end | target (`document` or selector), scrollX, scrollY, t |

When a task is finished, the page posts `{"webpage": "<task>"}` to `/<TOKEN>/end`, so
`captures/<TOKEN>_end.jsonl` exists only for completed sessions. `run_batch.py` records each token
with its bot, scenario, trial number, exit status and duration in `captures/manifest.jsonl`.

The tracker records the text typed into form fields: key events carry the key, and input and
change events carry the full field value. Do not expose the site to people without changing this.
`PRIVACY = true` in `honeypot/site/js/script.js` masks printable keys in key events only.

## Authors and credit

PromptGate AI: George Clemons, PhD student in computer science, University of North Dakota.
Advisor: Dr. Jielun Zhang.

Browsing-agent honeypot: Daniel Perez Fiadzeawu and Jielun Zhang, IC3 Lab (<https://labic3.org>),
School of Electrical Engineering & Computer Science, University of North Dakota, Grand Forks,
ND 58202, USA.

Prompt sources: WildChat (Allen Institute for AI) and LMSYS-Chat-1M (LMSYS Org).

## Reference

[1] E. Wang, Z. Shafiq, and Y. Vekaria, "FP-Agent: Fingerprinting AI browsing agents,"
arXiv:2605.01247, 2026. Code: <https://github.com/ethanbwang/fp-agent>.
