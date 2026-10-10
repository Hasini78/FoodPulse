# FoodPulse setup (Windows)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path .venv)) {
    python -m venv .venv
}
.\.venv\Scripts\pip install -r backend\requirements.txt

if (-not (Test-Path frontend\package.json)) {
    Write-Error "frontend/ not found. Scaffold the frontend first."
}
Set-Location frontend
npm install
Set-Location ..

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example — update secrets before production use."
}

Write-Host "Setup complete."
