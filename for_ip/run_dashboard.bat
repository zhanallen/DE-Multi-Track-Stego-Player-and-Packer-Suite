@echo off
title i18n Security Dashboard Launcher
echo ============================================================
echo      i18n and IP Context Security Dashboard Launcher
echo ============================================================
echo.
echo Opening browser and starting FastAPI backend server...
echo.

start "" http://127.0.0.1:8000
python main.py

pause
