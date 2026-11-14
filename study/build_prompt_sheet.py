#!/usr/bin/env python3
"""Build the participant workbook (PromptGate_prompt_sheet.xlsx) from the prompt bank.

Tabs: Start here (instructions), Participants (personal links and progress), Prompts to enter
(the 12 assigned prompts of each participant), Automated prompts (entered by the agent driver),
Totals. Needs openpyxl (pip install openpyxl).

  python build_prompt_sheet.py                        # writes PromptGate_prompt_sheet.xlsx here
  python build_prompt_sheet.py --site https://example.org --out sheet.xlsx
"""
import argparse, json
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--bank", default=str(HERE / "prompt_bank.json"))
ap.add_argument("--site", default="https://clemons.us", help="site address used for the participant links")
ap.add_argument("--out", default=str(HERE / "PromptGate_prompt_sheet.xlsx"))
a = ap.parse_args()

bank = json.load(open(a.bank, encoding="utf-8"))
byid = {p["id"]: p for p in bank["prompts"]}
per = int(bank.get("n_per_participant", 12))
n_people = len(bank["sets"])
n_auto = sum(1 for p in bank["prompts"] if p["class"] == "Automated AI Pipelines")
n_human_pool = len(bank["prompts"]) - n_auto
n_rows = sum(len(v) for v in bank["sets"].values())

F = Font(name="Arial", size=10); B = Font(name="Arial", size=10, bold=True)
H = Font(name="Arial", size=10, bold=True, color="FFFFFF"); T = Font(name="Arial", size=14, bold=True)
NOTE = Font(name="Arial", size=9, italic=True); LINK = Font(name="Arial", size=10, color="0000FF", underline="single")
HEAD_FILL = PatternFill("solid", fgColor="A12C8C"); INPUT_FILL = PatternFill("solid", fgColor="FFF2A8")
SHADOW_FILL = PatternFill("solid", fgColor="F9DDF4")
thin = Side(style="thin", color="D9B3D1"); BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
WRAP = Alignment(wrap_text=True, vertical="top")


def header(ws, row, cols):
    for i, c in enumerate(cols, 1):
        x = ws.cell(row=row, column=i, value=c)
        x.font = H; x.fill = HEAD_FILL; x.border = BOX; x.alignment = Alignment(wrap_text=True, vertical="center")


def widths(ws, w):
    for i, x in enumerate(w, 1):
        ws.column_dimensions[get_column_letter(i)].width = x


wb = Workbook()

# ---- Start here ----
ws = wb.active; ws.title = "Start here"; widths(ws, [110])
lines = [
    ("PromptGate AI prompt study: participant prompt sheet", T),
    (f"What this is. Each participant types prompts from the study's prompt bank into the study site. By default that is the "
     f"{per} assigned prompts listed here ({per // 2} Allow, {per // 2} Shadow AI). This workbook lists who types what, the link "
     "each person uses, and tracks progress.", F),
    ("", F), ("How a participant does it", B),
    ("1. Open your personal link from the Participants tab (it contains your ID, for example P07). Sign in with the study username and password you were given.", F),
    (f"2. Tick the consent box. The page asks how many prompts you would like to enter: leave it at {per} unless you were asked for a "
     "different number. Press Start. The site shows your prompts one at a time, in the same order as the 'Prompts to enter' tab.", F),
    ("3. TYPE the text in the 'Type this' column by hand. Do not copy and paste it: typing rhythm is what the study measures.", F),
    ("4. If the row has text in 'Then paste this', press the site's Copy data button and paste it after what you typed. All of that data is made up.", F),
    (f"5. Press Send, then Next. When all your prompts are done the site says 'All done'. Mark Done = Y in this sheet for each of the {per} listed prompts.", F),
    (f"If you choose more than {per}, the extra prompts appear on screen only (they are not listed in this sheet). If you choose fewer, "
     "you stop early and the remaining rows stay blank.", F),
    ("", F), ("Which cells to fill in", B),
    ("Yellow cells are for you to fill in: on Participants (name or initials, device, mouse or trackpad, date) and on 'Prompts to enter' (Done, Notes). Example: Done = Y, Notes = 'typo in second word'.", F),
    ("Everything else is fixed. Do not edit prompt text or IDs: the site and the analysis match on them.", F),
    ("", F), ("Where the prompts came from", B),
    ("Allow prompts: 60 real user prompts with human gold labels from the Paper 2 gold set (human_gold_v1), screened for length and content.", F),
    ("Shadow AI prompts: 60 items from synthetic_shadow_v1 (the fictional-payload set used in model training): customer and HR records, credentials, financials, contracts, code, and control-bypass requests. No real data.", F),
    ("Automated prompts (agents only, see 'Automated prompts' tab): 40 software-style prompts labeled Automated AI Pipelines, 26 from the human gold set and 14 from the judge-labeled 10k set.", F),
    (f"All {len(bank['prompts'])} bank prompts were held out when the original content model was trained, so the first live results are a fair test.", F),
    ("", F), ("Numbers", B),
    (f"Humans: {n_people} participants x {per} prompts = {n_people * per} entries at the default quantity. Every Allow and Shadow prompt is assigned to 2 different people.", F),
    (f"Agents: {n_auto * 3 + n_human_pool} sessions = each of the {n_auto} Automated prompts under 3 agent styles ({n_auto * 3}) + each of the {n_human_pool} Allow/Shadow prompts once ({n_human_pool}).", F),
    (f"Minimum useful pilot: 10 participants ({10 * per} human entries).", F),
]
for i, (text, font) in enumerate(lines, 1):
    c = ws.cell(row=i, column=1, value=text); c.font = font; c.alignment = WRAP

# ---- Participants ----
wp = wb.create_sheet("Participants"); widths(wp, [12, 58, 22, 18, 18, 14, 14, 14])
wp["A1"] = "Site address"; wp["A1"].font = B
wp["B1"] = a.site; wp["B1"].font = Font(name="Arial", size=10, color="0000FF"); wp["B1"].fill = INPUT_FILL
wp["C1"] = "Change B1 if the site address changes; every link below updates."; wp["C1"].font = NOTE
header(wp, 3, ["Participant ID", "Personal link (click to open)", "Name or initials", "Device (laptop / desktop)",
               "Mouse or trackpad", "Date done", f"Prompts done (of {per})", "Status"])
first, last = 4, 3 + n_people
for n, pid in enumerate(bank["sets"]):
    r = first + n
    wp.cell(row=r, column=1, value=pid).font = B
    wp.cell(row=r, column=2, value=f'=HYPERLINK($B$1&"/"&A{r}&"/gateway",$B$1&"/"&A{r}&"/gateway")').font = LINK
    for col in (3, 4, 5, 6):
        wp.cell(row=r, column=col).fill = INPUT_FILL
    wp.cell(row=r, column=7, value=f"=COUNTIFS('Prompts to enter'!$A:$A,A{r},'Prompts to enter'!$G:$G,\"Y\")")
    wp.cell(row=r, column=8, value=f'=IF(G{r}>={per},"Complete",IF(G{r}>0,"In progress","Not started"))')
    for col in range(1, 9):
        x = wp.cell(row=r, column=col); x.border = BOX
        if col not in (1, 2):
            x.font = F
wp.freeze_panes = "A4"

# ---- Prompts to enter ----
we = wb.create_sheet("Prompts to enter"); widths(we, [12, 7, 10, 12, 60, 70, 9, 30])
header(we, 1, ["Participant ID", "Order", "Prompt ID", "Category", "Type this (by hand)",
               "Then paste this (use the site's Copy data button)", "Done (Y)", "Notes"])
r = 2
for pid, ids in bank["sets"].items():
    for k, i in enumerate(ids, 1):
        p = byid[i]
        for col, v in enumerate([pid, k, i, p["class"], p["type_text"], p["paste_text"]], 1):
            x = we.cell(row=r, column=col, value=v); x.font = F; x.alignment = WRAP; x.border = BOX
            if p["class"] == "Shadow AI" and col == 4:
                x.fill = SHADOW_FILL
        for col in (7, 8):
            x = we.cell(row=r, column=col); x.fill = INPUT_FILL; x.border = BOX; x.font = F
        r += 1
end = r - 1
we.freeze_panes = "A2"; we.auto_filter.ref = f"A1:H{end}"

# ---- Automated prompts ----
wa = wb.create_sheet("Automated prompts"); widths(wa, [10, 16, 100, 12, 12, 12])
header(wa, 1, ["Prompt ID", "Source", "Prompt (entered by the agent driver, not by people)",
               "fill_bot run (Y)", "type_bot run (Y)", "evasive_bot run (Y)"])
r = 2
for p in bank["prompts"]:
    if p["class"] != "Automated AI Pipelines":
        continue
    for col, v in enumerate([p["id"], p["source"], p["type_text"]], 1):
        x = wa.cell(row=r, column=col, value=v); x.font = F; x.alignment = WRAP; x.border = BOX
    for col in (4, 5, 6):
        x = wa.cell(row=r, column=col); x.fill = INPUT_FILL; x.border = BOX
    r += 1
wa.freeze_panes = "A2"

# ---- Totals ----
wt = wb.create_sheet("Totals"); widths(wt, [48, 14, 14, 14])
header(wt, 1, ["Measure", "Planned", "Done", "Percent done"])
E = f"'Prompts to enter'!"
rows = [
    (f"Human prompt entries ({n_people} people x {per})", f"=COUNTA({E}C2:C{end})", f"=COUNTIF({E}G2:G{end},\"Y\")"),
    ("  of which Allow", f"=COUNTIF({E}D2:D{end},\"Allow\")", f"=COUNTIFS({E}D2:D{end},\"Allow\",{E}G2:G{end},\"Y\")"),
    ("  of which Shadow AI", f"=COUNTIF({E}D2:D{end},\"Shadow AI\")", f"=COUNTIFS({E}D2:D{end},\"Shadow AI\",{E}G2:G{end},\"Y\")"),
    ("Participants complete", f"=COUNTA(Participants!A{first}:A{last})", f"=COUNTIF(Participants!H{first}:H{last},\"Complete\")"),
    (f"Automated prompt runs ({n_auto} prompts x 3 agent styles)", f"=COUNTA('Automated prompts'!A2:A{n_auto + 1})*3",
     f"=COUNTIF('Automated prompts'!D2:F{n_auto + 1},\"Y\")"),
]
for i, (label, planned, done) in enumerate(rows, 2):
    wt.cell(row=i, column=1, value=label).font = F
    wt.cell(row=i, column=2, value=planned).font = F
    wt.cell(row=i, column=3, value=done).font = F
    d = wt.cell(row=i, column=4, value=f"=IF(B{i}=0,0,C{i}/B{i})"); d.font = F; d.number_format = "0%"
wt["A8"] = ("Agent runs are also logged automatically in agent_manifest.jsonl by sim_gateway.py, and the Admin page counts "
            "every entry the site received; the Y columns are optional.")
wt["A8"].font = NOTE

wb.save(a.out)
print(f"saved {a.out}: {n_people} participants, {n_rows} assigned prompts, {n_auto} automated prompts")
