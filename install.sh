#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "[*] Installing system packages..."
sudo apt update && sudo apt install -y tmux nano htop cmatrix mutt python3-pip python3-venv git curl

echo "[*] Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "[*] Done. Still needed (manual):"
echo "    1. Install Ollama: https://ollama.com/download"
echo "    2. ollama pull qwen2.5-coder:3b"
echo "    3. python3 -m ghost_shift.director_desk --no-rain"
