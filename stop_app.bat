@echo off
setlocal

taskkill /F /IM uvicorn.exe >nul 2>nul
taskkill /F /IM streamlit.exe >nul 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *uvicorn*" >nul 2>nul

echo Stop command executed. Verify with Task Manager if needed.
