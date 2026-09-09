@echo off
setlocal
"%~dp0.venv\Scripts\python.exe" -I "%~dp0backend\scripts\launch.py" --stop
if errorlevel 1 pause
