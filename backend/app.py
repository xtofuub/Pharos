"""Pharos standalone entry point used by PyInstaller."""
from __future__ import annotations
import os,sys,threading,time,webbrowser

def main()->None:
    host=os.environ.get("BREACHLENS__SERVER__BIND_ADDR","127.0.0.1")
    port=int(os.environ.get("BREACHLENS__SERVER__PORT","8443"))
    print("\n  ===========================================\n            Pharos v0.3.0\n       Local breach intelligence search\n  ===========================================\n")
    print(f"  Starting server on http://{host}:{port}")
    print("  First login: admin / breachelens (password change required)\n")
    def open_browser():
        time.sleep(2.0); url=f"http://{host}:{port}/"
        try: webbrowser.open(url); print(f"  Browser opened: {url}")
        except Exception: print(f"  Open manually: {url}")
    threading.Thread(target=open_browser,daemon=True).start()
    try:
        import uvicorn
        uvicorn.run("breachelens.main:app",host=host,port=port,log_level="info",access_log=False)
    except KeyboardInterrupt: print("\n  Pharos stopped.")
    except Exception as exc:
        print(f"\n  ERROR: {exc}"); input("\n  Press Enter to exit..."); sys.exit(1)
if __name__=="__main__": main()
