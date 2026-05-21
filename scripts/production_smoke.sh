#!/usr/bin/env bash
# Quick checks before deploy: syntax, imports, and unit tests.
# Install test deps once: pip install -r backend/requirements-dev.txt
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Python compile (src) =="
python3 -m compileall -q src

echo "== Pytest (unit) =="
if ! python3 -m pytest tests/ -q --tb=short; then
  echo "Hint: pip install -r backend/requirements-dev.txt"
  exit 1
fi

echo "== frontend package syntax =="
python3 -m compileall -q frontend

echo "OK — smoke checks passed."
