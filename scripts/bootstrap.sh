#!/usr/bin/env bash
set -euo pipefail

echo "==> Checking prerequisites..."

command -v git >/dev/null 2>&1 || { echo "git is required but not found."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 is required but not found."; exit 1; }

echo "==> Installing gitweave (gw) CLI..."
pip install -e . --quiet --break-system-packages 2>/dev/null \
  || pip install -e . --quiet

echo "==> Bootstrap complete. Run 'gw --help' to get started."
