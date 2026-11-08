#!/usr/bin/env python3
"""Honeypot server (capture-plus) — drop-in replacement for server.py that additionally records
a lightweight network/connection fingerprint on every POST, for the API-surface path of the study.

Same routes and capture files as server.py:
  GET  /<VERSION>/...          serve files from site/
  POST /<VERSION>/<endpoint>   append to captures/<VERSION>_<endpoint>.jsonl

Added to each capture record (best effort; empty when not present):
  client_ip, and from the request headers: User-Agent, Accept-Language, Accept-Encoding, Accept,
  Connection, and the Client Hints Sec-CH-UA* . When the server runs behind a TLS terminator
  (Caddy) that forwards TLS details, any X-TLS-* and X-Forwarded-* headers are captured too — see
  the deploy runbook for the Caddy config that adds X-TLS-Version / X-TLS-Cipher / X-JA4 headers.

Usage:  python server_plus.py [port] [bind]        default: 8781 127.0.0.1
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
MIME = {".html": "text/html", ".css": "text/css", ".js": "application/javascript",
        ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg",
        ".svg": "image/svg+xml", ".ico": "image/x-icon", ".txt": "text/plain", ".pdf": "application/pdf"}

# headers that make up the lightweight network fingerprint
NET_HEADERS = ["User-Agent", "Accept-Language", "Accept-Encoding", "Accept", "Connection",
               "Sec-CH-UA", "Sec-CH-UA-Mobile", "Sec-CH-UA-Platform", "Sec-CH-UA-Platform-Version",
               "Sec-Fetch-Site", "Sec-Fetch-Mode", "DNT",
               # forwarded by Caddy when deployed behind TLS (see runbook):
               "X-Forwarded-For", "X-Forwarded-Proto", "X-TLS-Version", "X-TLS-Cipher", "X-JA4", "X-JA3"]

_locks_guard = threading.Lock()
_capture_locks = defaultdict(threading.Lock)


def _lock_for(path):
    with _locks_guard:
        return _capture_locks[str(path)]


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.command}] {self.path} -> {args[1]}\n")

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
            "net": self._net(),                      # <-- lightweight network fingerprint
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
        print(f"Honeypot (capture-plus) on http://{bind}:{port}/<VERSION>/")
        print(f"Captures: {CAPTURE_DIR}")
        srv.serve_forever()
