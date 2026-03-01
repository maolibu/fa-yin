@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

cd /d "%~dp0"

echo.
echo   ========================================
echo        法印对照 · Fa-Yin
echo   ========================================
echo.

:: --- Step 1: 检测 Python ---
set "PYTHON_CMD="

:: 按优先级检测 Python 版本（3.14 → 3.10）
for %%C in (python3 python py) do (
    for /f "tokens=2" %%v in ('%%C -V 2^>nul') do (
        if not defined PYTHON_CMD (
            for /f "tokens=1,2 delims=." %%a in ("%%v") do (
                if %%a GEQ 3 (
                    if %%b GEQ 10 (
                        set "PYTHON_CMD=%%C"
                        set "PY_VER=%%v"
                    )
                )
            )
        )
    )
)

if defined PYTHON_CMD goto :found_python

:: --- 未找到，尝试 winget 自动安装 (Windows 10/11) ---
where winget >nul 2>&1
if !errorlevel! equ 0 (
    echo   [!] Python 3.10+ not found, trying winget install...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if !errorlevel! equ 0 (
        echo.
        echo   [OK] Python installed. Please CLOSE this window and double-click start.bat again.
        echo   (New PATH takes effect after restart^)
        pause
        exit /b 0
    )
)

echo   [X] Python 3.10+ not found.
echo   Please install from https://www.python.org/downloads/
echo   Make sure to check "Add Python to PATH"
pause
exit /b 1

:found_python
echo   [OK] Python !PY_VER! (!PYTHON_CMD!)

:: --- Step 2: 创建虚拟环境 ---
:: 检查 activate.bat 是否存在（而非仅检查目录），防止不完整的 venv
if exist ".venv\Scripts\activate.bat" goto :venv_ready

:: 如果 .venv 目录存在但不完整，先清除
if exist ".venv" (
    echo   [!] Incomplete .venv detected, recreating...
    rmdir /s /q .venv
)

echo   [..] Creating virtual environment...
set "VENV_OK=0"

:: 第 1 次尝试：标准方式创建 venv
!PYTHON_CMD! -m venv .venv 2>nul
if exist ".venv\Scripts\activate.bat" (
    set "VENV_OK=1"
    goto :venv_done
)

:: 第 2 次尝试：不带 pip 创建（兼容 conda/miniforge 的 Python）
if exist ".venv" rmdir /s /q .venv
!PYTHON_CMD! -m venv --without-pip .venv 2>nul
if exist ".venv\Scripts\activate.bat" (
    set "VENV_OK=1"
    goto :venv_done
)

:venv_done
if "!VENV_OK!"=="0" (
    echo   [X] Failed to create virtual environment.
    echo   Please ensure your Python installation includes the venv module.
    pause
    exit /b 1
)
echo   [OK] Virtual environment created.

:venv_ready
:: 激活虚拟环境
call .venv\Scripts\activate.bat

:: --- Step 3: 安装依赖 ---
:: 如果 pip 不可用（--without-pip 创建的 venv），先安装 pip
.venv\Scripts\python.exe -m pip --version >nul 2>&1
if !errorlevel! neq 0 (
    echo   [..] Installing pip...
    .venv\Scripts\python.exe -m ensurepip --default-pip 2>nul
    if !errorlevel! neq 0 (
        echo   [..] Downloading get-pip.py...
        curl -sS -o "%TEMP%\get-pip.py" https://bootstrap.pypa.io/get-pip.py
        .venv\Scripts\python.exe "%TEMP%\get-pip.py"
        del "%TEMP%\get-pip.py" 2>nul
    )
)

if not exist ".venv\.deps_installed" goto :install_deps
:: 检查 requirements.txt 是否比上次安装更新
for %%R in (requirements.txt) do set "REQ_TIME=%%~tR"
for %%D in (.venv\.deps_installed) do set "DEP_TIME=%%~tD"
if "!REQ_TIME!" gtr "!DEP_TIME!" goto :install_deps
echo   [OK] Dependencies ready.
goto :launch

:install_deps
echo   [..] Installing dependencies, first run may take a few minutes...
python -m pip install --quiet --upgrade pip
if !errorlevel! neq 0 (
    echo   [X] Failed to upgrade pip.
    pause
    exit /b 1
)

pip install --quiet -r requirements.txt
if !errorlevel! neq 0 (
    echo   [X] Failed to install dependencies.
    pause
    exit /b 1
)

echo done > .venv\.deps_installed
echo   [OK] Dependencies installed.

:launch
:: --- Step 4: 启动 ---
echo.
echo   Starting Fa-Yin...
echo.
python launcher.py %*
pause
