@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Run scripts\setup.ps1 and scripts\prepare_models.py first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -I "%~dp0backend\scripts\launch.py"
if errorlevel 1 pause
