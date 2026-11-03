#!/usr/bin/env bash
# Start the CWMS API and dashboard (Linux/macOS).
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 run_api.py
