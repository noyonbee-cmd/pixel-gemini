@echo off
title Pixel 10 Pro Google One Gemini Bot
cd /d "%~dp0"
echo ========================================================
echo       Pixel 10 Pro Google One Gemini Bot
echo ========================================================
echo.

:: Check Python installation
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to PATH.
    echo Please install Python 3.10+ from https://www.python.org/
    echo and check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: Check / create virtualenv
if not exist "venv\Scripts\python.exe" (
    echo [1/3] Creating virtual environment (venv)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create venv. Running with system python...
        goto RUN_SYSTEM
    )
)

:: Install / verify requirements
echo [2/3] Checking requirements...
venv\Scripts\python.exe -m pip install --quiet --upgrade pip
venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

:: Start the bot
echo [3/3] Starting Pixel Gemini Bot...
echo.
venv\Scripts\python.exe main.py
goto END

:RUN_SYSTEM
pip install --quiet -r requirements.txt
python main.py

:END
pause
