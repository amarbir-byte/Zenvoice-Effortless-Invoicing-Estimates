#!/usr/bin/env python3
"""
Run the Browser Agent with Desktop Overlay.

This creates a floating panel that appears on top of your browser,
showing agent reasoning and allowing you to give it tasks.

Usage:
    1. First, start Chrome with: python start_chrome.py
       Or manually: chrome --remote-debugging-port=9222

    2. Then run this script: python run_overlay.py

    3. Click 'Connect to Chrome' in the overlay panel

    4. Type a task and watch the agent work!
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from overlay.launcher import main

if __name__ == "__main__":
    main()
