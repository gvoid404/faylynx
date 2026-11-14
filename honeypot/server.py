#!/usr/bin/env python3
"""Honeypot web server with behavioral capture.

Routes
  GET  /<VERSION>/...          serve files from site/ (single-page app fallback)
  POST /<VERSION>/<endpoint>   append the request to captures/<VERSION>_<endpoint>.jsonl

VERSION is a per-session token ([A-Z0-9_-]{1,32}). It keeps sessions apart in
the capture files and prevents an agent from reusing cached pages across runs.

Usage
  python server.py [port] [bind]        default: 8781 127.0.0.1
"""
import http.server
import json
import re
import socketserver
import sys
import threading
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE / "site"
CAPTURE_DIR = HERE.parent / "captures"
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

VERSION_RE = re.compile(r"^/([A-Z0-9_\-]{1,32})(/.*)?$")

MIME = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".txt": "text/plain",
}

# One lock per capture file, so concurrent requests of the same session never
# interleave within a line, while different sessions write in parallel.
_locks_guard = threading.Lock()
_capture_locks = defaultdict(threading.Lock)


def _lock_for(path: Path) -> threading.Lock:
    with _locks_guard:
        return _capture_locks[str(path)]


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.command}] {self.path} -> {args[1]}\n")

    def do_GET(self):
        m = VERSION_RE.match(self.path.split("?")[0])
        if not m:
            return self._404()
        sub = m.group(2) or ""
        if not sub.startswith("/"):
            return self._404()

        candidate = ROOT / sub.lstrip("/")
        if candidate.is_file():
            return self._serve_file(candidate)

        if sub.startswith("/pages/"):
            page_file = ROOT / "pages" / (sub[len("/pages/"):] + ".html")
            if page_file.is_file():
                return self._serve_file(page_file)

        # Single-page app: unknown HTML routes load index.html; missing assets are 404.
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
        endpoint = sub[1:]

        body = b""
        if "Content-Length" in self.headers:
            try:
                body = self.rfile.read(int(self.headers["Content-Length"]))
            except (ValueError, OSError):
                body = b""

        capture_path = CAPTURE_DIR / f"{version}_{endpoint}.jsonl"
        record = {
            "ts": self.log_date_time_string(),
            "remote": self.client_address[0],
            "endpoint": endpoint,
            "version": version,
            "ua": self.headers.get("User-Agent", ""),
            "x_source": self.headers.get("X-Source", ""),
            "body": body.decode("utf-8", errors="ignore"),
        }
        try:
            with _lock_for(capture_path), open(capture_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as e:
            sys.stderr.write(f"capture write failed: {e}\n")

        out = b"Success"
        self.send_response(200)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def _serve_file(self, fp: Path):
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
        print(f"Honeypot on http://{bind}:{port}/<VERSION>/")
        print(f"Captures: {CAPTURE_DIR}")
        srv.serve_forever()
