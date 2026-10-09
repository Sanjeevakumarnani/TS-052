@echo off
setlocal
cd /d "%~dp0.."
if not exist backend\.venv\Scripts\activate.bat (
  echo Missing Python environment. Run scripts\setup-windows.bat first.
  pause
  exit /b 1
)
if not exist frontend\node_modules (
  echo Missing frontend dependencies. Run scripts\setup-windows.bat first.
  pause
  exit /b 1
)
start "InfraPulse API" cmd /k "cd /d ""%CD%\backend"" && call .venv\Scripts\activate.bat && uvicorn app.main:app --reload --port 8000"
timeout /t 2 /nobreak >nul
start "InfraPulse Web" cmd /k "cd /d ""%CD%\frontend"" && npm run dev"
echo API: http://127.0.0.1:8000/docs
echo App: http://localhost:5173
echo Close the two server windows to stop InfraPulse.
