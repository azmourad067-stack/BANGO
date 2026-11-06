@echo off
rem Installation de Bongo (a lancer une seule fois, par double-clic)
cd /d "%~dp0"
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.12 introuvable. Installe-le depuis https://www.python.org/downloads/ puis relance ce fichier.
  pause
  exit /b 1
)
if not exist .venv py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e ".[tout]"
if errorlevel 1 (
  echo L installation a echoue. Verifie la connexion Internet puis relance ce fichier.
  pause
  exit /b 1
)
if not exist .env copy .env.example .env >nul
.venv\Scripts\python -m bongo check-setup
pause
