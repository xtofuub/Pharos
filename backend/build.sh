#!/bin/sh
set -e
cd "$(dirname "$0")"

echo ""
echo "  Building BreachLens binary..."
echo ""

echo "  [1/3] Installing dependencies..."
python3 -m pip install -e . pyinstaller --quiet

echo "  [2/3] Building (1-2 minutes)..."
python3 -m PyInstaller breachelens.spec --noconfirm --clean

echo "  [3/3] Done!"
echo "  Binary: dist/BreachLens"
