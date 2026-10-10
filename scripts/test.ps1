$ErrorActionPreference = "Stop"
Set-Location (Join-Path (Split-Path $PSScriptRoot -Parent) "backend")
if (Test-Path ..\.venv\Scripts\Activate.ps1) {
    & ..\.venv\Scripts\Activate.ps1
}
pytest -q
