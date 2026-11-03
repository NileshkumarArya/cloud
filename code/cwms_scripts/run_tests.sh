#!/usr/bin/env bash
# Run backend tests plus an optional JS syntax check (Linux/macOS).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m unittest discover -s cwms_tests -t . -v
if command -v node >/dev/null 2>&1; then
    node --check cwms_dashboard/app.js
    echo "Frontend syntax check passed."
else
    echo "Node.js not found; skipped JS syntax check."
fi
