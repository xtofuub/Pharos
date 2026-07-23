#!/bin/sh
set -e
cd "$(dirname "$0")"
python3 -m pip install -e . pyinstaller --quiet
python3 -m PyInstaller breachelens.spec --noconfirm --clean
echo "Binary: dist/Pharos"
