@echo off
rem SAARTHI launcher: starts the app and opens it in your browser.
cd /d "%~dp0backend"
if not exist .venv\Scripts\python.exe (
  echo First-time setup: creating Python environment...
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
echo.
echo SAARTHI is starting at http://127.0.0.1:8000  (press Ctrl+C to stop)
start "" http://127.0.0.1:8000
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
