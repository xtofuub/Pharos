#!/usr/bin/env python3
"""
BreachLens launcher -- one command to run everything.

    python run.py

What this does:
  1. Checks Python version (3.11+)
  2. Installs dependencies if missing (pip install -e .)
  3. Starts the FastAPI backend on http://127.0.0.1:8443
  4. Opens your default browser to the dashboard
  5. Press Ctrl+C to stop

Works on Windows, macOS, and Linux. No npm, no Node, no venv required.
"""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

# ---- Config ----
HOST = os.environ.get("BREACHLENS__SERVER__BIND_ADDR", "127.0.0.1")
PORT = int(os.environ.get("BREACHLENS__SERVER__PORT", "8443"))
MIN_PYTHON = (3, 11)

BACKEND_DIR = Path(__file__).resolve().parent


def main() -> None:
    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║          BreachLens v0.1.0            ║")
    print("  ║   Local breach intelligence search    ║")
    print("  ╚══════════════════════════════════════╝")
    print()

    # 1. Check Python version
    if sys.version_info < MIN_PYTHON:
        print(f"  ERROR: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required (you have {sys.version_info[0]}.{sys.version_info[1]}).")
        print(f"  Download from https://python.org/downloads/")
        sys.exit(1)

    print(f"  Python {sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]} OK")

    # 2. Ensure dependencies are installed
    ensure_deps()

    # 3. Import and start the server
    print()
    print(f"  Starting BreachLens on http://{HOST}:{PORT}")
    print(f"  Default login: admin / breachelens")
    print()
    print("  Press Ctrl+C to stop.")
    print("  " + "=" * 50)
    print()

    # 4. Open browser after a short delay (in a background thread)
    import threading
    import time

    def open_browser():
        time.sleep(1.5)
        url = f"http://{HOST}:{PORT}/"
        print(f"  Opening browser: {url}")
        try:
            webbrowser.open(url)
        except Exception:
            pass  # headless environment

    threading.Thread(target=open_browser, daemon=True).start()

    # 5. Start uvicorn (blocking -- runs until Ctrl+C)
    try:
        import uvicorn
        uvicorn.run(
            "breachelens.main:app",
            host=HOST,
            port=PORT,
            log_level="info",
            access_log=False,
        )
    except KeyboardInterrupt:
        print()
        print("  BreachLens stopped.")
    except Exception as e:
        print(f"\n  ERROR: {e}")
        sys.exit(1)


def ensure_deps() -> None:
    """Check if breachelens package is importable; if not, pip install."""
    try:
        import breachelens  # noqa: F401
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
        print("  Dependencies OK")
        return
    except ImportError:
        pass

    print("  Installing dependencies (first run only)...")
    pip = [sys.executable, "-m", "pip", "install", "-e", str(BACKEND_DIR)]
    try:
        subprocess.check_call(pip, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print("  Dependencies installed OK")
    except subprocess.CalledProcessError as e:
        print(f"\n  ERROR: Failed to install dependencies.")
        print(f"  Run this manually:")
        print(f"    {sys.executable} -m pip install -e \"{BACKEND_DIR}\"")
        print(f"\n  Pip error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
