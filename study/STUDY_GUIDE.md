# PromptGate AI study: update, collect, refine

Site: https://clemons.us  (Elastic IP 3.139.149.111, user ubuntu)

## 1. Update the server

The server keeps a copy of the GitHub repository in `~/browsing-agent-honeypot`. To bring it up to
date, connect to the server and run:

```bash
cd ~/browsing-agent-honeypot && git pull --ff-only && sudo systemctl restart honeypot && systemctl is-active honeypot
```
It should print `active`. Open the site and hard-refresh (Ctrl+Shift+R). Do not unpack the old
`site_update.tgz` any more: it holds an earlier version of the site.

To connect from Windows PowerShell with a key:

```powershell
# a) make a key once (press Enter twice when asked for a passphrase)
ssh-keygen -t ed25519 -f "$HOME\.ssh\clemons_gw"
type "$HOME\.ssh\clemons_gw.pub"          # copy the one line it prints
```
In the EC2 browser terminal, paste that line inside the quotes and run it:
```bash
echo "PASTE-THE-LINE-HERE" >> ~/.ssh/authorized_keys
```
From then on:
```powershell
ssh -i "$HOME\.ssh\clemons_gw" ubuntu@clemons.us
```

## Site login

The Prompt Study and Live Detector pages, and the data they send, need a username and password.
The home page is open. Set or change the login on the server:

```bash
cd ~/browsing-agent-honeypot && git pull && bash study/protect_site.sh
```
Remove it with `bash study/protect_site.sh --remove`. Give participants the username and password
with their link; the browser asks once.

The agent driver uses the same login. The password is asked for when it starts (or read from the
`PROMPTGATE_PASSWORD` environment variable); it is never typed on the command line:

```powershell
python sim_gateway.py --base https://clemons.us --user study --limit 6
```

## 2. Collect

- People: send each participant their link from `PromptGate_prompt_sheet.xlsx` (Participants tab), for example
  `https://clemons.us/P07/gateway`. 12 prompts each by default, typed by hand; the participant can pick
  another number on the first screen (the limits are set on Admin > Prompt quantity).
- Agents (your laptop, needs `pip install playwright` and `playwright install chromium`):
  ```powershell
  python sim_gateway.py --base https://clemons.us --limit 6     # smoke test
  python sim_gateway.py --base https://clemons.us               # all 240 sessions
  ```

## 3. Where the data lands

JSONL files on the server in `~/browsing-agent-honeypot/captures/`, one set per link token:

| file | one line per | holds |
|---|---|---|
| `<TOKEN>_prompt.jsonl` | prompt sent | entered text, prompt id, class, that prompt's key/mouse events, browser + TLS headers, IP |
| `<TOKEN>_consent.jsonl` | consent click | timestamp |
| `<TOKEN>_classify.jsonl` | Live Detector use | prompt, events, and the model's answer |
| `<TOKEN>_feedback.jsonl` | detector feedback click | what the user said the prompt really was |
| `<TOKEN>_mm.jsonl` | 0.5 s batch | raw site-wide event stream (backup) |

Pull it to your laptop:
```powershell
scp -r -i "$HOME\.ssh\clemons_gw" ubuntu@clemons.us:browsing-agent-honeypot/captures captures_live
```

## 4. Update the models

On the site: **Admin > Update models > Run model update**. It runs on the server: it scores the
current models on the collected data, estimates the retrained models with participants and prompts
held out, retrains, and saves the result as a new version. **Admin > Roll back models** goes back to
any earlier version, to a date, or to the original models. The one-time setup is in the README
(Admin page). Do not copy model files into `honeypot/models/` by hand any more.

**Admin > Model accuracy** shows the accuracy of the models in use as a bar chart and the accuracy
of every model version as a line chart, and saves both as a PDF.
