# Start the CWMS API and dashboard (Windows PowerShell).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    python run_api.py
} finally {
    Pop-Location
}
