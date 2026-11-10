#!/usr/bin/env bash
# Password-protect the Prompt Study and Live Detector pages (and the data they send),
# leaving the home page open. Run on the server:  bash study/protect_site.sh
# Run it again any time to change the username or password. To remove protection:
#   bash study/protect_site.sh --remove
set -euo pipefail
CF="${CADDYFILE:-/etc/caddy/Caddyfile}"
BAK="$CF.bak.$(date +%s)"
sudo cp "$CF" "$BAK"

strip_old() {   # drop any earlier protection (ours, or a whole-site basic_auth block)
  sudo python3 - "$CF" <<'PY'
import re, sys
p = sys.argv[1]; s = open(p).read()
s = re.sub(r"[ \t]*# >>> promptgate-auth.*?# <<< promptgate-auth[^\n]*\n", "", s, flags=re.S)
s = re.sub(r"[ \t]*basic_?auth[^\n{]*\{[^}]*\}[ \t]*\n", "", s)
open(p, "w").write(s)
PY
}

if [ "${1:-}" = "--remove" ]; then
  strip_old; sudo caddy validate --config "$CF" >/dev/null 2>&1 && sudo systemctl reload caddy
  echo "Protection removed."; exit 0
fi

read -r -p "Username [study]: " U; U="${U:-study}"
read -r -s -p "Password: " P1; echo
read -r -s -p "Password again: " P2; echo
if [ -z "$P1" ] || [ "$P1" != "$P2" ]; then echo "Passwords are empty or do not match. Nothing changed."; exit 1; fi
HASH="$(caddy hash-password --plaintext "$P1")"; unset P1 P2

apply() {       # $1 = directive name (basic_auth on current Caddy, basicauth on older)
  strip_old
  sudo env DIRECTIVE="$1" AUTH_USER="$U" AUTH_HASH="$HASH" python3 - "$CF" <<'PY'
import os, sys
p = sys.argv[1]; s = open(p).read()
block = f"""    # >>> promptgate-auth (managed by study/protect_site.sh)
    @protected path */gateway */detector */pages/gateway.html */pages/detector.html */js/pages/gateway.js */js/pages/detector.js */prompt_bank.json */prompt */classify */feedback */consent
    {os.environ['DIRECTIVE']} @protected {{
        {os.environ['AUTH_USER']} {os.environ['AUTH_HASH']}
    }}
    # <<< promptgate-auth
"""
if "encode gzip" not in s:
    sys.exit("could not find 'encode gzip' in the Caddyfile")
s = s.replace("encode gzip\n", "encode gzip\n" + block, 1)
open(p, "w").write(s)
PY
  sudo caddy validate --config "$CF" >/dev/null 2>&1
}

if apply basic_auth || apply basicauth; then
  sudo systemctl reload caddy
  echo "Done. Prompt Study and Live Detector now need the login '$U'. The home page stays open."
else
  sudo cp "$BAK" "$CF"; echo "Caddy rejected the change; the previous configuration was restored."; exit 1
fi
