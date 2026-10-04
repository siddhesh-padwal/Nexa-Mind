@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please run setup.ps1 first. See README.md for instructions.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py
pause
