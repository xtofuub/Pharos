#!/usr/bin/env python3
"""Pharos launcher -- one command to run everything."""
from __future__ import annotations
import os,subprocess,sys,webbrowser
from pathlib import Path
HOST=os.environ.get("BREACHLENS__SERVER__BIND_ADDR","127.0.0.1")
PORT=int(os.environ.get("BREACHLENS__SERVER__PORT","8443"))
MIN_PYTHON=(3,11)
BACKEND_DIR=Path(__file__).resolve().parent

def main()->None:
    print("\n  Pharos v0.3.0\n  Local breach intelligence search\n")
    if sys.version_info<MIN_PYTHON:
        print("Python 3.11+ required");sys.exit(1)
    ensure_deps()
    print(f"Starting Pharos on http://{HOST}:{PORT}")
    print("First login: admin / breachelens (password change required)")
    import threading,time
    def open_browser():
        time.sleep(1.5)
        try:webbrowser.open(f"http://{HOST}:{PORT}/")
        except Exception:pass
    threading.Thread(target=open_browser,daemon=True).start()
    try:
        import uvicorn
        uvicorn.run("breachelens.main:app",host=HOST,port=PORT,log_level="info",access_log=False)
    except KeyboardInterrupt:print("\nPharos stopped.")

def ensure_deps()->None:
    try:
        import breachelens,fastapi,uvicorn
        return
    except ImportError:pass
    try:subprocess.check_call([sys.executable,"-m","pip","install","-e",str(BACKEND_DIR)])
    except subprocess.CalledProcessError:sys.exit(1)
if __name__=="__main__":main()
