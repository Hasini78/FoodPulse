$ErrorActionPreference = "Stop"
Set-Location (Join-Path (Split-Path $PSScriptRoot -Parent) "backend")
$env:PYTHONPATH = (Get-Location).Path
if (Test-Path ..\.venv\Scripts\Activate.ps1) {
    & ..\.venv\Scripts\Activate.ps1
}
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
