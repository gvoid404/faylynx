#!/usr/bin/env python3
"""PromptGate AI web server (capture-plus). Standard library only.

Routes (every address starts with a link token, /<TOKEN>/..., TOKEN = [A-Z0-9_-]{1,32})
  GET  /<TOKEN>/...                 pages and files from site/ (single-page app fallback)
  GET  /<TOKEN>/study_config        how many prompts the study page offers (set on the Admin page)
  GET  /<TOKEN>/logout              answers 401 so the browser forgets the site login
  POST /<TOKEN>/<endpoint>          append the request to captures/<TOKEN>_<endpoint>.jsonl
                                    (mm, prompt, consent, end, feedback, ...)
  POST /<TOKEN>/classify            Live Detector: run the active models, log input + answer
  GET|POST /<TOKEN>/admin/...       admin sign-in and admin API (see admin.py)

Each capture record also holds a lightweight network fingerprint: client IP and the request
headers User-Agent, Accept-*, Client Hints, plus X-TLS-* / X-Forwarded-* when Caddy forwards them.

Usage:  python server_plus.py [port] [bind]        default: 8781 127.0.0.1
"""
import http.server
import json
import re
import socketserver
import sys
import threading
import uuid
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import admin

HERE = Path(__file__).resolve().parent
ROOT = (HERE / "site").resolve()
CAPTURE_DIR = HERE.parent / "captures"
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

VERSION_RE = re.compile(r"^/([A-Z0-9_\-]{1,32})(/.*)?$")
ENDPOINT_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")          # capture endpoints are single plain words
MIME = {".html": "text/html", ".css": "text/css", ".js": "application/javascript",
        ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg",
        ".svg": "image/svg+xml", ".ico": "image/x-icon", ".txt": "text/plain", ".pdf": "application/pdf"}

# headers that make up the lightweight network fingerprint
NET_HEADERS = ["User-Agent", "Accept-Language", "Accept-Encoding", "Accept", "Connection",
               "Sec-CH-UA", "Sec-CH-UA-Mobile", "Sec-CH-UA-Platform", "Sec-CH-UA-Platform-Version",
               "Sec-Fetch-Site", "Sec-Fetch-Mode", "DNT",
               # forwarded by Caddy when deployed behind TLS:
               "X-Forwarded-For", "X-Forwarded-Proto", "X-TLS-Version", "X-TLS-Cipher", "X-JA4", "X-JA3"]

_locks_guard = threading.Lock()
_capture_locks = defaultdict(threading.Lock)


def _lock_for(path):
    with _locks_guard:
        return _capture_locks[str(path)]


def site_file(sub):
    """Path of a file under site/ for the URL part `sub`, or None. Refuses anything that would
    leave the site folder (.. segments, backslashes), so only published files can be read."""
    rel = sub.lstrip("/")
    if not rel or "\\" in rel or "\x00" in rel or any(part in ("..", ".") for part in rel.split("/")):
        return None
    cand = (ROOT / rel).resolve()
    try:
        cand.relative_to(ROOT)
    except ValueError:
        return None
    return cand if cand.is_file() else None


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.command}] {self.path.split('?')[0]} -> {args[1]}\n")

    def _net(self):
        fp = {}
        for h in NET_HEADERS:
            v = self.headers.get(h)
            if v:
                fp[h] = v
        # real client IP: prefer the left-most X-Forwarded-For hop, else the socket peer
        xff = self.headers.get("X-Forwarded-For", "")
        fp["client_ip"] = (xff.split(",")[0].strip() if xff else self.client_address[0])
        return fp

    def _json(self, code, obj, extra=()):
        out = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(out)))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        m = VERSION_RE.match(self.path.split("?")[0])
        if not m:
            return self._404()
        sub = m.group(2) or ""
        if not sub.startswith("/") or ".." in sub.split("/"):
            return self._404()
        if sub.startswith("/admin/api/"):
            return admin.handle(self, "GET", sub)
        if sub == "/study_config":
            return self._json(200, admin.public_study_config())
        if sub == "/logout":            # makes the browser forget the site login (see index.html)
            body = b"Logged out"
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="restricted"')
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        fp = site_file(sub)
        if fp:
            return self._serve_file(fp)
        if sub.startswith("/pages/"):
            fp = site_file("/pages/" + sub[len("/pages/"):] + ".html")
            if fp:
                return self._serve_file(fp)
        last_segment = sub.rsplit("/", 1)[-1]
        if "." in last_segment and last_segment.rsplit(".", 1)[-1].lower() not in ("html", "htm"):
            return self._404()
        return self._serve_file(ROOT / "index.html")

    def do_POST(self):
        m = VERSION_RE.match(self.path.split("?")[0])
        if not m:
            return self._404()
        version, sub = m.group(1), m.group(2) or ""
        if not sub.startswith("/"):
            return self._404()
        if sub.startswith("/admin/"):   # handled separately: admin requests are never written to captures
            return admin.handle(self, "POST", sub)
        endpoint = sub[1:]
        if not ENDPOINT_RE.match(endpoint):
            return self._404()
        body = b""
        if "Content-Length" in self.headers:
            try:
                body = self.rfile.read(min(int(self.headers["Content-Length"]), 4_000_000))
            except (ValueError, OSError):
                body = b""
        result = None
        if endpoint == "classify":          # live detector: run the models, log input + result
            try:
                import inference
                req = json.loads(body.decode("utf-8", errors="ignore") or "{}")
                result = inference.analyze(req.get("prompt", ""), req.get("events", []))
            except Exception as e:  # noqa: BLE001
                result = {"error": f"{type(e).__name__}: {e}"}
            result["request_id"] = uuid.uuid4().hex[:12]
        capture_path = CAPTURE_DIR / f"{version}_{endpoint}.jsonl"
        record = {
            "ts": self.log_date_time_string(),
            "remote": self.client_address[0],
            "endpoint": endpoint,
            "version": version,
            "ua": self.headers.get("User-Agent", ""),
            "x_source": self.headers.get("X-Source", ""),
            "net": self._net(),                      # <-- lightweight network fingerprint
            "body": body.decode("utf-8", errors="ignore"),
        }
        if result is not None:
            record["result"] = result
        try:
            with _lock_for(capture_path), open(capture_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as e:
            sys.stderr.write(f"capture write failed: {e}\n")
        out = b"Success" if result is None else json.dumps(result).encode("utf-8")
        self.send_response(200)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "text/plain" if result is None else "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def _serve_file(self, fp):
        data = fp.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(fp.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _404(self):
        body = (ROOT / "404.html").read_bytes()
        self.send_response(404)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8781
    bind = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    with Server((bind, port), Handler) as srv:
        print(f"PromptGate AI (capture-plus) on http://{bind}:{port}/<TOKEN>/")
        print(f"Captures: {CAPTURE_DIR}")
        srv.serve_forever()
