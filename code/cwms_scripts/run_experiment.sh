#!/usr/bin/env bash
# Run the reproducible multi-seed scheduling experiment (Linux/macOS).
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 cwms_scripts/run_experiment.py
