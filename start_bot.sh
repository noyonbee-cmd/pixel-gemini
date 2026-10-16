#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "========================================================"
echo "      Pixel 10 Pro Google One Gemini Bot"
echo "========================================================"
echo ""

# Check python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 is not installed. Please install Python 3.10+."
    exit 1
fi

# Create venv if not exists
if [ ! -d "venv" ]; then
    echo "[1/3] Creating virtual environment (venv)..."
    python3 -m venv venv
fi

# Activate & install requirements
echo "[2/3] Checking requirements..."
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Run bot
echo "[3/3] Starting Pixel Gemini Bot..."
echo ""
python main.py
