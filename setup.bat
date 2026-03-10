@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher ^(py^) not found. Install Python 3.11, 3.12, or 3.13 first.
  exit /b 1
)

set PY_LAUNCHER=

py -3.13 -c "import sys" >nul 2>nul
if not errorlevel 1 set PY_LAUNCHER=py -3.13

if "%PY_LAUNCHER%"=="" (
  py -3.12 -c "import sys" >nul 2>nul
  if not errorlevel 1 set PY_LAUNCHER=py -3.12
)

if "%PY_LAUNCHER%"=="" (
  py -3.11 -c "import sys" >nul 2>nul
  if not errorlevel 1 set PY_LAUNCHER=py -3.11
)

if "%PY_LAUNCHER%"=="" (
  echo No supported Python found. Install Python 3.11, 3.12, or 3.13.
  exit /b 1
)

echo Using %PY_LAUNCHER%
%PY_LAUNCHER% -m venv .venv
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
