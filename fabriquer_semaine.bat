@echo off
rem Fabrique les 7 episodes d une semaine puis la compilation (double-clic)
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Lance d abord installer.bat
  pause
  exit /b 1
)
echo Dates possibles : 2026-12-01, 2026-12-08, 2026-12-15, 2026-12-22
set /p START=Premier jour de la semaine (ex. 2026-12-01) : 
.venv\Scripts\python -m bongo build-week --start %START%
if errorlevel 1 (
  echo.
  echo Des episodes ne sont pas prets : regarde le rapport, corrige, puis relance ce fichier.
  echo La compilation n est pas fabriquee.
  pause
  exit /b 1
)
.venv\Scripts\python -m bongo compile --week %START%
pause
