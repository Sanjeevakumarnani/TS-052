@echo off
setlocal
cd /d "%~dp0.."
echo === InfraPulse setup ===
where python >nul 2>nul || (echo Python 3.10+ is required. & pause & exit /b 1)
where node >nul 2>nul || (echo Node.js 20+ is required for the React frontend. & pause & exit /b 1)
python -m venv backend\.venv
call backend\.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
pip install pytest httpx
if errorlevel 1 (echo Backend dependency installation failed. & pause & exit /b 1)
cd frontend
npm install
if errorlevel 1 (echo Frontend dependency installation failed. Check network access and retry npm install. & pause & exit /b 1)
echo Setup complete. Run scripts\start-infrapulse-windows.bat
pause
