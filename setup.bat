@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher ^(py^) not found. Install Python 3.11+ first.
  exit /b 1
)

py -3 -m venv .venv
if errorlevel 1 exit /b 1

call .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

where pixi >nul 2>nul
if errorlevel 1 (
  echo pixi not found in PATH. Skipping pixi install.
) else (
  pixi install
)

echo Setup complete.
