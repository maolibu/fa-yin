@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0"

echo ============================================
echo   Fa-Yin Launcher (Default PyPI Source)
echo ============================================
echo.

:: --- Step 1: Detect Python ---
set "PYTHON_CMD="

for /f "tokens=2" %%v in ('python -V 2^>nul') do set "PY_VER=%%v"
if defined PY_VER (
    for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
        if %%a GEQ 3 (
            if %%b GEQ 10 set "PYTHON_CMD=python"
        )
    )
)

if defined PYTHON_CMD goto :found_python

:: --- Try auto-install via winget (Windows 10/11) ---
where winget >nul 2>&1
if !errorlevel! equ 0 (
    echo [WARN] Python 3.10+ not found. Trying auto-install via winget...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if !errorlevel! equ 0 (
        echo.
        echo [OK] Python installed. Please close this window and double-click start.bat again.
        pause
        exit /b 0
    )
)

echo [WARN] Python 3.10+ not found.
echo Please install Python from python.org
echo Make sure to check "Add Python to PATH"
pause
exit /b 1

:found_python
echo [OK] Python !PY_VER! found.

:: --- Step 2: Virtual Env ---
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

:: --- Step 3: Install Deps ---
call .venv\Scripts\activate.bat
if not exist ".venv\.deps_installed" (
    echo Installing dependencies, first run may take a few minutes...
    python -m pip install --quiet --upgrade pip
    if !errorlevel! neq 0 (
        echo [X] Failed to upgrade pip.
        pause
        exit /b 1
    )

    pip install --quiet -r requirements.txt
    if !errorlevel! neq 0 (
        echo [X] Failed to install dependencies.
        echo If you are in mainland China, please use start_cn.bat instead.
        pause
        exit /b 1
    )

    echo done > .venv\.deps_installed
    echo [OK] Dependencies installed.
) else (
    echo [OK] Dependencies ready.
)

:: --- Step 4: Launch ---
echo Starting Fa-Yin...
python launcher.py
pause
