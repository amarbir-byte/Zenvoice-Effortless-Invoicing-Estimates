#!/usr/bin/env python3
"""
Start Chrome with remote debugging enabled.
This allows the agent to connect to your browser.
"""

import subprocess
import sys
import os
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import BrowserConfig


def find_chrome() -> str:
    """Find Chrome executable."""
    config = BrowserConfig()
    return config.chrome_path


def start_chrome(url: str = "https://www.google.com", port: int = 9222):
    """Start Chrome with remote debugging."""

    chrome_path = find_chrome()

    args = [
        chrome_path,
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        # Anti-detection
        "--disable-blink-features=AutomationControlled",
        url,
    ]

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  🌐 Starting Chrome with Remote Debugging                        ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Debug Port: {port}                                               ║
║  Opening: {url:<52} ║
║                                                                  ║
║  Chrome is ready for agent connection!                           ║
║  Now run: python run_overlay.py                                  ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""")

    try:
        # Start Chrome (non-blocking)
        process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"Chrome started (PID: {process.pid})")
        print("You can now run the agent overlay in another terminal.")

        # Wait for Chrome to exit
        process.wait()

    except FileNotFoundError:
        print(f"❌ Chrome not found at: {chrome_path}")
        print("Please install Chrome or set CHROME_PATH environment variable.")
        sys.exit(1)

    except KeyboardInterrupt:
        print("\nChrome closed.")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Start Chrome with remote debugging")
    parser.add_argument("url", nargs="?", default="https://www.google.com", help="URL to open")
    parser.add_argument("--port", type=int, default=9222, help="Debug port (default: 9222)")

    args = parser.parse_args()

    start_chrome(args.url, args.port)


if __name__ == "__main__":
    main()
