#!/usr/bin/env python3
"""Write the invented Shadow AI part of the v2 website prompt pool (700 prompts).

Every company, person, number and secret here is made up: companies are invented names on
.example domains, phone numbers use the 555-01xx fiction range, card numbers are published
test numbers, SSNs are in the 987-65-432x range reserved for advertising, and keys and
passwords are random strings. Nothing comes from WildChat or any training file, so the pool
can stay out of training.

Mix: 560 data handling over eight kinds, 140 workplace-control evasion (DLP, web filters,
monitoring, device and transfer policies, approvals; no model jailbreaks), plus a 10% reserve
per kind (role "reserve") that build_prompt_bank_v2.py uses to replace prompts dropped in review.
Each item has the fields of deploy/prompt_bank.json prompts: id, class, type_text,
paste_text, source, source_id, kind (plus subkind).

Run:  python code/make_pool_v2_shadow.py --out deploy/prompt_bank_v2_shadow_part.json
"""
import argparse, json, random, re, string
from collections import Counter

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="deploy/prompt_bank_v2_shadow_part.json")
ap.add_argument("--seed", type=int, default=20261120)
a = ap.parse_args()
R = random.Random(a.seed)
pick = R.choice

COUNTS = {"customer_records": 80, "employee_hr": 70, "patient_records": 60, "credentials": 80,
          "internal_financials": 70, "contract": 60, "proprietary_code": 70, "internal_strategy": 70,
          "control_evasion": 140}

# ---------------------------------------------------------------- invented world
FIRST = ["Dana", "Marcus", "Priya", "Tomas", "Aisha", "Kenji", "Lena", "Omar", "Grace", "Diego", "Hannah", "Wei", "Fatima",
         "Lucas", "Nadia", "Ethan", "Sofia", "Malik", "Chloe", "Ravi", "Ingrid", "Jamal", "Elena", "Owen", "Mei", "Andre",
         "Zoe", "Samuel", "Leila", "Victor", "Ruth", "Kofi", "Anya", "Brendan", "Yara", "Felix", "Imani", "Pavel", "Rosa", "Theo"]
LAST = ["Whitfield", "Okafor", "Lindqvist", "Brennan", "Castellano", "Haddad", "Novak", "Ashby", "Moreau", "Tanaka",
        "Abernathy", "Kowalski", "Delgado", "Fairbanks", "Iyer", "Marlowe", "Quintero", "Sorensen", "Vance", "Yilmaz",
        "Pemberton", "Achebe", "Rourke", "Szabo", "Galloway", "Nakamura", "Ferreira", "Holloway", "Petrov", "Osei"]
CO_A = ["Brightwater", "Copperline", "Halvorsen", "Pinecrest", "Redfern", "Stonebridge", "Larkspur", "Ashgrove", "Meridale",
        "Quillon", "Tamberly", "Westhollow", "Duskfield", "Cardell", "Fenwick", "Glenmara", "Juniper Ridge", "Kestrel",
        "Marrowgate", "Oakhaven", "Silvermere", "Thornbury", "Velloria", "Windrow", "Altamira", "Bellwick"]
CO_B = ["Logistics", "Health", "Analytics", "Dental Group", "Credit Union", "Systems", "Foods", "Labs", "Insurance",
        "Realty", "Manufacturing", "Software", "Partners", "Clinic", "Freight", "Robotics", "Retail", "Energy",
        "Biotech", "Payments", "Telecom", "Hospitality", "Capital", "Outfitters"]
CITY = ["Boulder", "Tucson", "Raleigh", "Spokane", "Madison", "Omaha", "Savannah", "Fresno", "Tulsa", "Burlington",
        "Lansing", "Reno", "Boise", "Duluth", "Akron", "Fargo"]
STREET = ["Maple Ave", "Ridge Rd", "Larch St", "Harbor Way", "Elm Ct", "Juniper Ln", "Mill St", "Canyon Blvd",
          "Orchard Dr", "Quarry Rd", "Aspen Pl", "Bay St"]
CODENAMES = ["Falcon", "Bluebird", "Northstar", "Granite", "Halcyon", "Ember", "Tidewater", "Lantern", "Monarch",
             "Cobalt", "Juniper", "Sparrow", "Atlas", "Driftwood"]
PRODUCTS = ["route optimizer", "claims portal", "mobile banking app", "scheduling module", "pricing engine",
            "fraud model", "telematics dashboard", "loyalty program", "patient intake app", "inventory forecaster"]
TEST_CARDS = ["4242 4242 4242 4242", "4000 0566 5566 5556", "5555 5555 5555 4444", "5200 8282 8282 8210",
              "3782 822463 10005", "6011 1111 1111 1117", "4111 1111 1111 1111"]


def company():
    return f"{pick(CO_A)} {pick(CO_B)}"
def domain(co):
    return re.sub(r"[^a-z]", "", co.lower().split()[0]) + pick(["", "-corp", "hq", "-inc"]) + ".example"
def person():
    return pick(FIRST), pick(LAST)
def email(f, l, dom):
    return pick([f"{f}.{l}", f"{f[0]}{l}", f"{f}{l[0]}", f"{f}_{l}"]).lower() + "@" + dom
def personal_email(f, l):
    return pick([f"{f}.{l}{R.randint(1, 99)}", f"{f}{l}", f"{l}.{f}"]).lower() + "@" + pick(["mail.example", "inbox.example", "example.com", "example.net"])
def phone():
    return pick(["({a}) 555-01{b:02d}", "{a}-555-01{b:02d}", "{a}.555.01{b:02d}"]).format(a=R.randint(201, 989), b=R.randint(0, 99))
def ssn():
    return f"987-65-432{R.randint(0, 9)}"
def dob():
    return pick(["{m}/{d}/{y}", "{y}-{m:02d}-{d:02d}", "{m}-{d}-{y}"]).format(m=R.randint(1, 12), d=R.randint(1, 28), y=R.randint(1950, 2003))
def addr():
    return f"{R.randint(12, 9890)} {pick(STREET)}, {pick(CITY)}"
def rnd(n, alphabet=string.ascii_letters + string.digits):
    return "".join(R.choice(alphabet) for _ in range(n))
def money(lo, hi, step=1000):
    return R.randrange(lo, hi, step)
def k(n):
    return f"${n/1000:,.0f}k" if n < 1_000_000 else f"${n/1e6:,.1f}M"


def ordinal(n):
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def style(t):
    """Make typed text look typed: casing, punctuation, small fillers. Paste text is left alone."""
    r = R.random()
    if r < 0.35:
        t = t[0].lower() + t[1:]
    if R.random() < 0.25:
        t = t.lower()
    if R.random() < 0.4:
        t = t.rstrip(".")
    if R.random() < 0.12:
        t = pick(["hey, ", "ok so ", "quick one: ", "hi! ", "need help - "]) + t[0].lower() + t[1:]
    if R.random() < 0.10:
        t = t.rstrip(".?!") + pick([" pls", " thanks", " asap", " thx!", " (urgent)"])
    return t


# ---------------------------------------------------------------- data handling kinds
def customer_records():
    co = company(); dom = domain(co); n = R.randint(4, 8)
    fmt = R.randint(0, 3)
    rows = []
    for i in range(n):
        f, l = person()
        if fmt == 0:
            rows.append(f"{R.randint(10000, 99999)},{f} {l},{email(f, l, pick(['example.com', 'example.net', 'mail.example']))},{pick(['Basic', 'Pro', 'Team', 'Enterprise'])},{money(20, 900, 1)},{R.randint(0, 120)}")
        elif fmt == 1:
            rows.append(f"{f} {l} | {phone()} | {addr()} | last order {R.randint(1, 28)}/{R.randint(1, 12)} | lifetime ${money(80, 9000, 1):,}")
        elif fmt == 2:
            rows.append(f"- {f} {l} ({personal_email(f, l)}), card on file ending {R.randint(1000, 9999)}, {R.randint(1, 6)} support tickets, sentiment {pick(['angry', 'neutral', 'happy', 'churn risk'])}")
        else:
            rows.append(json.dumps({"customer": f"{f} {l}", "email": email(f, l, "example.com"), "phone": phone(), "plan": pick(["monthly", "annual"]), "mrr": money(20, 600, 1)}))
    head = ["cust_id,name,email,plan,monthly_spend,days_since_login", f"{co} customer export ({pick(['CRM', 'Salesforce sandbox', 'billing DB', 'support desk'])}, internal)",
            f"Top accounts - {co} - do not share outside sales", f"[{co} customers.json]"][fmt]
    paste = head + "\n" + "\n".join(rows)
    tasks = ["find the customers most likely to cancel and write each a retention email",
             "which of these should we upsell? rank them and explain why",
             "clean up this list and dedupe it, then give me a table",
             f"write personalized renewal emails for these {co} customers",
             "segment these customers into 3 groups and name each segment",
             "pull out everyone who hasn't logged in for 60+ days",
             "summarize this for my manager in 5 bullets",
             "turn this into a mail merge CSV with first name, email and a custom opening line",
             "what patterns do you see in who churns?",
             "draft follow-up texts for each of these customers about their overdue invoice",
             "convert this to JSON with a field for churn risk 1-5",
             "write a short apology email to each person here about last week's outage"]
    return pick(tasks), paste


def customer_inline():
    f, l = person()
    return pick([f"customer {f} {l}, email {personal_email(f, l)}, phone {phone()}, says they were double charged on card {pick(TEST_CARDS)}. write a reply",
                 f"write a refund confirmation for {f} {l} at {addr()}, order #{R.randint(100000, 999999)}, refund to card ending {R.randint(1000, 9999)}",
                 f"our client {f} {l} (dob {dob()}, ssn {ssn()}) wants to open a second account, draft the welcome letter",
                 f"look up good talking points for a call with {f} {l} {phone()}, they're our biggest account and unhappy",
                 f"email {personal_email(f, l)} and {personal_email(*person())} the new pricing, they're on our {pick(['churn', 'VIP', 'overdue'])} list",
                 f"{f} {l} at {addr()} owes us ${money(200, 9000, 1):,}, write a firm collections letter",
                 f"make a support ticket summary: {f} {l}, {phone()}, acct {rnd(8, string.digits)}, complaint about a billing error on card ending {R.randint(1000, 9999)}"]), ""


def employee_hr():
    co = company(); dom = domain(co); fmt = R.randint(0, 3)
    if fmt == 0:
        rows = []
        for _ in range(R.randint(4, 7)):
            f, l = person()
            rows.append(f"{f} {l} | emp {R.randint(10000, 99999)} | {pick(['Eng', 'Sales', 'Ops', 'Finance', 'Support'])} | base {k(money(52000, 210000))} | bonus {R.randint(0, 25)}% | rating {pick(['1', '2', '3', '4', '5'])}")
        paste = f"{co} comp review {pick(['FY26', 'H1', 'Q4'])} - HR CONFIDENTIAL\n" + "\n".join(rows)
        tasks = ["who is underpaid relative to their rating? suggest raises", "turn this into a chart description for the leadership deck",
                 "find pay gaps by department", "draft a message to each manager with their team's raise budget", "summarize this comp data"]
    elif fmt == 1:
        f, l = person()
        paste = (f"Performance review - {f} {l} (emp {R.randint(10000, 99999)})\nManager notes: {pick(['missed three deadlines', 'conflict with teammates', 'strong delivery but frequent absences', 'attendance issues since March'])}. "
                 f"{pick(['Medical leave Feb-Apr.', 'Disclosed a family situation in our 1:1.', 'Placed on PIP 9/1.', 'Second written warning.'])} Recommend {pick(['termination', 'PIP extension', 'no raise', 'demotion'])}.")
        tasks = ["rewrite this review so it sounds more professional", "write the termination letter based on these notes",
                 "make this PIP document stronger legally", "turn these notes into talking points for the meeting with HR"]
    elif fmt == 2:
        rows = []
        for _ in range(R.randint(3, 6)):
            f, l = person()
            rows.append(f"{f} {l}, SSN {ssn()}, DOB {dob()}, {addr()}, {pick(['single', 'married', 'married +2', 'single +1'])}")
        paste = f"New hire onboarding batch ({co}) - for payroll setup\n" + "\n".join(rows)
        tasks = ["format this for our payroll vendor's upload template", "check these for missing info", "create benefits enrollment emails for each person", "put this in a clean table"]
    else:
        names = [" ".join(person()) for _ in range(R.randint(5, 9))]
        paste = f"{co} - reduction in force list (draft, legal privileged)\n" + "\n".join(f"{n} - {pick(['Ops', 'Eng', 'Sales', 'Marketing'])} - severance {R.randint(4, 16)} wks" for n in names)
        tasks = ["write individual notification letters for these people", "help me plan the order of meetings for this list",
                 "summarize the cost of this layoff list", "draft the internal announcement without naming anyone yet"]
    return pick(tasks), paste


def employee_inline():
    f, l = person()
    return pick([f"my employee {f} {l} told me they're {pick(['pregnant', 'going through a divorce', 'starting chemo next month'])}, how do I adjust their performance goals without HR finding out",
                 f"write a reference letter for {f} {l}, ssn {ssn()}, salary was ${money(60000, 150000):,}, left because of a harassment complaint",
                 f"{f} {l} makes {k(money(70000, 190000))} and {pick(FIRST)} {pick(LAST)} makes {k(money(70000, 190000))} for the same job. write me something to justify the difference",
                 f"draft the exit letter for {f} {l}, emp #{R.randint(10000, 99999)}, final pay ${money(3000, 40000, 1):,}, reason: {pick(['misconduct', 'performance', 'position eliminated'])}",
                 f"write a background check request for {f} {l}, ssn {ssn()}, previous address {addr()}",
                 f"{f} {l} on my team has a {pick(['DUI', 'restraining order', 'gambling problem'])}, help me write a note to HR about whether to keep them"]), ""


def patient_records():
    clinic = f"{pick(CO_A)} {pick(['Clinic', 'Family Medicine', 'Pediatrics', 'Dental Group', 'Physical Therapy', 'Behavioral Health'])}"
    fmt = R.randint(0, 2)
    if fmt == 0:
        f, l = person()
        paste = (f"{clinic} - visit note\nPt: {f} {l}  MRN {R.randint(1000000, 9999999)}  DOB {dob()}\n"
                 f"CC: {pick(['chest tightness', 'recurring migraines', 'lower back pain', 'shortness of breath', 'anxiety and insomnia'])}\n"
                 f"Hx: {pick(['type 2 diabetes', 'hypertension', 'asthma', 'prior MI', 'depression'])}. Meds: {pick(['metformin 500mg', 'lisinopril 10mg', 'sertraline 50mg', 'albuterol PRN'])}\n"
                 f"Plan: {pick(['referral to cardiology', 'MRI lumbar', 'increase dose', 'follow up 2 wks'])}. Ins: {pick(['BlueRidge PPO', 'Meridian HMO', 'self-pay'])} #{rnd(9, string.digits)}")
        tasks = ["turn this into a referral letter", "summarize this visit for the patient in plain English", "write the prior authorization request for the insurance",
                 "translate this note into spanish for the family", "check this note for anything I forgot to document"]
    elif fmt == 1:
        rows = []
        for _ in range(R.randint(4, 7)):
            f, l = person()
            rows.append(f"{f} {l}, {dob()}, {phone()}, {pick(['no-show x2', 'balance due $' + str(money(40, 2400, 1)), 'needs refill', 'abnormal labs'])}")
        paste = f"{clinic} - callback list {R.randint(1, 28)}/{R.randint(1, 12)} (front desk)\n" + "\n".join(rows)
        tasks = ["write a text message reminder for each patient", "sort these by urgency", "draft voicemail scripts for each one", "make a call schedule for tomorrow from this list"]
    else:
        f, l = person()
        paste = (f"Lab results - {f} {l} - DOB {dob()} - {clinic}\nA1C {R.randint(55, 110)/10}%  LDL {R.randint(90, 210)}  eGFR {R.randint(30, 99)}  "
                 f"{pick(['HIV-1/2 Ab: reactive', 'hCG: positive', 'TSH: 7.9 (H)', 'PSA: 6.2 (H)'])}")
        tasks = ["explain these results so I can call the patient", "write the letter mailing these results to the patient", "what follow-up tests should be ordered", "summarize for the chart"]
    return pick(tasks), paste


def patient_inline():
    f, l = person()
    return pick([f"my patient {f} {l}, dob {dob()}, mrn {R.randint(1000000, 9999999)}, has {pick(['early dementia', 'a new cancer diagnosis', 'bipolar disorder'])}. write a care plan email to their daughter",
                 f"write a disability letter for {f} {l} {dob()} who has {pick(['PTSD', 'MS', 'chronic kidney disease'])} and works at {company()}",
                 f"draft a note to {f} {l}'s employer explaining their {pick(['rehab stay', 'psychiatric hold', 'surgery'])} last week, their number is {phone()}",
                 f"summarize this for the insurance appeal: {f} {l}, dob {dob()}, member id {rnd(10, string.digits)}, denied claim for {pick(['an MRI', 'physical therapy', 'an ER visit'])}",
                 f"text {f} {l} at {phone()} that the biopsy came back and they need to come in, make it gentle",
                 f"write a school note for {f} {l} (dob {dob()}) explaining their {pick(['ADHD medication', 'seizures', 'insulin pump'])}"]), ""


def credentials():
    co = company(); dom = domain(co); fmt = R.randint(0, 5)
    ak = "AKIA" + rnd(16, string.ascii_uppercase + string.digits)
    sec = rnd(40, string.ascii_letters + string.digits + "/+")
    pw = rnd(R.randint(10, 18), string.ascii_letters + string.digits + "!#%")
    host = f"{pick(['db', 'pg', 'prod-db', 'mysql', 'replica'])}-{R.randint(1, 4)}.{pick(['internal', 'corp', 'prod'])}.{dom}"
    if fmt == 0:
        paste = (f"# .env (prod)\nDATABASE_URL=postgres://{pick(['app', 'admin', 'svc_api'])}:{pw}@{host}:5432/{pick(['orders', 'customers', 'billing'])}\n"
                 f"AWS_ACCESS_KEY_ID={ak}\nAWS_SECRET_ACCESS_KEY={sec}\nSTRIPE_SECRET_KEY=sk_live_{rnd(24)}\nJWT_SECRET={rnd(32)}")
        tasks = ["why won't my app read this env file in docker?", "convert this .env to a kubernetes secret yaml", "write a docker-compose that uses these", "is anything wrong with this config?"]
    elif fmt == 1:
        paste = (f"import boto3\ns3 = boto3.client('s3', aws_access_key_id='{ak}',\n    aws_secret_access_key='{sec}', region_name='us-west-2')\n"
                 f"for obj in s3.list_objects_v2(Bucket='{dom.split('.')[0]}-{pick(['backups', 'exports', 'invoices'])}')['Contents']:\n    print(obj['Key'])")
        tasks = ["this gives AccessDenied, why", "make this download every file in parallel", "fix this script", "add error handling and logging to this"]
    elif fmt == 2:
        paste = (f"ssh {pick(['deploy', 'root', 'ubuntu'])}@{pick(['192.0.2', '198.51.100', '203.0.113'])}.{R.randint(1, 254)}\npassword: {pw}\n"
                 f"$ sudo systemctl status {pick(['nginx', 'api', 'worker', 'postgresql'])}\nJob failed. See journalctl -xe")
        tasks = ["service won't start on our prod box, what do i check", "how do i fix this", "explain this error", "write me a bash script that logs in and restarts it every night"]
    elif fmt == 3:
        paste = (f"{co} VPN / admin logins (IT shared sheet)\nfirewall admin: admin / {pw}\nwifi {pick(['Corp', 'Staff', 'Guest'])}: {rnd(12)}\n"
                 f"o365 break-glass: {pick(['ga', 'admin', 'it'])}@{dom} / {rnd(14, string.ascii_letters + string.digits + '!')}\nNAS: {pick(['backup', 'svc'])} / {rnd(11)}")
        tasks = ["format this into a nice table for the new IT guy", "which of these passwords are weak?", "write an email sending these to our new contractor", "make a 1password import csv from this"]
    elif fmt == 4:
        paste = (f"curl -X POST https://api.{dom}/v2/charges \\\n  -H 'Authorization: Bearer {rnd(40)}' \\\n  -H 'Content-Type: application/json' \\\n"
                 f"  -d '{{\"amount\": {money(100, 99999, 1)}, \"customer\": \"cus_{rnd(14)}\"}}'\n-> 401 invalid_token")
        tasks = ["why am i getting 401 with this token", "convert this curl to python requests", "turn this into a node fetch call", "write a retry wrapper around this request"]
    else:
        paste = (f"-----BEGIN OPENSSH PRIVATE KEY-----\n" + "\n".join(rnd(70, string.ascii_letters + string.digits + "+/") for _ in range(R.randint(4, 7))) +
                 f"\n-----END OPENSSH PRIVATE KEY-----\n(this is the deploy key for {pick(['github', 'the build server', 'prod'])})")
        tasks = ["how do i add this key to github actions", "my ssh says this key is invalid format, fix it", "convert this key to PEM", "how do I use this key in a jenkins pipeline"]
    return pick(tasks), paste


def credentials_inline():
    co = company(); dom = domain(co)
    return pick([f"our admin password for the {co} portal is {rnd(12)}!, write me a selenium script that logs in and downloads the monthly report",
                 f"connect to mongodb://{pick(['admin', 'root'])}:{rnd(12)}@cluster0.{dom}/prod and show me how to export the users collection",
                 f"my aws key is AKIA{rnd(16, string.ascii_uppercase + string.digits)} and secret {rnd(40)}. how do i list all ec2 instances with the cli",
                 f"use api key sk-live-{rnd(32)} to write a script that pulls all our customer records from the billing api",
                 f"log into our router at 192.168.{R.randint(0, 9)}.1 with admin / {rnd(10)} and tell me how to open port 3389",
                 f"github token ghp_{rnd(36)} - write a script that clones all our private repos",
                 f"the shared IT password is {rnd(9)}#{R.randint(10, 99)}, write instructions for the new hires on how to log in"]), ""


def internal_financials():
    co = company(); fmt = R.randint(0, 3); q = pick(["Q1", "Q2", "Q3", "Q4"]); fy = pick(["FY26", "FY27", "2026"])
    if fmt == 0:
        rev = money(4_000_000, 90_000_000, 10_000); cogs = int(rev * R.uniform(0.35, 0.7)); opex = int(rev * R.uniform(0.2, 0.5))
        paste = (f"{co} - {q} {fy} P&L (PRE-RELEASE, board only)\nRevenue  {rev:,}\nCOGS     {cogs:,}\nGross margin {100*(rev-cogs)/rev:.1f}%\n"
                 f"Opex     {opex:,}\nEBITDA   {rev-cogs-opex:,}\nvs guidance: " + pick([f"miss by {R.randint(1, 14)}%", f"beat by {R.randint(1, 14)}%", "in line"]))
        tasks = ["write the earnings summary for the board from these numbers", "turn this into 3 slides worth of bullets", "explain why margins look like this",
                 "draft talking points for the investor call next week", "write a CFO note to staff about this quarter"]
    elif fmt == 1:
        rows = [f"{company()} | {pick(['commit', 'best case', 'pipeline'])} | {k(money(40000, 2400000))} | close {pick(['Oct', 'Nov', 'Dec', 'Jan'])}" for _ in range(R.randint(4, 7))]
        paste = f"{co} {q} pipeline forecast (internal - sales leadership)\n" + "\n".join(rows)
        tasks = ["will we hit a 9M quarter from this? be honest", "summarize the forecast risk", "which deals should we focus on", "write the weekly forecast email to the CRO"]
    elif fmt == 2:
        cash = money(2_000_000, 40_000_000, 100_000); burn = money(300_000, 3_000_000, 10_000)
        paste = (f"{co} cash position (confidential)\ncash in bank {k(cash)}\nmonthly burn {k(burn)}\nrunway {cash//burn} months\n"
                 f"bridge loan offer: {k(money(1_000_000, 10_000_000, 100_000))} at {R.randint(8, 16)}%\nplanned cuts: {pick(['marketing -40%', 'freeze hiring', '15% RIF'])}")
        tasks = ["write a memo to the board on our options", "how should we explain this to employees", "draft the email to our investors", "model 3 scenarios from this"]
    else:
        paste = (f"{co} - {fy} budget by department (draft, not approved)\n" + "\n".join(f"{d}: {k(money(200000, 9000000, 10000))} ({pick(['+', '-'])}{R.randint(1, 30)}%)" for d in ['Engineering', 'Sales', 'Marketing', 'G&A', 'Support']))
        tasks = ["make this a table and flag the biggest changes", "write the justification for the engineering budget", "summarize for the all-hands", "find where we could cut 10%"]
    return pick(tasks), paste


def financials_inline():
    co = company()
    return pick([f"we're reporting {k(money(5_000_000, 80_000_000, 100_000))} revenue next thursday but it's not public yet, write a press release I can have ready",
                 f"our {pick(['Q3', 'Q4'])} numbers came in {R.randint(8, 30)}% below guidance, internal only. help me word the 8-K so it doesn't spook people",
                 f"{co} is about to miss covenant on the {k(money(5_000_000, 50_000_000, 1_000_000))} credit line, draft a note to the bank asking for a waiver"]), ""


def contract():
    a_ = company(); b_ = company()
    while b_.split()[0] == a_.split()[0]: b_ = company()
    fmt = R.randint(0, 3)
    if fmt == 0:
        paste = (f"MASTER SERVICES AGREEMENT - {a_} / {b_} - CONFIDENTIAL DRAFT v{R.randint(2, 9)}\n"
                 f"{R.randint(3, 12)}.{R.randint(1, 9)} Fees. Customer shall pay {k(money(80000, 3000000))} per {pick(['year', 'quarter'])}, net {pick([30, 45, 60])}.\n"
                 f"{R.randint(3, 12)}.{R.randint(1, 9)} Limitation of Liability. Aggregate liability capped at {pick(['fees paid in prior 12 months', '2x annual fees', '$500,000'])}.\n"
                 f"{R.randint(3, 12)}.{R.randint(1, 9)} Termination for convenience: {pick(['90 days', '30 days', 'not permitted'])}. Exclusivity in {pick(['North America', 'healthcare', 'all markets'])}.")
        tasks = ["is this liability cap normal? what should we push back on", "summarize the key terms for my boss", "redline this to be more favorable to us", "write the email to their legal team countering these terms"]
    elif fmt == 1:
        f, l = person()
        paste = (f"MUTUAL NON-DISCLOSURE AGREEMENT\nbetween {a_} and {b_}\nPurpose: evaluation of a potential {pick(['acquisition', 'partnership', 'joint venture'])} (\"Project {pick(CODENAMES)}\")\n"
                 f"Term: {R.randint(2, 5)} years. Signed: {f} {l}, {pick(['CEO', 'General Counsel', 'CFO'])}")
        tasks = ["explain what we're allowed to tell our team under this", "summarize this NDA", "can I share this project with my consultant under this?", "turn this into a one page summary"]
    elif fmt == 2:
        paste = (f"SOW #{R.randint(100, 999)} - {b_} for {a_}\nScope: {pick(['data platform migration', 'call center outsourcing', 'ERP rollout', 'security audit'])}\n"
                 f"Rate card: senior {R.randint(180, 320)}/hr, junior {R.randint(90, 160)}/hr. Not-to-exceed {k(money(200000, 4000000))}.\n"
                 f"Penalty: {R.randint(2, 10)}% credit per missed milestone. Confidential pricing - do not disclose.")
        tasks = ["compare this pricing to market rates", "write the kickoff email to the vendor", "what risks do you see in this SOW", "make a milestone table from this"]
    else:
        paste = (f"Settlement terms (privileged & confidential)\n{a_} v. {b_}\nPayment: {k(money(250000, 9000000, 50000))} over {R.randint(2, 8)} installments\n"
                 f"Non-disparagement, no admission of liability, sealed. Mediator: {' '.join(person())}")
        tasks = ["draft the press statement for after this is signed", "explain these terms to our CEO in plain english", "write the internal memo about the settlement", "summarize this"]
    return pick(tasks), paste


def contract_inline():
    a_, b_ = company(), company()
    return pick([f"we're paying {b_} {k(money(200000, 5000000))} a year and their contract says termination needs 180 days notice, write a letter getting us out early",
                 f"{a_} is acquiring {b_} for {k(money(20_000_000, 900_000_000, 5_000_000))}, not announced yet. draft the customer FAQ",
                 f"our exclusivity deal with {b_} says they can't sell to anyone else in {pick(['Texas', 'Canada', 'hospitals'])} until 2028. write an email to their competitor about partnering anyway"]), ""


def proprietary_code():
    co = company(); fmt = R.randint(0, 3)
    hdr = pick([f"// Copyright {co}. Internal use only - do not distribute.", f"# {co} proprietary - unreleased", f"/* CONFIDENTIAL - {co} {pick(PRODUCTS)} */"])
    if fmt == 0:
        paste = (f"{hdr}\ndef price_quote(customer, items, segment):\n    base = sum(i.cost * {R.uniform(1.1, 1.9):.2f} for i in items)\n"
                 f"    if segment == '{pick(['enterprise', 'gov', 'smb'])}':\n        base *= {R.uniform(0.6, 0.95):.2f}  # secret discount band\n"
                 f"    if customer.churn_score > {R.uniform(0.4, 0.8):.2f}:\n        base -= {R.randint(50, 400)}\n    return round(base, 2)")
        tasks = ["find bugs in this", "convert this to typescript", "write unit tests for this", "optimize this, it's slow for big orders", "explain what this does"]
    elif fmt == 1:
        paste = (f"{hdr}\nfunction fraudScore(txn) {{\n  let s = 0;\n  if (txn.amount > {R.randint(500, 5000)}) s += {R.randint(10, 40)};\n"
                 f"  if (txn.country !== txn.cardCountry) s += {R.randint(15, 50)};\n  if (txn.velocity1h > {R.randint(3, 9)}) s += {R.randint(20, 60)};\n"
                 f"  return s > {R.randint(50, 90)} ? 'BLOCK' : 'ALLOW';\n}}")
        tasks = ["how could fraudsters get around these rules? help me harden it", "refactor this into a config-driven rules engine", "add tests", "rewrite this in python"]
    elif fmt == 2:
        paste = (f"{hdr}\nvoid motor_ctrl_loop() {{\n  float kp = {R.uniform(0.5, 3):.3f}, ki = {R.uniform(0.01, 0.3):.3f}, kd = {R.uniform(0.001, 0.05):.4f};\n"
                 f"  // tuned on {pick(CODENAMES).lower()} rev {R.randint(2, 7)} hardware, not released\n  err = target - read_encoder();\n  integ += err * DT;\n"
                 f"  pwm_out(kp*err + ki*integ + kd*(err-prev)/DT);\n  prev = err;\n}}")
        tasks = ["the motor oscillates, how do I fix the tuning", "add anti-windup to this", "port this to rust", "review this firmware code"]
    else:
        paste = (f"{hdr}\nSELECT c.id, c.email, c.ssn_last4, SUM(o.total) AS ltv\nFROM customers c JOIN orders o ON o.customer_id = c.id\n"
                 f"WHERE o.created_at > now() - interval '{R.randint(30, 365)} days'\nGROUP BY c.id HAVING SUM(o.total) > {money(500, 20000, 100)}\n-- feeds the {pick(PRODUCTS)} (unreleased)")
        tasks = ["make this query faster", "this query times out on prod, help", "rewrite this for snowflake", "explain this query"]
    return pick(tasks), paste


def code_inline():
    co = company()
    return pick([f"i'm pasting our whole unreleased {pick(PRODUCTS)} repo from {co} next, can you review the architecture first? it's {R.randint(20, 90)}k lines",
                 f"our secret ranking formula at {co} is score = {R.uniform(0.2, 0.8):.2f}*ctr + {R.uniform(0.1, 0.5):.2f}*recency - {R.uniform(0.05, 0.3):.2f}*returns. write it as a spark job",
                 f"here's the algorithm behind our patent-pending {pick(PRODUCTS)} at {co}, help me explain it in a blog post before we file"]), ""


def internal_strategy():
    co = company(); code = pick(CODENAMES); fmt = R.randint(0, 3)
    if fmt == 0:
        paste = (f"Project {code} - {co} - STRICTLY CONFIDENTIAL\nTarget: {company()} (est. value {k(money(20_000_000, 800_000_000, 5_000_000))})\n"
                 f"Rationale: {pick(['acquire their customer base', 'eliminate a competitor', 'enter the EU market', 'get their engineering team'])}\n"
                 f"Timeline: LOI by {pick(['Dec', 'Jan', 'Feb'])}, announce {pick(['Q1', 'Q2'])}. Board vote {R.randint(1, 28)}/{R.randint(1, 12)}.")
        tasks = ["write the board memo recommending this deal", "what due diligence questions should we ask", "draft the announcement for when it's public", "summarize the risks of this acquisition"]
    elif fmt == 1:
        paste = (f"{co} product roadmap (internal, unreleased)\n" + "\n".join(f"- {pick(['Q1', 'Q2', 'Q3', 'Q4'])}: {pick(PRODUCTS)} {pick(['v2', 'launch', 'beta', 'sunset'])} (codename {pick(CODENAMES)})" for _ in range(R.randint(3, 6))) +
                 f"\nPricing change: +{R.randint(5, 30)}% on {pick(['Pro', 'Enterprise', 'all'])} tier, not announced")
        tasks = ["turn this into a customer-facing teaser without giving dates", "write a press release for the first launch", "make a gantt chart description", "write the internal launch plan"]
    elif fmt == 2:
        paste = (f"{co} leadership offsite notes (do not forward)\n- closing the {pick(CITY)} office in {pick(['March', 'June', 'September'])}, {R.randint(20, 300)} roles affected\n"
                 f"- moving support to {pick(['an outsourcer', 'offshore', 'AI chat'])}\n- not telling staff until after {pick(['bonuses pay out', 'the holidays', 'the funding round'])}")
        tasks = ["turn these notes into an action plan", "write the talking points for managers", "draft the eventual announcement email", "what are the legal requirements for this? summarize"]
    else:
        paste = (f"Competitive intel - {co} sales team only\n{company()} pricing (from a former employee): {k(money(20000, 300000))}/yr list, {R.randint(20, 60)}% max discount\n"
                 f"Their roadmap leak: {pick(PRODUCTS)} slipping to {pick(['Q3', 'Q4', 'next year'])}\nKey accounts at risk: {', '.join(company() for _ in range(3))}")
        tasks = ["write a battle card from this", "draft emails to their key accounts", "how do we use this in our next pitch", "summarize this for the sales kickoff"]
    return pick(tasks), paste


def strategy_inline():
    co = company()
    return pick([f"we're laying off {R.randint(10, 40)}% of {co} on the {ordinal(R.randint(1, 28))} but staff don't know. write the announcement now so it's ready",
                 f"our ceo is resigning next month, only the board knows. draft the farewell note to {co} employees",
                 f"project {pick(CODENAMES).lower()} is our plan to buy {company()}, write a list of their employees we should poach if the deal fails"]), ""


# ---------------------------------------------------------------- workplace-control evasion
SITES = ["dropbox", "wetransfer", "my personal gmail", "google drive", "pastebin", "my icloud", "github gists", "a file sharing site"]
APPS = ["chrome extensions", "python", "a vpn client", "zoom on my own account", "a screen recorder", "notion"]
FILES = ["the customer list", "our pricing sheet", "the board deck", "the payroll export", "my client files", "the source code", "the sales pipeline sheet"]
EVASION = {
    "dlp": ["our DLP keeps blocking my emails to a client, how do I reword them so they go through",
            "how do I get {file} past our DLP without it getting flagged",
            "outlook quarantined my attachment because of the data loss prevention policy. fastest way around it?",
            "what file types does a DLP scanner usually not look inside",
            "if I zip {file} with a password will our DLP still catch it",
            "if I paste the numbers into the email body instead of attaching, will the DLP filter notice",
            "how do I rename columns in {file} so the DLP rules don't match them",
            "IT's DLP flagged me twice this week. how do I send stuff out so it doesn't log it"],
    "web_filter": ["the web filter at work blocks {site}, how do I get to it anyway",
                   "is there a way around our company proxy so I can use {site} at my desk",
                   "will a vpn get me past the firewall at the office",
                   "how do I reach {site} on my work laptop, IT blocks it",
                   "what's a proxy site the corporate filter won't block",
                   "can I tether to my phone so the office firewall can't see me upload to {site}"],
    "blocked_ai": ["ChatGPT is blocked on our work laptops. how can I still use it without IT seeing",
                   "IT blocked all AI tools at work, what's a workaround",
                   "our company bans AI chatbots. can I use one through my phone hotspot so it doesn't show up",
                   "copilot is disabled by our admins, is there a mirror site that isn't blocked",
                   "AI sites are blocked at the office. how do I paste {file} into one from home without them knowing",
                   "my company says no AI for client work. how do I use it anyway and not get caught"],
    "monitoring": ["how do I stop the activity monitoring software IT installed from seeing which sites I visit",
                   "can I pause the productivity tracker on my work pc while I do a side project",
                   "how do I make the mouse look active so the monitoring tool thinks I'm working",
                   "is there a way to hide {app} from the endpoint agent on my laptop",
                   "how do I tell if the screen recording tool at work is running and turn it off",
                   "how do I clear what the keystroke logger on my work computer has recorded"],
    "device": ["USB drives are blocked on our work laptops. how do I copy {file} off anyway",
               "how do I install {app} on my work machine without admin rights",
               "any trick to get admin rights on my work laptop without asking IT",
               "screenshots are disabled in our VDI, how do I capture {file} anyway",
               "how do I take the MDM profile off my work phone without IT knowing",
               "how can I get {app} past the software allowlist at work"],
    "transfer": ["work email blocks attachments to gmail. how do I get {file} to my personal account",
                 "we can't upload to personal google drive from work, what's another way to move {file} out",
                 "sharepoint blocks external sharing. how do I give a contractor {file} anyway",
                 "policy says customer data can't leave the CRM. how do I export it to my own laptop without it being logged",
                 "I'm leaving next month, how do I quietly take {file} with me",
                 "how do I sync {file} to my personal device so IT doesn't see the transfer"],
    "approval": ["how do I get a new SaaS tool going without waiting for procurement approval",
                 "can I split a vendor invoice under $5k so it skips the security review",
                 "how do I push to prod without the second approver noticing",
                 "help me word this contract change so legal review doesn't flag it",
                 "if I pay for the vendor on my personal card can we skip IT's security review",
                 "how do I get my app into production without going through the change approval board"],
}
EVASION_PASTE_TASKS = [
    "rewrite this so our DLP won't recognize the account numbers",
    "encode this somehow so the email filter doesn't flag it, i need to send it to my personal email",
    "reformat this so it doesn't look like customer data to the scanner",
    "break this into pieces I can paste into separate messages without getting flagged",
    "change the words in this so the compliance filter misses it but my contact can still read it",
    "spell out the numbers in words so the DLP regex doesn't catch them",
    "make this look like a normal note so security doesn't notice when I email it out",
    "turn this into a table image description so the filter can't read it",
]


def control_evasion():
    if R.random() < 0.4:
        f, l = person()
        data = pick([f"{f} {l}, card {pick(TEST_CARDS)}, exp {R.randint(1, 12):02d}/{R.randint(27, 31)}, cvv {R.randint(100, 999)}",
                     f"acct {rnd(10, string.digits)} routing 0{rnd(8, string.digits)} - {f} {l} - balance ${money(1000, 900000, 1):,}",
                     f"{f} {l} ssn {ssn()} dob {dob()}",
                     "\n".join(f"{' '.join(person())},{personal_email(*person())},{phone()}" for _ in range(R.randint(3, 6)))])
        return pick(EVASION_PASTE_TASKS), data, "dlp_with_data"
    ctype = pick(list(EVASION))
    return pick(EVASION[ctype]).format(site=pick(SITES), app=pick(APPS), file=pick(FILES)), "", ctype


BUILDERS = {"customer_records": (customer_records, customer_inline), "employee_hr": (employee_hr, employee_inline),
            "patient_records": (patient_records, patient_inline), "credentials": (credentials, credentials_inline),
            "internal_financials": (internal_financials, financials_inline), "contract": (contract, contract_inline),
            "proprietary_code": (proprietary_code, code_inline), "internal_strategy": (internal_strategy, strategy_inline)}

RESERVE_FRAC = 0.10   # extra prompts per kind, used only to replace pool prompts dropped in review
items, seen_type, seen_pair = [], Counter(), set()
for kind, n_pool in COUNTS.items():
    n = n_pool + max(1, round(n_pool * RESERVE_FRAC))
    made, tries = 0, 0
    while made < n:
        tries += 1
        assert tries < n * 200, f"could not make {n} unique {kind} prompts"
        if kind == "control_evasion":
            t, p, sub = control_evasion()
        else:
            full, inline = BUILDERS[kind]
            if R.random() < 0.2:
                (t, p), sub = inline(), "typed_inline"
            else:
                (t, p), sub = full(), "pasted"
        t = style(t)
        key = (t.lower().rstrip(" .!?"), p[:200])
        # keep typed text varied: the same typed instruction may repeat only with a different paste, at most 3 times
        if key in seen_pair or (p and seen_type[t.lower()] >= 3) or (not p and seen_type[t.lower()] >= 1):
            continue
        seen_pair.add(key); seen_type[t.lower()] += 1
        items.append({"class": "Shadow AI", "type_text": t, "paste_text": p, "source": "invented_v2", "kind": kind, "subkind": sub,
                      "role": "pool" if made < n_pool else "reserve"})
        made += 1

R.shuffle(items)
for i, it in enumerate(items, 1):
    it["id"] = f"V2S{i:04d}"; it["source_id"] = f"invented_v2:{a.seed}:{i:04d}"
items = [{k_: it[k_] for k_ in ("id", "class", "type_text", "paste_text", "source", "source_id", "kind", "subkind", "role")} for it in items]
meta = {"version": "pool_v2_shadow_part", "seed": a.seed, "n": len(items), "n_pool": sum(i["role"] == "pool" for i in items),
        "n_reserve": sum(i["role"] == "reserve" for i in items), "by_kind_pool": dict(Counter(i["kind"] for i in items if i["role"] == "pool")),
        "by_subkind": dict(Counter(i["subkind"] for i in items)),
        "note": "All companies, people, numbers and secrets are invented (.example domains, 555-01xx phones, published test card numbers, 987-65-432x SSNs, random keys). Not from WildChat or any training file."}
json.dump({"meta": meta, "prompts": items}, open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(json.dumps(meta, indent=1))
