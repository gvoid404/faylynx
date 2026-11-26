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

## What is in place

- The site: a home page, a **Prompt Study** page and a **Live Detector** page, with a study login
  in front of the last two, and an **Admin** page with its own password.
- A fixed pool of 1,000 prompts (`bank_v2`: 70% Shadow AI, 20% Allow, 10% Automated) with 40
  assigned prompts per participant and 200 set aside for agents. Participants can choose how many
  prompts they enter. The earlier 160-prompt pool is kept as `study/prompt_bank_v1.json`.
- An agent driver that enters prompts into the site from a laptop.
- Two models, one for content and one for behavior, trained before any study data was collected.
- Model updates that run on the server from the Admin page, with every version kept and a
  rollback to any date or all the way back to the original models.
- A **Model accuracy** page under Admin: a bar chart of the models in use, a line chart across
  model versions, and both as a PDF download.

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
| Prompt Study | `/<TOKEN>/gateway` | study login | A participant types prompts from the prompt pool; each one is recorded with its typing and mouse behavior. |
| Live Detector | `/<TOKEN>/detector` | study login | Type or paste any prompt and see the category the gateway assigns, with the two parts of the decision shown separately. |
| Admin | `/<TOKEN>/admin` | admin password | Overview of the collected data, model accuracy charts with a PDF download, model updates run on the server, model rollback, prompt quantity settings. |

The top menu is: Prompt Study, Live Detector, Admin (a drop-down with Overview, Model accuracy,
Update models, Roll back models, Prompt quantity) and Log out.

## Repository layout

```
honeypot/
  server_plus.py          the PromptGate web server (Python standard library only)
  admin.py                admin back end: password, sign-in, overview, model-update job, settings
  accuracy.py             reads the collected entries and works out the accuracy of each model version
  charts.py               draws the accuracy charts, as SVG for the page and as a PDF
  model_registry.py       model versions: store, activate, roll back
  inference.py            scores both models in plain Python and applies the category rule
  behavioral_features.py  turns key and mouse events into behavior features
  models/                 the original models (content_model.json, actor_model.json)
  server.py               the lab's original server (six-task honeypot only)
  site/                   the single-page site
    index.html, js/app.js, js/script.js (site-wide tracker), js/recorder.js (per-prompt recorder)
    pages/home.html, gateway.html, detector.html, admin.html and js/pages/*.js
    pages/forums, flights, shop, careers, sort, game    the six original honeypot tasks
    prompt_bank.json      the prompt pool the study page reads
study/
  STUDY_GUIDE.md              step-by-step notes for updating the server and collecting data
  prompt_bank.json            the prompt pool (same file as honeypot/site/prompt_bank.json)
  prompt_bank_v1.json         the previous 160-prompt pool, kept for rollback (not served)
  pool_v2/                    the tools that built the bank_v2 pool (code only; see its README)
  PromptGate_prompt_sheet.xlsx  participant workbook: links, assigned prompts, progress
  sim_gateway.py              agent driver (run on a laptop)
  refine_models.py            scores the models on collected data and retrains them (run by Admin)
  train_and_export.py         trains both models and writes them as JSON
  build_base_corpus.py        packs the private training corpus
  server_setup_training.sh    one-time install of the training tools on the server
  inference.py, behavioral_features.py, models/    earlier copies, no longer used by the scripts
  protect_site.sh             sets, changes or removes the study login
  sim_sessions.py, results/   scripted sessions and their features (training data of the behavior model)
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
(see [The server](#the-server)).

## Prompt Study page

1. The participant opens their link, for example `https://<site>/P07/gateway`, and signs in with
   the study username and password.
2. The consent card explains what is recorded. The participant ticks the box, chooses how many
   prompts to enter, and presses Start.
3. Each prompt is shown on screen. The participant types it by hand. Shadow AI prompts also come
   with made-up data to paste in after the typed part. Send, then Next.
4. On a participant link, reloading the page continues where the participant left off.

**How many prompts.** The quantity is selectable in two places:

- The participant picks a number on the consent card (when the admin allows it).
- The admin sets the default, the fewest and the most on **Admin > Prompt quantity**, and can turn
  the participant's choice off. The shipped settings are default 12, fewest 2, most 40; the most can
  be raised to the whole pool (1,000 with bank_v2).

Participants `P01` to `P20` each have 40 assigned prompts of their own (no prompt is assigned to
two people): 28 Shadow AI, 8 Allow and 4 Automated, ordered so that every block of 10 is 7/2/1, so
whatever number a participant picks, they see about the pool's mix. A smaller number stops early. A
larger number continues through the rest of the pool (other participants' prompts and the agent
reserve) in the same 7/2/1 blocks, in an order fixed for that participant.
Any other link token gets a random draw of Allow and Shadow AI prompts.

Prompts longer than 300 characters that have no separate data part (real prompts that are mostly
pasted text) are shown in the copy box and pasted whole, not retyped; the entry is logged with
`pasted_whole: true`.

`study/PromptGate_prompt_sheet.xlsx` was made for the 160-prompt pool and does not list the bank_v2
assignments; the participant links in it are unchanged.

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

### Model accuracy

**Admin > Model accuracy** shows how well the models judge prompts, in three figures. Each one is
the share of entries judged correctly.

| Figure | What it measures |
|---|---|
| Content model | The category from the text of the prompt alone. |
| Behavior model | Person or agent, from typing and mouse behavior. |
| Both together | The final category the gateway gives. |

- **Accuracy of the models in use**: a bar chart of the three figures for the version the Live
  Detector is using. The table under it splits the content figure by category and the behavior
  figure into people and agents.
- **Accuracy over time**: a line chart with one point for the original models and one for each
  model update, oldest on the left. Pointing at a bar or at a version shows its figures. The
  chart draws the original models and the 11 most recent updates; the table under it lists every
  version.
- **Download as PDF**: one page (US Letter) with both charts, the version table and a note on how
  to read them, saved as `PromptGate_model_accuracy_<date>.pdf`.

Every figure comes from entries the models were not trained on:

- The **original models** are scored on all entries collected so far (links `P01` to `P20` and the
  agent driver), so their figures move as more entries come in. Until there are 20 usable entries,
  the page shows their test scores from before the study: the content model on the prompt pool,
  which was held out of its training, and the behavior model by cross-validation. "Both together"
  is not measured until then.
- A **model update** shows the estimates made when it was created (step 2 under
  [Update models](#update-models)), and they stay as they were. An update of the behavior model
  alone keeps the content figure of the version it started from.
- An entry counts when its text is close to the prompt that was assigned, the same rule the model
  update uses. The Entries column says how many entries each row is based on.

The server draws the charts itself in plain Python (`honeypot/charts.py`), so nothing has to be
installed for this page.

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
In testing on a 2-CPU machine, an update of both models took about 40 seconds and an update of the
behavior model alone a few seconds. Allow about 1 GB of free memory for an update of both models.

Until the private training corpus is on the server, an update retrains the **behavior model
only** and carries the content model over. To retrain the content model as well, copy the corpus
to the server once:

```powershell
scp -i YOUR-KEY base_corpus.jsonl.gz ubuntu@YOUR-SERVER:browsing-agent-honeypot/runtime/
```

The content model is retrained only when a second private file is there too: the human-confirmed
real Shadow AI rows (Paper 2's 734 verified training rows, plus 746 invented Shadow AI rows that keep
the pilot model's recipe), with secrets masked. Without it an update would lose real Shadow AI
recall, so the update then retrains the behavior model only. Copy it once:

```powershell
scp -i YOUR-KEY verified_train_masked.jsonl.gz ubuntu@YOUR-SERVER:browsing-agent-honeypot/runtime/
```

The Admin page says which case applies before you press the button. The corpus is built from the
project's labeled data with `study/build_base_corpus.py`. Both files hold third-party dataset text
and must stay out of this repository (`.gitignore` blocks `runtime/`).

**Real Shadow AI check.** Before a new version is activated, the update scores its own recipe on
the verified real rows it did not train on (5 folds, grouped by near-duplicate cluster). The new
version is activated only if its recall on real data-handling prompts is no more than 5 points
below the active version's (or the floor stored in the verified file, minus 5 points, when the
active version has no check yet), and its false alarms on real look-alike Allow prompts are no
more than 5 points above. Otherwise it is saved but not activated, and the Admin page says why.
**Behavior check.** The behavior model is replaced only if, with participants held out, the new one sees
people's entries as human, and catches agents, within 5 points of the current behavior model on the same
entries. Otherwise the update keeps the current behavior model and replaces only the content model. With few
real participants a new behavior model mostly learns the agents, so expect it to be kept until more people
have taken part.

A content model trained this way is marked `masked`; the gateway then masks secrets in a prompt
(`honeypot/mask_secrets.py`) before scoring it with that model.

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

### Prompt quantity

The quantity settings described [above](#prompt-study-page), and how many pool prompts people and
agents have entered so far.

## Prompt pool: size and source

**Current pool: `bank_v2`** (in `study/prompt_bank.json`, same file as
`honeypot/site/prompt_bank.json`), **1,000 prompts**, built by the Paper 2 tools
(`make_pool_v2_shadow.py`, `paper2_pool_v2_real_rev6.ipynb`, `build_prompt_bank_v2b.py`):

| Category | In the pool | Source |
|---|---:|---|
| Shadow AI | 700 | Written for this project: 560 data handling (customer, staff and patient records, credentials, internal financials, contracts, proprietary code, internal strategy) and 140 workplace-control evasion (DLP, web filters, monitoring, device and transfer policies, approvals; no model jailbreaks). Every company, person, number and secret is made up. |
| Allow | 200 | Real first-turn prompts from WildChat-4.8M (non-toxic release, ODC-BY), a uniform random sample: 134 work-style, 66 general. |
| Automated | 100 | Real prompts from the same sample. |

The real prompts were kept only if the masking step (`mask_secrets.py`) found no personal data or
secret in them, they were not in or near any training, audit or earlier-pool prompt, an LLM judge
(rubric v3.1) labeled them with confidence of at least 0.8, and they passed a hand review. Pool
prompts stay out of content-model training: the training scripts hold out whatever pool is in
`prompt_bank.json`.

The 200 prompts in the bank's `agent_reserve` (same 70/20/10 mix) are not assigned to any
participant; the agent driver enters only these by default.

**Previous pool: `bank_v1`** (kept in `study/prompt_bank_v1.json`), **160 prompts**. People typed
the 120 Allow and Shadow AI prompts; agents entered all 160. The original models were scored on
this pool, and the Model accuracy page says so until enough study entries exist. To go back to it,
copy it over both `prompt_bank.json` files. It was built as follows:

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
N sessions; `--all-prompts` enters every pool prompt instead of the agent reserve (about 1,200
sessions).

What it sends (bank_v2): the 200 prompts in the agent reserve, each of its 20 Automated prompts
under three agent styles (60 sessions) plus each of its 180 Allow and Shadow AI prompts once (180
sessions), so that prompt category and typist are
not tied together.

| Agent style | How it enters the prompt |
|---|---|
| `fill_bot` | fills the box in one step: no typing, no mouse path |
| `type_bot` | types every character at a fast, even pace |
| `evasive_bot` | types with random variation and moves the mouse, trying to look like a person |

Each session is also listed in `agent_manifest.jsonl` in the folder the driver was started from.
The entries show up on **Admin > Overview**, and **Admin > Update models** can use them.

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

It should print `active`. Restarting signs admins out and stops a model update that is running.
Collected data, model versions, settings and passwords are in `captures/` and `runtime/`, which
`git pull` does not touch.

On a new server, after the service and Caddy are set up as below, set the study login, the admin
password and the training tools:

```bash
cd ~/browsing-agent-honeypot
bash study/protect_site.sh
python3 honeypot/admin.py set-password
bash study/server_setup_training.sh
```

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
- **Admin password.** The Admin page's data and actions need the admin password
  (`python3 honeypot/admin.py set-password`). It is stored only as a salted PBKDF2-SHA256 hash in
  `runtime/admin_auth.json`, and admin requests are not written to the capture files.
- **Files.** The web server only serves files inside `honeypot/site/`, and the addresses that
  accept data are single plain words. Collected data is read over SSH, not through the site.
- **What is recorded.** The site records what visitors type on the study and detector pages, their
  typing and mouse behavior, and their network address. The study page shows a consent notice
  first, uses only made-up sensitive data, and asks participants not to enter real personal or
  confidential information. Do not invite participants before the approvals your institution
  requires are in place.
- **Keep the data private.** `captures/` and `runtime/` are listed in `.gitignore`. Keep them, and
  the project's labeled data and training corpus, out of any public place.

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
