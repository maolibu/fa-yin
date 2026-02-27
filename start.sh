#!/usr/bin/env bash
# 法印对照 · 一键启动脚本 (macOS / Linux)
# 自动检测 Python、创建虚拟环境、安装依赖、启动服务

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
REQ_FILE="$SCRIPT_DIR/requirements.txt"

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║       法印对照 · Fa-Yin          ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# ─── Step 1: 检测 Python ────────────────────────────────────
find_python() {
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
            major=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
            minor=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON_CMD=$(find_python) || {
    echo "  ❌ 未找到 Python 3.10+，正在尝试自动安装..."
    echo ""
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS: 尝试用 Homebrew 安装
        if command -v brew &>/dev/null; then
            echo "  ⏳ 正在通过 Homebrew 安装 Python..."
            brew install python@3.12
            PYTHON_CMD=$(find_python) || {
                echo "  ❌ 安装失败，请手动安装：brew install python@3.12"
                exit 1
            }
        else
            echo "  请先安装 Homebrew："
            echo '    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
            echo "  然后运行：brew install python@3.12"
            echo "  或从 https://www.python.org/downloads/ 直接下载"
            exit 1
        fi
    else
        # Ubuntu/Debian: 尝试 apt 安装
        if command -v apt &>/dev/null; then
            echo "  ⏳ 正在通过 apt 安装 Python..."
            sudo apt update && sudo apt install -y python3 python3-venv python3-pip
            PYTHON_CMD=$(find_python) || {
                echo "  ❌ 安装失败，请手动运行：sudo apt install python3 python3-venv python3-pip"
                exit 1
            }
        else
            echo "  请安装 Python 3.10+："
            echo "    https://www.python.org/downloads/"
            exit 1
        fi
    fi
}

PYTHON_VER=$("$PYTHON_CMD" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
echo "  ✅ Python $PYTHON_VER ($PYTHON_CMD)"

# ─── Step 2: 创建虚拟环境 ───────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "  ⏳ 创建虚拟环境..."
    # Ubuntu 可能缺 python3-venv，尝试自动安装
    if ! "$PYTHON_CMD" -m venv "$VENV_DIR" 2>/dev/null; then
        if command -v apt &>/dev/null; then
            PY_SHORT=$($PYTHON_CMD -c "import sys; print(f'python3.{sys.version_info.minor}')")
            echo "  ⏳ 安装 ${PY_SHORT}-venv..."
            sudo apt install -y "${PY_SHORT}-venv"
            "$PYTHON_CMD" -m venv "$VENV_DIR"
        else
            echo "  ❌ 无法创建虚拟环境，请安装 python3-venv"
            exit 1
        fi
    fi
    echo "  ✅ 虚拟环境已创建"
fi

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

# ─── Step 3: 安装依赖 ───────────────────────────────────────
if [ ! -f "$VENV_DIR/.deps_installed" ] || [ "$REQ_FILE" -nt "$VENV_DIR/.deps_installed" ]; then
    echo "  ⏳ 安装依赖包..."
    pip install --quiet --upgrade pip
    pip install --quiet -r "$REQ_FILE"
    touch "$VENV_DIR/.deps_installed"
    echo "  ✅ 依赖安装完成"
else
    echo "  ✅ 依赖已就绪"
fi

# ─── Step 4: 启动 ───────────────────────────────────────────
echo ""
echo "  🚀 正在启动法印对照..."
echo ""
python launcher.py "$@"
