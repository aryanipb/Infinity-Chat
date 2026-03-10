@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

if not exist .venv (
  echo Missing .venv. Run setup.bat first.
  exit /b 1
)

if exist .env (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" set %%A=%%B
  )
)

if "%BACKEND_HOST%"=="" set BACKEND_HOST=0.0.0.0
if "%BACKEND_PORT%"=="" set BACKEND_PORT=8080
if "%UI_HOST%"=="" set UI_HOST=0.0.0.0
if "%UI_PORT%"=="" set UI_PORT=8501

call .venv\Scripts\activate

start /b cmd /c "python -m uvicorn main:app --host %BACKEND_HOST% --port %BACKEND_PORT% > backend.log 2>&1"
start /b cmd /c "streamlit run ui.py --server.port %UI_PORT% --server.address %UI_HOST% > streamlit.log 2>&1"

echo Backend: http://127.0.0.1:%BACKEND_PORT%
echo Streamlit: http://127.0.0.1:%UI_PORT%
echo LAN: http://YOUR_LAN_IP:%UI_PORT%
