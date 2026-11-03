# Run the reproducible multi-seed scheduling experiment (Windows PowerShell).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    python cwms_scripts/run_experiment.py
} finally {
    Pop-Location
}
