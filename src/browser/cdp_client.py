"""
Chrome DevTools Protocol (CDP) client for browser communication.
Provides low-level access to Chrome without triggering automation detection.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Callable, List
import aiohttp
import websockets

logger = logging.getLogger(__name__)


class CDPClient:
    """
    Chrome DevTools Protocol client.
    Connects to Chrome via WebSocket and executes CDP commands.
    """

    def __init__(self, host: str = "localhost", port: int = 9222):
        self.host = host
        self.port = port
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.session_id: Optional[str] = None
        self.target_id: Optional[str] = None
        self._message_id = 0
        self._callbacks: Dict[int, asyncio.Future] = {}
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._receive_task: Optional[asyncio.Task] = None

    @property
    def debug_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    async def connect(self, target_url: Optional[str] = None) -> bool:
        """
        Connect to Chrome DevTools.

        Args:
            target_url: Optional URL to navigate to after connecting.

        Returns:
            True if connected successfully.
        """
        try:
            # Get list of available targets
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.debug_url}/json") as resp:
                    targets = await resp.json()

            # Find a page target or create one
            page_target = None
            for target in targets:
                if target.get("type") == "page":
                    page_target = target
                    break

            if not page_target:
                # Create a new target
                async with aiohttp.ClientSession() as session:
                    url = target_url or "about:blank"
                    async with session.get(
                        f"{self.debug_url}/json/new?{url}"
                    ) as resp:
                        page_target = await resp.json()

            self.target_id = page_target["id"]
            ws_url = page_target["webSocketDebuggerUrl"]

            # Connect via WebSocket
            self.ws = await websockets.connect(
                ws_url,
                max_size=100 * 1024 * 1024,  # 100MB max message size
                ping_interval=30,
                ping_timeout=10,
            )

            # Start receiving messages
            self._receive_task = asyncio.create_task(self._receive_loop())

            # Enable required domains
            await self.send("Page.enable")
            await self.send("DOM.enable")
            await self.send("Runtime.enable")
            await self.send("Network.enable")
            await self.send("Input.enable")

            logger.info(f"Connected to Chrome target: {self.target_id}")

            if target_url and target_url != "about:blank":
                await self.navigate(target_url)

            return True

        except Exception as e:
            logger.error(f"Failed to connect to Chrome: {e}")
            return False

    async def disconnect(self):
        """Disconnect from Chrome."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self.ws:
            await self.ws.close()
            self.ws = None

        logger.info("Disconnected from Chrome")

    async def send(
        self, method: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send a CDP command and wait for response.

        Args:
            method: CDP method name (e.g., "Page.navigate")
            params: Optional parameters for the method

        Returns:
            Response from Chrome
        """
        if not self.ws:
            raise RuntimeError("Not connected to Chrome")

        self._message_id += 1
        message_id = self._message_id

        message = {
            "id": message_id,
            "method": method,
            "params": params or {},
        }

        # Create a future to wait for the response
        future = asyncio.Future()
        self._callbacks[message_id] = future

        await self.ws.send(json.dumps(message))
        logger.debug(f"Sent: {method} (id={message_id})")

        try:
            result = await asyncio.wait_for(future, timeout=30)
            return result
        except asyncio.TimeoutError:
            del self._callbacks[message_id]
            raise TimeoutError(f"CDP command timed out: {method}")

    async def _receive_loop(self):
        """Background task to receive messages from Chrome."""
        try:
            async for message in self.ws:
                data = json.loads(message)

                # Handle command responses
                if "id" in data:
                    message_id = data["id"]
                    if message_id in self._callbacks:
                        future = self._callbacks.pop(message_id)
                        if "error" in data:
                            future.set_exception(
                                RuntimeError(data["error"].get("message", "Unknown error"))
                            )
                        else:
                            future.set_result(data.get("result", {}))

                # Handle events
                if "method" in data:
                    method = data["method"]
                    params = data.get("params", {})
                    await self._handle_event(method, params)

        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in receive loop: {e}")

    async def _handle_event(self, method: str, params: Dict[str, Any]):
        """Handle CDP events."""
        handlers = self._event_handlers.get(method, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(params)
                else:
                    handler(params)
            except Exception as e:
                logger.error(f"Error in event handler for {method}: {e}")

    def on(self, event: str, handler: Callable):
        """Register an event handler."""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def off(self, event: str, handler: Optional[Callable] = None):
        """Remove an event handler."""
        if event in self._event_handlers:
            if handler:
                self._event_handlers[event].remove(handler)
            else:
                del self._event_handlers[event]

    # High-level convenience methods

    async def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to a URL."""
        result = await self.send("Page.navigate", {"url": url})
        # Wait for page to load
        await self.wait_for_load()
        return result

    async def wait_for_load(self, timeout: float = 30):
        """Wait for page to finish loading."""
        load_event = asyncio.Event()

        def on_load(params):
            load_event.set()

        self.on("Page.loadEventFired", on_load)

        try:
            await asyncio.wait_for(load_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Page load timeout")
        finally:
            self.off("Page.loadEventFired", on_load)

    async def evaluate(self, expression: str) -> Any:
        """Execute JavaScript and return the result."""
        result = await self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )

        if "exceptionDetails" in result:
            raise RuntimeError(
                result["exceptionDetails"].get("text", "JavaScript error")
            )

        return result.get("result", {}).get("value")

    async def screenshot(self, format: str = "png", quality: int = 90) -> bytes:
        """Capture a screenshot."""
        params = {"format": format}
        if format == "jpeg":
            params["quality"] = quality

        result = await self.send("Page.captureScreenshot", params)
        import base64
        return base64.b64decode(result["data"])

    async def get_document(self) -> Dict[str, Any]:
        """Get the DOM document."""
        return await self.send("DOM.getDocument", {"depth": -1, "pierce": True})

    async def query_selector(self, selector: str) -> Optional[int]:
        """Query for an element by CSS selector."""
        doc = await self.get_document()
        root_id = doc["root"]["nodeId"]

        try:
            result = await self.send(
                "DOM.querySelector",
                {"nodeId": root_id, "selector": selector},
            )
            node_id = result.get("nodeId", 0)
            return node_id if node_id > 0 else None
        except Exception:
            return None

    async def query_selector_all(self, selector: str) -> List[int]:
        """Query for all elements matching a CSS selector."""
        doc = await self.get_document()
        root_id = doc["root"]["nodeId"]

        try:
            result = await self.send(
                "DOM.querySelectorAll",
                {"nodeId": root_id, "selector": selector},
            )
            return result.get("nodeIds", [])
        except Exception:
            return []

    async def get_box_model(self, node_id: int) -> Optional[Dict[str, Any]]:
        """Get the box model for an element."""
        try:
            result = await self.send("DOM.getBoxModel", {"nodeId": node_id})
            return result.get("model")
        except Exception:
            return None

    async def get_element_bounds(self, selector: str) -> Optional[Dict[str, float]]:
        """Get the bounding box for an element."""
        node_id = await self.query_selector(selector)
        if not node_id:
            return None

        box_model = await self.get_box_model(node_id)
        if not box_model:
            return None

        # Box model content quad: [x1,y1, x2,y2, x3,y3, x4,y4]
        content = box_model.get("border", box_model.get("content", []))
        if len(content) < 8:
            return None

        x = min(content[0], content[2], content[4], content[6])
        y = min(content[1], content[3], content[5], content[7])
        width = max(content[0], content[2], content[4], content[6]) - x
        height = max(content[1], content[3], content[5], content[7]) - y

        return {"x": x, "y": y, "width": width, "height": height}

    async def get_viewport_size(self) -> Dict[str, int]:
        """Get the current viewport size."""
        result = await self.evaluate(
            "JSON.stringify({width: window.innerWidth, height: window.innerHeight})"
        )
        return json.loads(result)

    async def get_scroll_position(self) -> Dict[str, int]:
        """Get the current scroll position."""
        result = await self.evaluate(
            "JSON.stringify({x: window.scrollX, y: window.scrollY})"
        )
        return json.loads(result)

    async def get_page_size(self) -> Dict[str, int]:
        """Get the full page size."""
        result = await self.evaluate(
            """JSON.stringify({
                width: Math.max(document.body.scrollWidth, document.documentElement.scrollWidth),
                height: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)
            })"""
        )
        return json.loads(result)
