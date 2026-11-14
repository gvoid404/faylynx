#!/usr/bin/env python3
"""Model versions for the Live Detector, with rollback.

  baseline   the two model files shipped in the repository (honeypot/models/). Never modified.
  versions   every model update is stored under runtime/models/versions/<id>/ with a meta.json
             (id = UTC date-time of the update, e.g. 20261113-221005).
  active     runtime/models/active.json names the version the detector uses. No file, or a
             missing version, means the baseline.

Everything under runtime/ is server-local and git-ignored, so `git pull` never touches it.

Command line (run on the server, from the repository root):
  python3 honeypot/model_registry.py list
  python3 honeypot/model_registry.py activate <id|baseline>
  python3 honeypot/model_registry.py rollback-to <YYYY-MM-DD>
  python3 honeypot/model_registry.py import <content_model.json> <actor_model.json> [note]
"""
import json, os, re, shutil, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASELINE_DIR = HERE / "models"
RUNTIME = Path(os.environ.get("PROMPTGATE_RUNTIME") or (REPO / "runtime"))
STORE = RUNTIME / "models"
VERSIONS = STORE / "versions"
ACTIVE = STORE / "active.json"
ACTIVATIONS = STORE / "activations.jsonl"
FILES = ("content_model.json", "actor_model.json")
ID_RE = re.compile(r"^\d{8}-\d{6}(-\d+)?$")
_baseline_cache = {}


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_atomic(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def _summarize(folder):
    """Small facts about a pair of model files (read once, at registration)."""
    c = _read(Path(folder) / "content_model.json", {}) or {}
    a = _read(Path(folder) / "actor_model.json", {}) or {}
    return {"content": {"tag": c.get("tag"), "created_at": c.get("created_at"), "n_train": c.get("n_train"),
                        "cv5_macro_f1": c.get("cv5_macro_f1"),
                        "bank_acc": c.get("bank_acc") or c.get("bank_holdout_acc"),
                        "bank_held_out": c.get("bank_held_out", "bank_holdout_acc" in c)},
            "actor": {"tag": a.get("tag"), "created_at": a.get("created_at"), "n_train": a.get("n_train"),
                      "n_agent": a.get("n_agent"), "cv5_acc": a.get("cv5_acc")}}


def exists(vid):
    if vid == "baseline":
        return all((BASELINE_DIR / f).is_file() for f in FILES)
    return bool(ID_RE.match(vid or "")) and all((VERSIONS / vid / f).is_file() for f in FILES)


def active_id():
    vid = (_read(ACTIVE, {}) or {}).get("version_id", "baseline")
    return vid if vid != "baseline" and exists(vid) else "baseline"


def active_dir():
    vid = active_id()
    return BASELINE_DIR if vid == "baseline" else VERSIONS / vid


def baseline_meta():
    key = tuple((BASELINE_DIR / f).stat().st_mtime for f in FILES)
    if _baseline_cache.get("key") != key:
        s = _summarize(BASELINE_DIR)
        _baseline_cache.update(key=key, meta={
            "version_id": "baseline", "kind": "baseline", "label": "Original models",
            "created_at": s["content"].get("created_at") or s["actor"].get("created_at"),
            "note": "Shipped with the site; trained before any live data was collected.", **s})
    return dict(_baseline_cache["meta"])


def list_versions():
    """Baseline first, then updates oldest to newest. Each entry has 'active': bool."""
    out = [baseline_meta()]
    if VERSIONS.is_dir():
        metas = []
        for d in VERSIONS.iterdir():
            if d.is_dir() and exists(d.name):
                m = _read(d / "meta.json", {}) or {}
                m.setdefault("version_id", d.name); m.setdefault("kind", "update")
                m.setdefault("created_at", None)
                metas.append(m)
        out += sorted(metas, key=lambda m: (m.get("created_at") or "", m["version_id"]))
    act = active_id()
    for m in out:
        m["active"] = (m["version_id"] == act)
    return out


def register(src_dir, meta=None):
    """Store a new version from a folder holding the two model files. Returns its id."""
    src = Path(src_dir)
    for f in FILES:
        if not (src / f).is_file():
            raise FileNotFoundError(f"{f} missing in {src}")
        json.load(open(src / f, encoding="utf-8"))        # must be valid JSON
    base = time.strftime("%Y%m%d-%H%M%S", time.gmtime()); vid = base; n = 1
    while (VERSIONS / vid).exists():
        n += 1; vid = f"{base}-{n}"
    dest = VERSIONS / vid; dest.mkdir(parents=True)
    for f in FILES:
        shutil.copyfile(src / f, dest / f)
    m = {"version_id": vid, "kind": "update", "created_at": now_iso(), **_summarize(dest)}
    m.update(meta or {})
    _write_atomic(dest / "meta.json", m)
    return vid


def activate(vid, note=""):
    if not exists(vid):
        raise ValueError(f"unknown model version: {vid}")
    prev = active_id()
    _write_atomic(ACTIVE, {"version_id": vid, "activated_at": now_iso(), "note": note})
    with open(ACTIVATIONS, "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": now_iso(), "from": prev, "to": vid, "note": note}) + "\n")
    return vid


def rollback_to(when_iso):
    """Activate the newest version created at or before `when_iso` (UTC, e.g. 2026-11-13T23:59:59Z).
    If no update is that old, this is the baseline."""
    cands = [m for m in list_versions() if m["version_id"] != "baseline" and (m.get("created_at") or "9") <= when_iso]
    vid = cands[-1]["version_id"] if cands else "baseline"
    return activate(vid, note=f"rolled back to {when_iso}")


def activations(limit=20):
    try:
        lines = open(ACTIVATIONS, encoding="utf-8").read().splitlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        try: out.append(json.loads(line))
        except ValueError: pass
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        for m in list_versions():
            print(("* " if m["active"] else "  ") + f"{m['version_id']:18s} {m.get('created_at') or '':22s} {m.get('note') or m.get('label') or ''}")
    elif cmd == "activate" and len(sys.argv) > 2:
        print("active:", activate(sys.argv[2], note="command line"))
    elif cmd == "rollback-to" and len(sys.argv) > 2:
        print("active:", rollback_to(sys.argv[2] + "T23:59:59Z"))
    elif cmd == "import" and len(sys.argv) > 3:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            shutil.copyfile(sys.argv[2], Path(td) / FILES[0]); shutil.copyfile(sys.argv[3], Path(td) / FILES[1])
            vid = register(td, {"note": " ".join(sys.argv[4:]) or "imported from files"})
        print("registered", vid, "- activate it with: python3 honeypot/model_registry.py activate", vid)
    else:
        print(__doc__)
