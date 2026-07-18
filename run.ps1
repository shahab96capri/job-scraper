# ==================================================
# Job Intelligence Platform - Run
# ==================================================
# Always runs main.py using THIS PROJECT'S OWN virtual environment,
# directly by full path -- so you never need to "activate" anything
# first, and it can never accidentally use the wrong Python version.
#
# Usage (same arguments main.py normally takes):
#   .\run.ps1 crawl --all-categories --pages 1
#   .\run.ps1 sites
#   .\run.ps1 crawl --help

$PROJECT_ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$PYTHON = Join-Path $PROJECT_ROOT ".venv\Scripts\python.exe"

if (!(Test-Path $PYTHON)) {

    Write-Host "Virtual environment not found." -ForegroundColor Red
    Write-Host "Run .\setup.ps1 first." -ForegroundColor Red
    exit 1

}

Set-Location $PROJECT_ROOT

& $PYTHON main.py @args
