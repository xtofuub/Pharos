"""
Pharos standalone entry point -- used by PyInstaller to build the .exe.

When double-clicked:
  1. Starts the FastAPI backend on 127.0.0.1:8443
  2. Opens the default browser to the dashboard
  3. Prints a console window with status (press Ctrl+C to stop)
"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser


def main() -> None:
    host = os.environ.get("BREACHLENS__SERVER__BIND_ADDR", "127.0.0.1")
    port = int(os.environ.get("BREACHLENS__SERVER__PORT", "8443"))

    print()
    print("  ===========================================")
    print("            Pharos v0.2.0")
    print("       Local breach intelligence search")
    print("  ===========================================")
    print()
    print(f"  Starting server on http://{host}:{port}")
    print(f"  Default login: admin / breachelens")
    print()
    print("  Your browser will open automatically.")
    print("  Press Ctrl+C to stop the server.")
    print("  -------------------------------------------")
    print()

    def open_browser():
        time.sleep(2.0)
        url = f"http://{host}:{port}/"
        try:
            webbrowser.open(url)
            print(f"  Browser opened: {url}")
        except Exception:
            print(f"  Open manually: {url}")

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        import uvicorn
        uvicorn.run(
            "breachelens.main:app",
            host=host,
            port=port,
            log_level="info",
            access_log=False,
        )
    except KeyboardInterrupt:
        print()
        print("  Pharos stopped.")
    except Exception as e:
        print(f"\n  ERROR: {e}")
        input("\n  Press Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    main()
