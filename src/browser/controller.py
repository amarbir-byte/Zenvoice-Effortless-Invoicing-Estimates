"""
Browser controller that manages Chrome instance and CDP connection.
Handles browser lifecycle and provides high-level browser operations.
"""

import asyncio
import logging
import subprocess
import sys
import time
from typing import Optional, Dict, Any, List
import os
import signal

from .cdp_client import CDPClient

logger = logging.getLogger(__name__)


class BrowserController:
    """
    High-level browser controller.
    Manages Chrome process and CDP connection.
    """

    def __init__(
        self,
        chrome_path: str = "",
        port: int = 9222,
        user_data_dir: Optional[str] = None,
        headless: bool = False,
        window_width: int = 1920,
        window_height: int = 1080,
    ):
        self.chrome_path = chrome_path or self._detect_chrome()
        self.port = port
        self.user_data_dir = user_data_dir
        self.headless = headless
        self.window_width = window_width
        self.window_height = window_height

        self.process: Optional[subprocess.Popen] = None
        self.cdp: Optional[CDPClient] = None
        self._started_chrome = False

    def _detect_chrome(self) -> str:
        """Auto-detect Chrome installation."""
        possible_paths = [
            # Windows
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            # Linux
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
            # macOS
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]

        # Check LOCALAPPDATA on Windows
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            possible_paths.insert(
                0, os.path.join(local_app_data, r"Google\Chrome\Application\chrome.exe")
            )

        for path in possible_paths:
            if os.path.exists(path):
                return path

        # Try finding in PATH
        import shutil
        for name in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]:
            path = shutil.which(name)
            if path:
                return path

        raise FileNotFoundError(
            "Chrome not found. Please install Chrome or specify the path manually."
        )

    def _build_chrome_args(self) -> List[str]:
        """Build Chrome command line arguments."""
        args = [
            self.chrome_path,
            f"--remote-debugging-port={self.port}",
            f"--window-size={self.window_width},{self.window_height}",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=TranslateUI",
            "--disable-ipc-flooding-protection",
            "--disable-hang-monitor",
            "--disable-prompt-on-repost",
            "--disable-sync",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-client-side-phishing-detection",
            "--disable-default-apps",
            "--disable-extensions-except=",
            "--metrics-recording-only",
            # Anti-detection flags
            "--disable-blink-features=AutomationControlled",
        ]

        if self.user_data_dir:
            args.append(f"--user-data-dir={self.user_data_dir}")

        if self.headless:
            # Note: headless mode is more detectable
            args.append("--headless=new")

        return args

    async def start(self, url: Optional[str] = None) -> bool:
        """
        Start Chrome and connect via CDP.

        Args:
            url: Optional URL to open on start.

        Returns:
            True if started successfully.
        """
        # Check if Chrome is already running with remote debugging
        if await self._check_existing_chrome():
            logger.info("Connecting to existing Chrome instance")
        else:
            # Start new Chrome instance
            logger.info("Starting new Chrome instance")
            args = self._build_chrome_args()
            if url:
                args.append(url)

            try:
                # Start Chrome process
                self.process = subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                self._started_chrome = True

                # Wait for Chrome to start
                await asyncio.sleep(2)

                if self.process.poll() is not None:
                    raise RuntimeError("Chrome process exited immediately")

            except Exception as e:
                logger.error(f"Failed to start Chrome: {e}")
                return False

        # Connect via CDP
        self.cdp = CDPClient(port=self.port)
        connected = await self.cdp.connect(url)

        if not connected:
            logger.error("Failed to connect to Chrome via CDP")
            return False

        # Apply anti-detection measures
        await self._apply_stealth()

        logger.info("Browser started and connected successfully")
        return True

    async def _check_existing_chrome(self) -> bool:
        """Check if Chrome is already running with remote debugging."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://localhost:{self.port}/json/version",
                    timeout=aiohttp.ClientTimeout(total=2),
                ) as resp:
                    if resp.status == 200:
                        return True
        except Exception:
            pass
        return False

    async def _apply_stealth(self):
        """Apply anti-detection JavaScript patches (simplified version)."""
        # Simplified stealth - just remove webdriver flag
        stealth_js = """
        try {
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        } catch(e) {}
        """

        try:
            await self.cdp.send(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": stealth_js},
            )
            logger.debug("Applied basic stealth patch")
        except Exception as e:
            # Stealth is optional - don't fail if it doesn't work
            logger.debug(f"Stealth patch skipped: {e}")

    async def stop(self):
        """Stop the browser."""
        if self.cdp:
            await self.cdp.disconnect()
            self.cdp = None

        if self.process and self._started_chrome:
            try:
                if sys.platform == "win32":
                    self.process.terminate()
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)

                # Wait for process to exit
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if sys.platform == "win32":
                        self.process.kill()
                    else:
                        os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)

            except Exception as e:
                logger.warning(f"Error stopping Chrome: {e}")

            self.process = None
            self._started_chrome = False

        logger.info("Browser stopped")

    async def navigate(self, url: str):
        """Navigate to a URL."""
        if not self.cdp:
            raise RuntimeError("Browser not started")
        await self.cdp.navigate(url)

    async def screenshot(self) -> bytes:
        """Take a screenshot."""
        if not self.cdp:
            raise RuntimeError("Browser not started")
        return await self.cdp.screenshot()

    async def get_viewport_state(self) -> Dict[str, Any]:
        """Get current viewport state for the agent."""
        if not self.cdp:
            raise RuntimeError("Browser not started")

        viewport = await self.cdp.get_viewport_size()
        scroll = await self.cdp.get_scroll_position()
        page_size = await self.cdp.get_page_size()

        # Get current URL
        url = await self.cdp.evaluate("window.location.href")

        # Get page title
        title = await self.cdp.evaluate("document.title")

        return {
            "url": url,
            "title": title,
            "viewport": viewport,
            "scroll": scroll,
            "page_size": page_size,
        }

    async def get_visible_text(self) -> str:
        """Get visible text content."""
        if not self.cdp:
            raise RuntimeError("Browser not started")

        # Get text from visible area
        text = await self.cdp.evaluate("""
            (function() {
                const selection = window.getSelection();
                selection.removeAllRanges();

                const range = document.createRange();
                range.selectNode(document.body);
                selection.addRange(range);

                const text = selection.toString();
                selection.removeAllRanges();

                return text.substring(0, 50000);  // Limit text length
            })()
        """)

        return text or ""

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()
