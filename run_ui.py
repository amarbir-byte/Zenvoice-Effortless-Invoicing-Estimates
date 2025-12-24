#!/usr/bin/env python3
"""
Launch the Browser Agent UI.
Opens a web interface with browser on left, reasoning on right.
"""

import sys
import webbrowser
import time
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   🌐 Browser Agent - Visual Interface                            ║
║   ─────────────────────────────────────────────────────────      ║
║   Browser on LEFT  |  Reasoning on RIGHT                         ║
║                                                                  ║
║   Opening: http://localhost:8000                                 ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""")

    # Open browser after short delay
    def open_browser():
        time.sleep(1.5)
        webbrowser.open('http://localhost:8000')

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # Start server
    from ui.server import main as start_server
    start_server()


if __name__ == "__main__":
    main()
