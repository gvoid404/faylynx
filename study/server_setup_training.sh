#!/usr/bin/env bash
# One-time setup on the server so the Admin page can run model updates.
# Installs the training libraries into runtime/venv (kept apart from the system Python).
#   cd ~/browsing-agent-honeypot && bash study/server_setup_training.sh
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$REPO/runtime/venv"
FREE_MB=$(df -Pm "$REPO" | awk 'NR==2 {print $4}')
if [ "${FREE_MB:-0}" -lt 1500 ]; then
  echo "Only ${FREE_MB} MB of disk space is free; about 1500 MB is needed. Free some space or grow the disk, then run this again."
  exit 1
fi
if ! python3 -c "import venv, ensurepip" >/dev/null 2>&1; then
  echo ">>> installing python3-venv ..."
  sudo apt-get update -y && sudo apt-get install -y python3-venv
fi
mkdir -p "$REPO/runtime"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
echo ">>> installing scikit-learn, pandas and xgboost (a few minutes) ..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet scikit-learn pandas
# xgboost-cpu is the small CPU-only build. It is not offered for every machine type (for example
# ARM servers); the standard package is used there instead.
if ! "$VENV/bin/pip" install --quiet xgboost-cpu 2>/dev/null; then
  echo ">>> the small xgboost build is not offered for this machine; installing the standard one ..."
  "$VENV/bin/pip" install --quiet xgboost
fi
"$VENV/bin/python" -c "import sklearn, xgboost, pandas; print('Training tools ready: scikit-learn', sklearn.__version__, '| xgboost', xgboost.__version__)"
echo "Done. Open Admin > Update models on the site; it will now offer 'Run model update'."
