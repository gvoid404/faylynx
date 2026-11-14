#!/usr/bin/env python3
"""Admin back end for PromptGate AI (standard library only).

  * its own password (separate from the study login), with sign-in sessions and lock-out
  * overview of the collected data
  * model update: runs study/refine_models.py on this server, stores the result as a new
    model version and (optionally) makes it active
  * rollback: activate any earlier version, the newest one before a date, or the original models
  * prompt pool report and the study settings (how many prompts a participant enters)

Set or change the admin password on the server (it is never sent over the web to set it):
  python3 honeypot/admin.py set-password
"""
import getpass, hashlib, hmac, json, os, re, secrets, subprocess, sys, threading, time
from http.cookies import SimpleCookie
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_registry as reg

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
RUNTIME = reg.RUNTIME
CAPTURE_DIR = REPO / "captures"
AUTH_FILE = RUNTIME / "admin_auth.json"
SETTINGS_FILE = RUNTIME / "settings.json"
JOBS = RUNTIME / "jobs"
STATUS_FILE = JOBS / "update_status.json"
CORPUS = RUNTIME / "base_corpus.jsonl.gz"
BANK_FILE = HERE / "site" / "prompt_bank.json"
POOL_FILE = HERE / "prompt_pool.json"

COOKIE = "pg_admin"
SESSION_TTL = 8 * 3600
MAX_FAILS, LOCK_SECONDS = 5, 15 * 60
PBKDF2_ITERS = 310_000
MIN_PASSWORD = 8
DEFAULT_SETTINGS = {"default_quantity": 12, "min_quantity": 2, "max_quantity": 40, "participant_can_choose": True}

_lock = threading.Lock()
_sessions = {}          # token -> (expiry in epoch seconds, password-file stamp at sign-in)
_fails = {}             # client ip -> [epoch seconds of recent failures]
_job_lock = threading.Lock()
_stats_cache = {}       # file name -> ((mtime, size), summary)


# ------------------------------------------------------------------ password + sessions
def password_set():
    return AUTH_FILE.is_file()


def set_password(pw):
    if len(pw) < MIN_PASSWORD:
        raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, PBKDF2_ITERS)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    tmp = AUTH_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump({"algo": "pbkdf2_sha256", "iterations": PBKDF2_ITERS, "salt": salt.hex(),
                   "hash": digest.hex(), "set_at": reg.now_iso()}, f)
    os.chmod(tmp, 0o600); os.replace(tmp, AUTH_FILE)
    with _lock:
        _sessions.clear()                      # changing the password signs everyone out


def check_password(pw):
    try:
        d = json.load(open(AUTH_FILE))
        digest = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(d["salt"]), int(d["iterations"]))
        return hmac.compare_digest(digest, bytes.fromhex(d["hash"]))
    except (OSError, ValueError, KeyError):
        return False


def _client_ip(h):
    xff = h.headers.get("X-Forwarded-For", "")
    return xff.split(",")[0].strip() if xff else h.client_address[0]


def _locked_for(ip):
    now = time.time()
    with _lock:
        recent = [t for t in _fails.get(ip, []) if now - t < LOCK_SECONDS]
        _fails[ip] = recent
        if len(recent) >= MAX_FAILS:
            return int(LOCK_SECONDS - (now - recent[0])) + 1
    return 0


def _session_token(h):
    try:
        c = SimpleCookie(h.headers.get("Cookie", ""))
        return c[COOKIE].value if COOKIE in c else None
    except Exception:
        return None


def _authenticated(h):
    tok = _session_token(h)
    if not tok:
        return False
    now = time.time()
    with _lock:
        exp, stamp = _sessions.get(tok, (0, None))
        if exp > now and stamp == _auth_stamp():
            return True
        _sessions.pop(tok, None)
    return False


def _auth_stamp():
    """Changes whenever the password file is rewritten, which ends every open admin session."""
    try:
        return AUTH_FILE.stat().st_mtime_ns
    except OSError:
        return None


def _cookie_header(h, value, max_age):
    secure = "; Secure" if h.headers.get("X-Forwarded-Proto", "") == "https" else ""
    return f"{COOKIE}={value}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict{secure}"


# ------------------------------------------------------------------ small helpers
def _send(h, code, obj, extra_headers=()):
    out = json.dumps(obj).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", "application/json")
    h.send_header("Cache-Control", "no-store")
    h.send_header("Content-Length", str(len(out)))
    for k, v in extra_headers:
        h.send_header(k, v)
    h.end_headers()
    h.wfile.write(out)


def _body(h, limit=20_000):
    try:
        n = min(int(h.headers.get("Content-Length", "0")), limit)
        return json.loads(h.rfile.read(n).decode("utf-8") or "{}") if n else {}
    except (ValueError, OSError):
        return {}


def _read_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


# ------------------------------------------------------------------ study settings
def bank_counts():
    bank = _read_json(BANK_FILE, {"prompts": []})
    counts = {}
    for p in bank.get("prompts", []):
        counts[p["class"]] = counts.get(p["class"], 0) + 1
    return counts


def human_pool_size():
    c = bank_counts()
    return c.get("Allow", 0) + c.get("Shadow AI", 0)


def get_settings():
    s = dict(DEFAULT_SETTINGS); s.update(_read_json(SETTINGS_FILE, {}))
    pool = human_pool_size() or 120
    s["max_quantity"] = max(1, min(int(s["max_quantity"]), pool))
    s["min_quantity"] = max(1, min(int(s["min_quantity"]), s["max_quantity"]))
    s["default_quantity"] = max(s["min_quantity"], min(int(s["default_quantity"]), s["max_quantity"]))
    s["participant_can_choose"] = bool(s["participant_can_choose"])
    return s


def save_settings(new):
    pool = human_pool_size() or 120
    try:
        s = {"default_quantity": int(new["default_quantity"]), "min_quantity": int(new["min_quantity"]),
             "max_quantity": int(new["max_quantity"]), "participant_can_choose": bool(new["participant_can_choose"])}
    except (KeyError, TypeError, ValueError):
        raise ValueError("Not saved: default, fewest and most must be whole numbers.")
    if not (1 <= s["min_quantity"] <= s["default_quantity"] <= s["max_quantity"] <= pool):
        raise ValueError(f"Not saved: fewest, default and most must run from small to large, and all be between 1 and {pool} "
                         "(the number of Allow and Shadow AI prompts in the pool).")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    json.dump(s, open(tmp, "w"), indent=1); os.replace(tmp, SETTINGS_FILE)
    return get_settings()


def public_study_config():
    """What the Prompt Study page needs (no secrets)."""
    s = get_settings(); c = bank_counts()
    return {**s, "pool": {"Allow": c.get("Allow", 0), "Shadow AI": c.get("Shadow AI", 0)}}


# ------------------------------------------------------------------ collected-data overview
def _role(token):
    if re.fullmatch(r"P\d{2}", token): return "human"
    if token.startswith("AG-"): return "agent"
    return "other"


def _prompt_file_summary(path):
    """Small per-file summary of a <TOKEN>_prompt.jsonl (cached by mtime + size)."""
    st = path.stat(); key = (st.st_mtime, st.st_size)
    hit = _stats_cache.get(path.name)
    if hit and hit[0] == key:
        return hit[1]
    entries = []
    for line in open(path, encoding="utf-8", errors="ignore"):
        if not line.strip():
            continue
        try:
            b = json.loads(json.loads(line)["body"])
        except (ValueError, KeyError, TypeError):
            continue
        entries.append((b.get("prompt_id"), b.get("target_class"), bool(b.get("skipped")) or not (b.get("prompt") or "").strip()))
    summary = {"entries": entries, "mtime": st.st_mtime}
    _stats_cache[path.name] = (key, summary)
    return summary


def _line_count(path):
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def collect_stats():
    roles = {"human": {"entries": 0, "skipped": 0, "by_class": {}, "tokens": set(), "prompt_ids": set()},
             "agent": {"entries": 0, "skipped": 0, "by_class": {}, "tokens": set(), "prompt_ids": set()},
             "other": {"entries": 0, "skipped": 0, "by_class": {}, "tokens": set(), "prompt_ids": set()}}
    per_participant, usage, last = {}, {}, 0.0
    detector = feedback = consents = 0
    if CAPTURE_DIR.is_dir():
        for p in CAPTURE_DIR.iterdir():
            name = p.name
            if not name.endswith(".jsonl"):
                continue
            try:
                last = max(last, p.stat().st_mtime)
            except OSError:
                continue
            if name.endswith("_prompt.jsonl"):
                token = name[:-len("_prompt.jsonl")]; role = _role(token); r = roles[role]
                s = _prompt_file_summary(p)
                for pid, cls, skipped in s["entries"]:
                    if skipped:
                        r["skipped"] += 1; continue
                    r["entries"] += 1; r["tokens"].add(token); r["prompt_ids"].add(pid)
                    r["by_class"][cls] = r["by_class"].get(cls, 0) + 1
                    if role != "other" and pid:
                        u = usage.setdefault(pid, {"human": 0, "agent": 0}); u[role] += 1
                if role == "human":
                    done = sum(1 for e in s["entries"] if not e[2])
                    per_participant[token] = {"token": token, "entries": done, "last": _iso(s["mtime"])}
            elif name.endswith("_classify.jsonl"):
                detector += _line_count(p)
            elif name.endswith("_feedback.jsonl"):
                feedback += _line_count(p)
            elif name.endswith("_consent.jsonl"):
                consents += 1
    out = {k: {"entries": v["entries"], "skipped": v["skipped"], "by_class": v["by_class"],
               "links": len(v["tokens"]), "distinct_prompts": len(v["prompt_ids"] - {None})} for k, v in roles.items()}
    return {"roles": out, "participants": sorted(per_participant.values(), key=lambda x: x["token"]),
            "detector_uses": detector, "detector_feedback": feedback, "consents": consents,
            "last_activity": _iso(last) if last else None, "usage": usage}


def overview():
    s = collect_stats(); s.pop("usage", None)
    act = reg.active_id()
    meta = next((m for m in reg.list_versions() if m["version_id"] == act), {})
    return {**s, "active_model": {"version_id": act, "created_at": meta.get("created_at"), "kind": meta.get("kind")},
            "settings": get_settings(), "environment": environment()}


def pool_report():
    pool = _read_json(POOL_FILE, {}); stats = collect_stats(); usage = stats["usage"]
    bank = _read_json(BANK_FILE, {"prompts": []})
    per_class = {}
    for p in bank.get("prompts", []):
        c = per_class.setdefault(p["class"], {"in_bank": 0, "entered_by_humans": 0, "entered_by_agents": 0,
                                               "human_entries": 0, "agent_entries": 0})
        c["in_bank"] += 1
        u = usage.get(p["id"], {})
        c["entered_by_humans"] += 1 if u.get("human") else 0
        c["entered_by_agents"] += 1 if u.get("agent") else 0
        c["human_entries"] += u.get("human", 0); c["agent_entries"] += u.get("agent", 0)
    return {"pool": pool, "collected": per_class, "human_pool_size": human_pool_size(),
            "agent_pool_size": sum(bank_counts().values()), "settings": get_settings()}


# ------------------------------------------------------------------ model update job
def training_python():
    for cand in (os.environ.get("PROMPTGATE_TRAIN_PYTHON"), str(RUNTIME / "venv" / "bin" / "python")):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def environment():
    return {"training_ready": training_python() is not None, "corpus_present": CORPUS.is_file(),
            "setup_command": "bash study/server_setup_training.sh",
            "corpus_path": "runtime/base_corpus.jsonl.gz"}


def _pid_alive(pid):
    try:
        os.kill(int(pid), 0); return True
    except (OSError, TypeError, ValueError):
        return False


def _write_status(st):
    JOBS.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_FILE.with_suffix(".tmp")
    json.dump(st, open(tmp, "w"), indent=1); os.replace(tmp, STATUS_FILE)


def update_status():
    st = _read_json(STATUS_FILE, {"state": "idle"})
    if st.get("state") == "running" and not _job_lock.locked() and not _pid_alive(st.get("pid")):
        st.update(state="failed", message="The update was interrupted (the service restarted). Run it again.",
                  finished_at=reg.now_iso())
        _write_status(st)
    log = ""
    if st.get("log"):
        try:
            log = "\n".join(open(st["log"], encoding="utf-8", errors="ignore").read().splitlines()[-40:])
        except OSError:
            pass
    return {**{k: v for k, v in st.items() if k not in ("log", "pid")}, "log_tail": log, "environment": environment()}


def start_update(activate=True):
    py = training_python()
    if not py:
        raise RuntimeError("The training environment is not installed on this server yet. Run: bash study/server_setup_training.sh")
    if not _job_lock.acquire(blocking=False):
        raise RuntimeError("A model update is already running.")
    job_id = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    jobdir = JOBS / job_id; jobdir.mkdir(parents=True, exist_ok=True)
    st = {"state": "running", "job_id": job_id, "started_at": reg.now_iso(), "activate": bool(activate),
          "content_retrained": CORPUS.is_file(), "log": str(jobdir / "update.log")}
    _write_status(st)
    threading.Thread(target=_run_update, args=(py, jobdir, st), daemon=True).start()
    return job_id


def _run_update(py, jobdir, st):
    try:
        cmd = [py, str(REPO / "study" / "refine_models.py"), "--captures", str(CAPTURE_DIR),
               "--out", str(jobdir / "models"), "--report", str(jobdir / "report.json"), "--work", str(jobdir / "work")]
        cmd += ["--corpus", str(CORPUS)] if CORPUS.is_file() else ["--actor-only"]
        with open(st["log"], "w", encoding="utf-8") as logf:
            proc = subprocess.Popen(cmd, cwd=str(REPO / "study"), stdout=logf, stderr=subprocess.STDOUT,
                                    env={**os.environ, "PYTHONWARNINGS": "ignore"})
            st["pid"] = proc.pid; _write_status(st)
            try:
                rc = proc.wait(timeout=3600)
            except subprocess.TimeoutExpired:
                proc.kill(); rc = -9
        report = _read_json(jobdir / "report.json", {})
        if rc == 0:
            note = "Model update from collected data" + ("" if st["content_retrained"] else " (behavior model only)")
            vid = reg.register(jobdir / "models", {"note": note, "report": report, "content_retrained": st["content_retrained"]})
            if st["activate"]:
                reg.activate(vid, note="model update")
            st.update(state="done", version_id=vid, activated=bool(st["activate"]), report=report,
                      message="New version " + vid + (" is now active." if st["activate"] else " was saved but is not active."))
        elif rc == 3:
            st.update(state="failed", report=report, message=report.get("error") or "Not enough collected data yet.")
        else:
            st.update(state="failed", message=f"The update stopped with an error (code {rc}). See the log below.")
        for sub in ("models", "work"):
            _rmtree(jobdir / sub)
    except Exception as e:                                   # noqa: BLE001
        st.update(state="failed", message=f"{type(e).__name__}: {e}")
    finally:
        st["finished_at"] = reg.now_iso(); st.pop("pid", None)
        _write_status(st)
        _job_lock.release()


def _rmtree(path):
    import shutil
    shutil.rmtree(path, ignore_errors=True)


# ------------------------------------------------------------------ HTTP entry point
def handle(h, method, sub):
    """Called by the web server for /admin/... requests. Always sends a response."""
    try:
        return _route(h, method, sub)
    except Exception as e:                                   # noqa: BLE001
        return _send(h, 500, {"error": f"{type(e).__name__}: {e}"})


def _route(h, method, sub):
    if method == "GET" and sub == "/admin/api/session":
        return _send(h, 200, {"password_set": password_set(), "authenticated": _authenticated(h),
                              "locked_for": _locked_for(_client_ip(h))})

    if method == "POST" and sub == "/admin/login":
        ip = _client_ip(h)
        if not password_set():
            return _send(h, 503, {"error": "No admin password has been set on the server yet."})
        wait = _locked_for(ip)
        if wait:
            return _send(h, 429, {"error": f"Too many wrong passwords. Try again in {wait // 60 + 1} minutes."})
        pw = str(_body(h).get("password", ""))
        if not check_password(pw):
            time.sleep(0.4)
            with _lock:
                _fails.setdefault(ip, []).append(time.time()); left = MAX_FAILS - len(_fails[ip])
            return _send(h, 401, {"error": "Wrong password.", "attempts_left": max(left, 0)})
        tok = secrets.token_urlsafe(32)
        with _lock:
            now = time.time()
            for k in [k for k, (exp, _) in _sessions.items() if exp < now]:
                _sessions.pop(k, None)
            _sessions[tok] = (now + SESSION_TTL, _auth_stamp()); _fails.pop(ip, None)
        return _send(h, 200, {"ok": True}, [("Set-Cookie", _cookie_header(h, tok, SESSION_TTL))])

    if method == "POST" and sub == "/admin/logout":
        tok = _session_token(h)
        with _lock:
            _sessions.pop(tok, None)
        return _send(h, 200, {"ok": True}, [("Set-Cookie", _cookie_header(h, "", 0))])

    # everything below needs a signed-in admin
    if not _authenticated(h):
        return _send(h, 401, {"error": "Sign in to the admin page first."})
    if method == "POST" and h.headers.get("X-PG-Admin") != "1":
        return _send(h, 403, {"error": "Request refused."})          # blocks cross-site form posts

    if method == "GET":
        if sub == "/admin/api/overview": return _send(h, 200, overview())
        if sub == "/admin/api/models":
            return _send(h, 200, {"versions": list(reversed(reg.list_versions())), "active": reg.active_id(),
                                  "activations": list(reversed(reg.activations(15)))})
        if sub == "/admin/api/update/status": return _send(h, 200, update_status())
        if sub == "/admin/api/pool": return _send(h, 200, pool_report())
        if sub == "/admin/api/settings": return _send(h, 200, get_settings())
        return _send(h, 404, {"error": "Unknown admin address."})

    body = _body(h)
    if sub == "/admin/api/settings":
        try:
            return _send(h, 200, {"ok": True, "settings": save_settings(body)})
        except ValueError as e:
            return _send(h, 400, {"error": str(e)})
    if sub == "/admin/api/models/activate":
        vid = str(body.get("version_id", ""))
        if not reg.exists(vid):
            return _send(h, 400, {"error": "Unknown model version."})
        reg.activate(vid, note="chosen on the admin page")
        return _send(h, 200, {"ok": True, "active": reg.active_id()})
    if sub == "/admin/api/models/rollback":
        to = str(body.get("to", ""))
        if to == "baseline":
            reg.activate("baseline", note="rolled back to the original models")
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", to):
            reg.rollback_to(to)
        else:
            return _send(h, 400, {"error": "Give a date, or 'baseline'."})
        return _send(h, 200, {"ok": True, "active": reg.active_id()})
    if sub == "/admin/api/update/start":
        try:
            return _send(h, 200, {"ok": True, "job_id": start_update(activate=bool(body.get("activate", True)))})
        except RuntimeError as e:
            return _send(h, 409, {"error": str(e)})
    return _send(h, 404, {"error": "Unknown admin address."})


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "set-password":
        p1 = getpass.getpass("New admin password (at least %d characters): " % MIN_PASSWORD)
        p2 = getpass.getpass("Again: ")
        if p1 != p2:
            sys.exit("The two entries do not match. Nothing changed.")
        try:
            set_password(p1)
        except ValueError as e:
            sys.exit(str(e))
        print("Admin password saved. Anyone signed in to the admin page has been signed out.")
    else:
        print(__doc__)
