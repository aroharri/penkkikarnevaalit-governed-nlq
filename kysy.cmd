@echo off
REM Double-click this file. It opens the question session in this folder.
REM Nothing to type, no paths to get right, no shell to know.
REM
REM Anything on the command line is passed straight to the CLI, so a shortcut
REM ending "kysy.cmd --router rules" opens the session on the offline router.

cd /d "%~dp0"
chcp 65001 >nul
title penkkikarnevaalit-governed-nlq

if not exist ".venv\Scripts\python.exe" (
  echo Virtuaaliymparistoa ei ole viela luotu. Aja ensin:
  echo.
  echo     python -m venv .venv
  echo     .venv\Scripts\pip install -e ".[dev]"
  echo.
  pause
  exit /b 1
)

if not exist "warehouse.duckdb" (
  echo Varastoa ei ole viela rakennettu. Rakennetaan nyt.
  echo.
  ".venv\Scripts\python.exe" warehouse\build.py
  echo.
)

".venv\Scripts\python.exe" -m nlq.cli %*

echo.
pause
