# ==================================================
# Job Intelligence Platform - Bootstrap Setup
# ==================================================

Write-Host "Starting project setup..." -ForegroundColor Cyan


# -------------------------------
# Project Root
# -------------------------------

$PROJECT_ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

Set-Location $PROJECT_ROOT


Write-Host ""
Write-Host "Project root:"
Write-Host $PROJECT_ROOT



# -------------------------------
# Python Check
# -------------------------------
# NOTE: this project targets Python 3.12 specifically and pins package
# versions that may not have installable wheels for newer Pythons. We
# always ask for 3.12 explicitly via the "py" launcher rather than the
# bare "python" command, so this keeps working correctly even on a
# machine that also has a newer Python (e.g. 3.14) installed alongside it.

Write-Host ""
Write-Host "Checking for Python 3.12..."


$pythonVersion = py -3.12 --version 2>$null


if (-not $pythonVersion) {

    Write-Host "Python 3.12 was not found." -ForegroundColor Red
    Write-Host "Download it from: https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    Write-Host "During install, make sure 'Add python.exe to PATH' is checked."
    exit 1

}


Write-Host $pythonVersion



# -------------------------------
# Virtual Environment
# -------------------------------


if (!(Test-Path ".venv")) {


    Write-Host ""
    Write-Host "Creating virtual environment (Python 3.12)..."


    py -3.12 -m venv .venv

}
else {

    Write-Host ".venv already exists"

}



$PYTHON = ".\.venv\Scripts\python.exe"



# -------------------------------
# Upgrade pip
# -------------------------------


Write-Host ""
Write-Host "Updating pip..."


& $PYTHON -m pip install --upgrade pip



# -------------------------------
# Requirements
# -------------------------------


if (Test-Path "requirements.txt") {


    Write-Host ""
    Write-Host "Installing requirements..."


    & $PYTHON -m pip install -r requirements.txt


}
else {


    Write-Host "requirements.txt missing"
    exit 1

}



# -------------------------------
# Playwright
# -------------------------------


Write-Host ""
Write-Host "Installing Playwright browser..."


& $PYTHON -m playwright install chromium



# -------------------------------
# ENV Setup
# -------------------------------


Write-Host ""
Write-Host "Environment setup"



if (!(Test-Path ".env.example")) {


    Write-Host ".env.example missing"
    exit 1

}



if (Test-Path ".env") {


    $answer = Read-Host ".env exists. Replace? (y/n)"


    if ($answer -eq "y") {

        Remove-Item ".env"

    }
    else {

        Write-Host "Keeping existing .env"

    }

}



if (!(Test-Path ".env")) {


    Write-Host ""
    Write-Host "Database configuration"
    Write-Host "(This assumes a PostgreSQL user + database with these exact" -ForegroundColor DarkGray
    Write-Host " names already exist on your machine. This script does not" -ForegroundColor DarkGray
    Write-Host " create them for you.)" -ForegroundColor DarkGray


   $dbUser = Read-Host "PostgreSQL username"

    if (!$dbUser) {
        $dbUser="job_platform_user"
    }


    $dbPassword = Read-Host "PostgreSQL password"


    if (!$dbPassword){

        $dbPassword="change_me"

    }


    $dbName = Read-Host "Database name"


    if (!$dbName){

        $dbName="job_intelligence"

    }



    Copy-Item ".env.example" ".env"



    (Get-Content ".env") `
    -replace "job_platform_user",$dbUser `
    -replace "change_me",$dbPassword `
    -replace "job_intelligence",$dbName `
    | Set-Content ".env"



    Write-Host ".env created"

}



# -------------------------------
# Database migrations
# -------------------------------
# Creates/updates all tables the app needs. Safe to re-run every time --
# Alembic skips migrations that are already applied, so this is a no-op
# on a database that's already up to date.

Write-Host ""
Write-Host "Running database migrations..."

& $PYTHON -m alembic upgrade head

if ($LASTEXITCODE -ne 0) {

    Write-Host ""
    Write-Host "Migrations failed -- is PostgreSQL running, and do the" -ForegroundColor Red
    Write-Host "username/password/database name in .env match a real," -ForegroundColor Red
    Write-Host "already-created PostgreSQL user and database?" -ForegroundColor Red
    exit 1

}



# -------------------------------
# Directories
# -------------------------------
# Everything the app actually writes to (output/json, output/excel, logs)
# is created automatically on demand by the app itself -- nothing to do
# here.



# -------------------------------
# Finish
# -------------------------------


Write-Host ""
Write-Host "================================="
Write-Host "SETUP COMPLETED"
Write-Host "================================="


Write-Host ""
Write-Host "Activate environment:"
Write-Host ".\.venv\Scripts\Activate.ps1"


Write-Host ""
Write-Host "Run:"
Write-Host "python main.py crawl --pages 1"
