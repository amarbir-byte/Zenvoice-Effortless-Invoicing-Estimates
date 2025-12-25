"""
Overlay Launcher - Connects the floating panel to the browser agent.
Uses a persistent event loop for async operations.
"""

import asyncio
import threading
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from overlay.panel import OverlayPanel
from src.browser.controller import BrowserController
from src.browser.cdp_client import CDPClient
from src.agent.llm import LMStudioClient
from src.agent.orchestrator import AgentOrchestrator, TaskConfig
from src.agent.actions import Action, ActionResult
from config import config, load_config_from_env


class AsyncLoopThread:
    """Manages a persistent event loop in a background thread."""

    def __init__(self):
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None

    def start(self):
        """Start the event loop thread."""
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def _run_loop(self):
        """Run the event loop forever."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run_coroutine(self, coro):
        """Run a coroutine in the event loop."""
        if self.loop is None:
            raise RuntimeError("Event loop not started")
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def stop(self):
        """Stop the event loop."""
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)


class OverlayAgent:
    """
    Manages the connection between the overlay panel and browser agent.
    """

    def __init__(self):
        self.panel = OverlayPanel(
            on_task=self._on_task,
            on_stop=self._on_stop,
            on_connect=self._on_connect,
        )

        self.browser: Optional[BrowserController] = None
        self.llm: Optional[LMStudioClient] = None
        self.agent: Optional[AgentOrchestrator] = None

        # Persistent event loop for async operations
        self.async_loop = AsyncLoopThread()

    def _on_connect(self):
        """Handle connect button - connect to existing Chrome."""
        future = self.async_loop.run_coroutine(self._connect_to_chrome())

        # Handle result in background
        def on_done(f):
            try:
                f.result()
            except Exception as e:
                self.panel.add_log('error', f'Connection error: {str(e)}')

        future.add_done_callback(on_done)

    async def _connect_to_chrome(self):
        """Connect to Chrome with remote debugging enabled."""
        try:
            self.panel.add_log('status', 'Connecting to Chrome...')

            # Create CDP client
            cdp = CDPClient(port=config.browser.remote_debugging_port)

            try:
                connected = await cdp.connect()
                if not connected:
                    raise RuntimeError("Could not connect to Chrome")
            except Exception as e:
                self.panel.add_log('error', 'Chrome not found with remote debugging')
                self.panel.add_log('status', 'Start Chrome with:')
                self.panel.add_log('status', 'chrome --remote-debugging-port=9222')
                self.panel.set_connected(False)
                return

            self.panel.add_log('status', 'Connected to Chrome')

            # Create browser controller and use the connected CDP
            self.browser = BrowserController(
                port=config.browser.remote_debugging_port,
            )
            self.browser.cdp = cdp

            # Apply stealth patches
            await self.browser._apply_stealth()
            self.panel.add_log('status', 'Applied stealth patches')

            # Connect to LM Studio
            self.panel.add_log('status', 'Connecting to LM Studio...')

            self.llm = LMStudioClient(
                base_url=config.lm_studio.base_url,
                model=config.lm_studio.model,
            )

            if not await self.llm.check_health():
                self.panel.add_log('error', 'LM Studio not available')
                self.panel.add_log('status', 'Start LM Studio and load a model')
                self.panel.set_connected(True)  # Still connected to Chrome
                return

            models = await self.llm.list_models()
            self.panel.add_log('status', f'LM Studio connected ({len(models)} models)')

            # Create agent
            self.agent = AgentOrchestrator(self.browser, self.llm)
            await self.agent.initialize()

            self.panel.add_log('status', 'Agent ready!')
            self.panel.set_connected(True)

        except Exception as e:
            self.panel.add_log('error', f'Connection failed: {str(e)}')
            self.panel.set_connected(False)
            raise

    def _on_task(self, task: str):
        """Handle task submission."""
        future = self.async_loop.run_coroutine(self._run_task(task))

        def on_done(f):
            try:
                f.result()
            except Exception as e:
                self.panel.add_log('error', f'Task error: {str(e)}')
            finally:
                self.panel.set_task_running(False)

        future.add_done_callback(on_done)

    async def _run_task(self, task: str):
        """Run a task with the agent."""
        if not self.agent:
            self.panel.add_log('error', 'Agent not connected')
            return

        try:
            self.panel.set_task_running(True)
            self.panel.add_log('status', f'Starting task: {task}')

            # Action callback
            def on_action(action: Action, result: ActionResult):
                if action.thought:
                    self.panel.add_log('thinking', action.thought)

                status = 'action' if result.success else 'error'
                details = f"{action.action_type.name}"
                if action.target:
                    details += f" → {action.target[:30]}"
                if action.value:
                    details += f" = {action.value[:20]}"

                self.panel.add_log(status, details, result.message if not result.success else None)

            task_config = TaskConfig(
                max_actions=50,
                verbose=True,
                screenshot_on_action=False,
                use_vision=False,  # Disable for now to avoid OCR issues
                use_dom=True,
                on_action=on_action,
            )

            result = await self.agent.run_task(task, task_config)

            if result.success:
                self.panel.add_log('status', f'✓ Task completed ({result.actions_taken} actions)')
            else:
                self.panel.add_log('error', f'Task failed: {result.message}')

        except Exception as e:
            self.panel.add_log('error', f'Error: {str(e)}')
            raise

    def _on_stop(self):
        """Handle stop button."""
        if self.agent:
            self.agent.stop()
            self.panel.add_log('status', 'Task stopped')

    def run(self):
        """Run the overlay agent."""
        # Start the async event loop thread
        self.async_loop.start()

        # Run the UI (blocks until closed)
        self.panel.run()

        # Cleanup
        self.async_loop.stop()

    async def cleanup(self):
        """Clean up resources."""
        if self.browser and self.browser.cdp:
            await self.browser.cdp.disconnect()

        if self.llm:
            await self.llm.close()


def main():
    """Main entry point."""
    load_config_from_env()

    print("""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   🧠 Browser Agent - Desktop Overlay                             ║
║   ─────────────────────────────────────────────────────────      ║
║                                                                  ║
║   1. Start Chrome with: chrome --remote-debugging-port=9222     ║
║   2. Click 'Connect to Chrome' in the overlay panel              ║
║   3. Type a task and press Enter or click Run                    ║
║                                                                  ║
║   The agent panel will float on top of your browser!             ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""")

    agent = OverlayAgent()
    agent.run()


if __name__ == "__main__":
    main()
