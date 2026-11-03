# Run backend tests plus an optional JS syntax check (Windows PowerShell).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    python -m unittest discover -s cwms_tests -t . -v
    if (Get-Command node -ErrorAction SilentlyContinue) {
        node --check cwms_dashboard/app.js
        Write-Host "Frontend syntax check passed."
    } else {
        Write-Host "Node.js not found; skipped JS syntax check."
    }
} finally {
    Pop-Location
}
