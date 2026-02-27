@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: 法印对照 · 一键启动脚本 (Windows)
:: 自动检测 Python、创建虚拟环境、安装依赖、启动服务

cd /d "%~dp0"

echo.
echo   ╔══════════════════════════════════╗
echo   ║       法印对照 · Fa-Yin          ║
echo   ╚══════════════════════════════════╝
echo.

:: ─── Step 1: 检测 Python ────────────────────────────────────
set "PYTHON_CMD="

:: 尝试 python3
where python3 >nul 2>&1
if %errorlevel%==0 (
    for /f "tokens=*" %%v in ('python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "PY_VER=%%v"
    for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
        if %%a GEQ 3 if %%b GEQ 10 set "PYTHON_CMD=python3"
    )
)

:: 尝试 python
if not defined PYTHON_CMD (
    where python >nul 2>&1
    if %errorlevel%==0 (
        for /f "tokens=*" %%v in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "PY_VER=%%v"
        for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
            if %%a GEQ 3 if %%b GEQ 10 set "PYTHON_CMD=python"
        )
    )
)

:: 尝试 py launcher (Windows)
if not defined PYTHON_CMD (
    where py >nul 2>&1
    if %errorlevel%==0 (
        for /f "tokens=*" %%v in ('py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "PY_VER=%%v"
        for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
            if %%a GEQ 3 if %%b GEQ 10 set "PYTHON_CMD=py -3"
        )
    )
)

:: 尝试自动安装 Python (winget, Windows 10/11 自带)
if not defined PYTHON_CMD (
    where winget >nul 2>&1
    if !errorlevel!==0 (
        echo   ❌ 未找到 Python 3.10+，正在尝试自动安装...
        echo.
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        if !errorlevel!==0 (
            echo.
            echo   ✅ Python 安装完成，请关闭此窗口，重新双击 start.bat
            pause
            exit /b 0
        )
    )
    echo   ❌ 未找到 Python 3.10+，自动安装也未成功
    echo.
    echo   请手动下载安装 Python：
    echo     https://www.python.org/downloads/
    echo.
    echo   安装时请勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('%PYTHON_CMD% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"') do set "FULL_VER=%%v"
echo   ✅ Python %FULL_VER%

:: ─── Step 2: 创建虚拟环境 ───────────────────────────────────
if not exist ".venv" (
    echo   ⏳ 创建虚拟环境...
    %PYTHON_CMD% -m venv .venv
    echo   ✅ 虚拟环境已创建
)

:: 激活虚拟环境
call .venv\Scripts\activate.bat

:: ─── Step 3: 安装依赖 ───────────────────────────────────────
if not exist ".venv\.deps_installed" (
    echo   ⏳ 安装依赖包（首次可能需要几分钟）...
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    echo done > .venv\.deps_installed
    echo   ✅ 依赖安装完成
) else (
    echo   ✅ 依赖已就绪
)

:: ─── Step 4: 启动 ───────────────────────────────────────────
echo.
echo   🚀 正在启动法印对照...
echo.
python launcher.py %*

pause
