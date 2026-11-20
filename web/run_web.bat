@echo off
rem StegoPlayer Web API launcher (Windows, primary platform).
rem Double-click or run from any folder; it switches to the repository root.
setlocal
chcp 65001 >nul
rem pee_stego.py prints emoji; force UTF-8 so a cp950 console cannot crash decoding.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."
if not defined STEGO_WEB_HOST set "STEGO_WEB_HOST=127.0.0.1"
if not defined STEGO_WEB_PORT set "STEGO_WEB_PORT=8765"
set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
echo [StegoPlayer Web] http://%STEGO_WEB_HOST%:%STEGO_WEB_PORT%  (Ctrl+C to stop)
"%PYTHON_EXE%" -m uvicorn web.backend.main:app --host %STEGO_WEB_HOST% --port %STEGO_WEB_PORT%
endlocal
