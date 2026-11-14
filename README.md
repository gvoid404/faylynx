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
browsing-agent honeypot, which is kept in this repository and credited [below](#the-original-browsing-agent-honeypot-ic3-lab).

The models shipped here were trained before any study data was collected: the content model on
public and synthetic prompts, the behavior model on scripted browser sessions. See
[Known limits](#known-limits).

## Contents

- [What the site has](#what-the-site-has)
- [Repository layout](#repository-layout)
- [Run it on your own computer](#run-it-on-your-own-computer)
- [Prompt Study page](#prompt-study-page)
- [Live Detector page](#live-detector-page)
- [Admin page](#admin-page)
- [Prompt pool: size and source](#prompt-pool-size-and-source)
- [Run the agents from a laptop](#run-the-agents-from-a-laptop)
- [What is recorded](#what-is-recorded)
- [The models](#the-models)
- [Server setup and updates](#server-setup-and-updates)
- [Logins and privacy](#logins-and-privacy)
- [Rebuilding the prompt bank and the models](#rebuilding-the-prompt-bank-and-the-models)
- [The original browsing-agent honeypot (IC3 Lab)](#the-original-browsing-agent-honeypot-ic3-lab)
- [Change log](#change-log)
- [Authors and credit](#authors-and-credit)

## What the site has

Every address starts with a link token: `https://<site>/<TOKEN>/<page>`. The token says who is
visiting. `P01` to `P20` are participant links, the agent driver uses tokens that start with `AG-`,
and anything else (for example `HOME`) is counted as a test link. Tokens are 1 to 32 characters
from `A-Z`, `0-9`, `_` and `-`.

| Page | Address | Who can open it | What it does |
|---|---|---|---|
| Home | `/HOME/` | anyone | Two cards that lead to the study and the detector. |
| Prompt Study | `/<TOKEN>/gateway` | study login | A participant types prompts from the prompt bank; each one is recorded with its typing and mouse behavior. |
| Live Detector | `/<TOKEN>/detector` | study login | Type or paste any prompt and see the category the gateway assigns, with the two parts of the decision shown separately. |
| Admin | `/<TOKEN>/admin` | admin password | Collected-data overview, model updates run on the server, model rollback, prompt pool and quantity settings, agent instructions. |

The top menu is: Prompt Study, Live Detector, Admin (a drop-down with Overview, Update models,
Roll back models, Prompt pool and quantity, Run the agents) and Log out.

## Repository layout

```
honeypot/
  server_plus.py          the PromptGate web server (Python standard library only)
  admin.py                admin back end: password, sign-in, overview, model-update job, settings
  model_registry.py       model versions: store, activate, roll back
  inference.py            scores both models in plain Python and applies the category rule
  behavioral_features.py  turns key and mouse events into behavior features
  models/                 the original models (content_model.json, actor_model.json)
  prompt_pool.json        pool sizes and sources shown on the Admin page
  server.py               the lab's original server (six-task honeypot only)
  site/                   the single-page site
    index.html, js/app.js, js/script.js (site-wide tracker), js/recorder.js (per-prompt recorder)
    pages/gateway.html, detector.html, admin.html and js/pages/*.js
    pages/forums, flights, shop, careers, sort, game    the six original honeypot tasks
    prompt_bank.json      the prompt bank the study page reads
study/
  prompt_bank.json            the prompt bank (same file as honeypot/site/prompt_bank.json)
  PromptGate_prompt_sheet.xlsx  participant workbook: links, assigned prompts, progress
  sim_gateway.py              agent driver (run on a laptop)
  refine_models.py            scores the models on collected data and retrains them (run by Admin)
  train_and_export.py         trains both models and writes them as JSON
  build_prompt_bank.py        rebuilds the prompt bank and prompt_pool.json
  build_prompt_sheet.py       rebuilds the participant workbook
  build_base_corpus.py        packs the private training corpus
  server_setup_training.sh    one-time install of the training tools on the server
  protect_site.sh             sets, changes or removes the study login
  sim_sessions.py, results/   scripted sessions and their features (first behavior model)
agent/, patches/              the lab's LLM browsing-agent runner and Skyvern patch
captures/                     collected data, created at run time (never committed)
runtime/                      server-local state, created at run time (never committed):
                              admin password hash, settings, model versions, training tools,
                              private training corpus
```

## Run it on your own computer

Needs Python 3.11 or newer. The web server uses only the standard library.

```bash
git clone https://github.com/gvoid404/faylynx.git
cd faylynx
python3 honeypot/server_plus.py 8781 127.0.0.1
```

Open <http://127.0.0.1:8781/HOME/>. To use the Admin page, set its password first:

```bash
python3 honeypot/admin.py set-password
```

There is no study login on a local copy; that login is added by the web front end on the server
(see [Server setup and updates](#server-setup-and-updates)).

## Prompt Study page

1. The participant opens their link, for example `https://<site>/P07/gateway`, and signs in with
   the study username and password.
2. The consent card explains what is recorded. The participant ticks the box, chooses how many
   prompts to enter, and presses Start.
3. Each prompt is shown on screen. The participant types it by hand. Shadow AI prompts also come
   with made-up data to paste in after the typed part. Send, then Next.
4. On a participant link (`P01` to `P20`), reloading the page continues where the participant left off.

**How many prompts.** The quantity is selectable in two places:

- The participant picks a number on the consent card (when the admin allows it).
- The admin sets the default, the fewest and the most on **Admin > Prompt pool and quantity**, and
  can turn the participant's choice off. The shipped settings are default 12, fewest 2, most 40.
  The most can be at most 120, the number of Allow and Shadow AI prompts in the pool.

Participants `P01` to `P20` always start with their 12 assigned prompts (6 Allow and 6 Shadow AI,
alternating; every prompt is assigned to exactly 2 people). A larger number continues with more
prompts from the pool in an order that is fixed for that participant; a smaller number stops
early. Any other link token gets a random draw.

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

## Admin page

The Admin page has its own password, separate from the study login.

**Set or change the admin password** on the server (it is never set over the web):

```bash
cd ~/browsing-agent-honeypot && python3 honeypot/admin.py set-password
```

The password needs at least 8 characters. Changing it signs everyone out of the Admin page. Five
wrong passwords lock sign-in from that address for 15 minutes. A sign-in lasts 8 hours, and the
Log out link in the menu ends it.

### Overview

Counts of participants with entries, prompts entered by people and by agents, Live Detector uses
and feedback clicks, entries from test links, a per-participant table, and which models are in use.

### Update models

**Admin > Update models > Run model update** runs the update on the server. Nothing has to be
copied to or from a laptop. The job:

1. scores the models now in use on everything participants and agents have entered,
2. estimates how the retrained models will do, with participants held out for the behavior model
   and prompts held out for the content model,
3. retrains on all of it and stores the result as a new version.

With the box "Use the new version as soon as it finishes" ticked, the Live Detector switches to the
new version at once. Without it, the version is stored and can be switched on later. The page
shows a before and after table and keeps the earlier versions. An update needs at least 20 usable
entries; with fewer it stops and says so.

One-time setup on the server (about 5 minutes, needs about 1.5 GB of free disk space):

```bash
cd ~/browsing-agent-honeypot && bash study/server_setup_training.sh
```

This installs scikit-learn, pandas and xgboost into `runtime/venv`, apart from the system Python.

Until the private training corpus is on the server, an update retrains the **behavior model
only** and carries the content model over. To retrain the content model as well, copy the corpus
to the server once:

```powershell
scp -i YOUR-KEY base_corpus.jsonl.gz ubuntu@YOUR-SERVER:browsing-agent-honeypot/runtime/
```

The Admin page says which of the two cases applies before you press the button. The corpus holds
third-party dataset text and must stay out of this repository (`.gitignore` blocks it).

### Roll back models

**Admin > Roll back models** offers three ways back, each with a second click to confirm:

- **Roll back to this date**: pick a day; the newest version made on or before that day is used.
  If no update is that old, the original models are used.
- **Restore the original models**: all the way back to the models shipped in this repository.
- **Use this version**: on any row of the version table.

A rollback takes effect on the next request. Nothing is deleted, so any version can be switched on
again, and the page keeps a list of recent changes. The same from the command line on the server:

```bash
python3 honeypot/model_registry.py list
python3 honeypot/model_registry.py rollback-to 2026-11-20
python3 honeypot/model_registry.py activate baseline
python3 honeypot/model_registry.py activate 20261120-153000
```

Versions are stored in `runtime/models/versions/<date-time>/`; `git pull` never touches them. A
version's name is the date and time it was made in UTC, so late in the day it can show the next
day's date; the Admin page shows local times.

### Prompt pool and quantity

The quantity settings described [above](#prompt-study-page), the size and source of the prompt
pool, and how many pool prompts people and agents have entered so far.

### Run the agents

The laptop instructions [below](#run-the-agents-from-a-laptop), with the commands filled in for
the site you are on.

## Prompt pool: size and source

The pool (`bank_v1`, in `study/prompt_bank.json`) holds **160 prompts**. People draw from the 120
Allow and Shadow AI prompts; agents enter all 160.

| Category | In the pool | Passed screening | In the source | Source |
|---|---:|---:|---:|---|
| Allow | 60 | 169 | 779 | Human gold set of this project (`human_gold_v1`): real user prompts labeled by hand. 403 are from WildChat, 376 from LMSYS-Chat-1M. |
| Shadow AI | 60 | 337 | 600 | Synthetic Shadow set (`synthetic_shadow_v1`): ordinary prompts with a made-up sensitive payload added. No real data. |
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

The 160 pool prompts were held out when the original content model was trained.

**Licenses.** WildChat is released under ODC-BY 1.0, which asks for attribution (checked on the
WildChat-1M dataset card; the WildChat-4.8M card still needs checking). The LMSYS-Chat-1M Dataset
License Agreement does not allow the data to be distributed or hosted. 37 pool prompts (21 Allow,
16 Automated) come from LMSYS-Chat-1M; replacing them with WildChat prompts is an open item. The
Shadow AI prompts were generated for this project.

The same numbers are on **Admin > Prompt pool and quantity** and in `honeypot/prompt_pool.json`.
`study/build_prompt_bank.py` rebuilds both files from the project data.

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
Leave out `--user` if the site has no study login. If the login is refused, the driver stops at
once and says so.

The full run is 240 sessions and takes about an hour. Leave the window open.

| Option | Effect |
|---|---|
| `--limit 40` | run 40 sessions |
| `--classes automated` | only one category; any of `allow`, `shadow`, `automated`, separated by commas |
| `--manifest FILE` | where the list of sessions is written (default `agent_manifest.jsonl`) |
| `--seed N` | a different random order |

What it sends: each of the 40 Automated prompts under three agent styles (120 sessions), plus each
of the 120 Allow and Shadow AI prompts once (120 sessions), so that prompt category and typist are
not tied together.

| Agent style | How it enters the prompt |
|---|---|
| `fill_bot` | fills the box in one step: no typing, no mouse path |
| `type_bot` | types every character at a fast, even pace |
| `evasive_bot` | types with random variation and moves the mouse, trying to look like a person |

Afterwards each session is listed in `agent_manifest.jsonl`, the entries show up on
**Admin > Overview**, and **Admin > Update models** can use them.

## What is recorded

Everything is written on the server as JSON Lines files in `captures/`, one line per request, one
set of files per link token:

| File | One line per | Holds |
|---|---|---|
| `<TOKEN>_prompt.jsonl` | prompt sent | entered text, prompt id and category, the key and mouse events for that prompt, chosen quantity, time taken |
| `<TOKEN>_consent.jsonl` | consent click | time, chosen quantity |
| `<TOKEN>_classify.jsonl` | Live Detector use | prompt, events, and the answer the models gave (with the model version) |
| `<TOKEN>_feedback.jsonl` | detector feedback click | what the visitor said the prompt really was |
| `<TOKEN>_end.jsonl` | finished session | which page was completed |
| `<TOKEN>_mm.jsonl` | half-second batch | the site-wide event stream (backup) |

Every line also holds the time, the client address and a light network fingerprint: User-Agent,
Accept headers, Client Hints, and the TLS version and cipher passed on by the web front end.

Copy the data to a laptop for analysis or backup:

```powershell
scp -r -i YOUR-KEY ubuntu@YOUR-SERVER:browsing-agent-honeypot/captures captures_live
```

## The models

Both models are stored as JSON and scored in plain Python (`honeypot/inference.py`), so the server
needs no machine-learning libraries to run the detector. The plain-Python scores match the
training libraries (largest probability difference 0.00002 for the content model on 760 prompts,
0.0000001 for the behavior model on 324 sessions).

**Content model.** TF-IDF on words and word pairs (30,000 terms) with logistic regression, three
classes. The original model (`v4`) was trained on 11,309 labeled prompts: 5,666 Allow, 5,073
Automated, 570 Shadow AI. Five-fold cross-validated macro-F1 is 0.947. On the 160 held-out pool
prompts it gets Allow 60 of 60, Shadow AI 60 of 60 and Automated 10 of 40.

**Behavior model.** Gradient-boosted trees (XGBoost, 200 trees) on seven features: variation in the
time between keys, variation in key hold time, straightness of mouse paths, share of text that
appeared without key presses, paste-to-typing ratio, and whether there was any mouse movement or
any typing. It was trained on 324 scripted browser sessions (186 agent, 138 human-like);
five-fold cross-validated accuracy is 0.929.

### Known limits

- **No real people yet in the behavior model.** Its "human" sessions are a scripted stand-in
  (curved mouse paths, uneven typing, pauses, typos). How well it separates real people from agents
  is exactly what the pilot is for.
- **The content model is weak on Automated prompts it has not seen**: 10 of 40 on the held-out
  pool. The gateway leans on the behavior path for that category. The cross-validation score is
  flattering because the training data contains many near-identical pipeline templates.
- **The Shadow AI score is optimistic.** The pool's Shadow AI prompts come from the same generator
  as the Shadow AI training data.
- **37 pool prompts are from LMSYS-Chat-1M**; replacing them is an open item (see Licenses above).

## Server setup and updates

The live site runs on one Ubuntu 24.04 server: the Python server listens on `127.0.0.1:8781`
as a systemd service, and Caddy in front of it provides HTTPS and the study login. The commands in
this README assume the repository is in `~/browsing-agent-honeypot` and the service is called
`honeypot`.

**Update a running server** after a change in this repository:

```bash
cd ~/browsing-agent-honeypot && git pull --ff-only && sudo systemctl restart honeypot && systemctl is-active honeypot
```

It should print `active`. Restarting signs admins out and stops a model update that is running.
Collected data, model versions, settings and passwords are in `captures/` and `runtime/`, which
`git pull` does not touch.

**Set up a new server:**

1. Install the tools and get the code:

   ```bash
   sudo apt-get update && sudo apt-get install -y python3 git caddy
   git clone https://github.com/gvoid404/faylynx.git ~/browsing-agent-honeypot
   ```

2. Create `/etc/systemd/system/honeypot.service`:

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

   then `sudo systemctl daemon-reload && sudo systemctl enable --now honeypot`.

3. Put this in `/etc/caddy/Caddyfile` (with your own host name) and run `sudo systemctl reload caddy`:

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

4. Set the study login, the admin password and the training tools:

   ```bash
   cd ~/browsing-agent-honeypot
   bash study/protect_site.sh
   python3 honeypot/admin.py set-password
   bash study/server_setup_training.sh
   ```

Open ports 80 and 443 to everyone, and port 22 only to the addresses you connect from.

## Logins and privacy

| What | Protected by |
|---|---|
| Home page | open |
| Prompt Study and Live Detector pages, the prompt bank file, and the addresses they send data to | study login (HTTP Basic, added by Caddy; `bash study/protect_site.sh` sets or changes it, `--remove` takes it off) |
| Admin page data and actions | admin password (`python3 honeypot/admin.py set-password`) |
| Collected data in `captures/` | not reachable through the web server at all; read it over SSH |

- The admin password is stored only as a salted PBKDF2-SHA256 hash in `runtime/admin_auth.json`.
  Admin requests are not written to the capture files.
- The web server only serves files inside `honeypot/site/`, and the addresses that accept data are
  single plain words.
- The site records what visitors type on the study and detector pages, their typing and mouse
  behavior, and their network address. The study page shows a consent notice first, uses only
  made-up sensitive data, and asks participants not to enter real personal or confidential
  information. Do not invite participants before the approvals your institution requires are in
  place.
- `captures/` and `runtime/` are listed in `.gitignore`. Keep them, and the training corpus, out
  of any public place.

## Rebuilding the prompt bank and the models

These steps need the project's labeled data folder (`paper2-three-class`), which is not in this
repository because it contains third-party dataset text.

```bash
cd study
python build_prompt_bank.py  --p2 PATH/paper2-three-class      # prompt_bank.json + prompt_pool.json
python build_prompt_sheet.py                                   # participant workbook
python build_base_corpus.py  --p2 PATH/paper2-three-class      # base_corpus.jsonl.gz (private)
python train_and_export.py   --corpus base_corpus.jsonl.gz --out ../honeypot/models --tag v4   # the original models
```

`build_prompt_bank.py` reproduces the published bank exactly. `train_and_export.py` holds the 160
pool prompts out of content training unless `--include-bank` is given.

**Test sets that stay out of training.** `build_base_corpus.py` leaves out the sealed Shadow test
rows of the gold set, the 400 prompts of the sealed human-audit holdout, 22 near-duplicates of
those prompts, and 32 synthetic Shadow rows that were built on them. It reads only prompt ids from
the sealed key. No pool prompt contains or closely matches a holdout prompt, so models updated
from collected data stay clear of the holdout as well.

`refine_models.py` can also be run by hand:

```bash
python refine_models.py --captures ../captures --corpus ../runtime/base_corpus.jsonl.gz --out new_models
python ../honeypot/model_registry.py import new_models/content_model.json new_models/actor_model.json "note"
```

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
  into two columns instead of four open-ended ones.
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

The lab's study used `forums`, `flight_booking`, `shopping` and `careers`. All personal data in
the task prompts (names, e-mail addresses, phone and card numbers) is fictional.

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
page is hidden). Each line of `captures/<TOKEN>_mm.jsonl` holds one request; its `body` has
`visitorId`, `sourcePage` and `eventFrames`, a list of events. In each event the last element is
the `performance.now()` time in milliseconds and the second is the CSS selector of the target.

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
change events carry the full field value. `PRIVACY = true` in `honeypot/site/js/script.js` masks
printable keys in key events only.

## Change log

- **2026-11-13.** Admin page with its own password and a drop-down menu; model updates run on the
  server; model versions with rollback by date, by version, or to the original models; prompt pool
  report; selectable prompt quantity; agent instructions and a login check in the agent driver;
  Log out also ends an admin sign-in. Server hardening: file requests are confined to the site
  folder and data addresses are restricted to plain words. Original models retrained (`v4`) with
  the sealed audit holdout left out of the training corpus.
- **2026-11-10.** Study login for the Prompt Study and Live Detector pages; Log out link; agent
  driver signs in with the same login.
- **2026-11-09.** PromptGate AI site: prompt bank, participant workbook, Live Detector, first
  models, model refinement script.
- **2026-11-08.** Prompt-capture page and capture-plus server added to the lab's honeypot.

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
