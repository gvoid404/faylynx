# PromptGate AI study: update, collect, refine

Site: https://clemons.3-20-226-103.nip.io  (instance 3.20.226.103, user ubuntu)

## 1. Put the update on the server (once)

The update is `site_update.tgz` in this folder (new look, name, menu, prompt bank, Live Detector, models).
It is too big to paste into the browser terminal, so copy it with scp. Windows PowerShell:

```powershell
# a) make a key (press Enter twice when asked for a passphrase)
ssh-keygen -t ed25519 -f "$HOME\.ssh\clemons_gw"
type "$HOME\.ssh\clemons_gw.pub"          # copy the one line it prints
```
In the EC2 browser terminal, paste that line inside the quotes and run it:
```bash
echo "PASTE-THE-LINE-HERE" >> ~/.ssh/authorized_keys
```
Back in PowerShell, from this `deploy` folder:
```powershell
scp -i "$HOME\.ssh\clemons_gw" site_update.tgz ubuntu@3.20.226.103:
ssh -i "$HOME\.ssh\clemons_gw" ubuntu@3.20.226.103 "tar xzf site_update.tgz -C browsing-agent-honeypot && sudo systemctl restart honeypot && systemctl is-active honeypot"
```
It should print `active`. Open the site and hard-refresh (Ctrl+Shift+R).

## 2. Collect

- People: send each participant their link from `PromptGate_prompt_sheet.xlsx` (Participants tab), for example
  `https://clemons.3-20-226-103.nip.io/P07/gateway`. 12 prompts each, typed by hand.
- Agents (your laptop, needs `pip install playwright` and `playwright install chromium`):
  ```powershell
  python sim_gateway.py --base https://clemons.3-20-226-103.nip.io --limit 6     # smoke test
  python sim_gateway.py --base https://clemons.3-20-226-103.nip.io               # all 240 sessions
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
scp -r -i "$HOME\.ssh\clemons_gw" ubuntu@3.20.226.103:browsing-agent-honeypot/captures captures_live
```

## 4. Refine the models and publish them to the detector

```powershell
pip install scikit-learn xgboost pandas
python refine_models.py --captures captures_live --p2 ..
scp -i "$HOME\.ssh\clemons_gw" models\content_model.json models\actor_model.json ubuntu@3.20.226.103:browsing-agent-honeypot/honeypot/models/
```
`refine_models.py` scores the current models on the live data, estimates the refined models with
participants and prompts held out, retrains on everything, and writes `refine_report.json`. The Live
Detector reloads the two model files on its own; no restart needed.
