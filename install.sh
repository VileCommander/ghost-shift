#!/bin/bash
set -e
echo "[*] Updating system packages..."
sudo apt update && sudo apt install -y tmux cmatrix python3-pip python3-venv git curl

echo "[*] Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "[*] Phase 1 dependencies installed successfully."
