"""
Web UI Server for Browser Automation Agent.
Provides a split-view interface: browser on left, reasoning on right.
"""

import asyncio
import base64
import json
import logging
import time
from typing import Optional, Dict, Any, List
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config, load_config_from_env
from src.browser.controller import BrowserController
from src.agent.llm import LMStudioClient
from src.agent.orchestrator import AgentOrchestrator, TaskConfig
from src.agent.actions import Action, ActionResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ui-server")

app = FastAPI(title="Browser Agent UI")

# Global state
class AgentState:
    def __init__(self):
        self.browser: Optional[BrowserController] = None
        self.llm: Optional[LMStudioClient] = None
        self.agent: Optional[AgentOrchestrator] = None
        self.websockets: List[WebSocket] = []
        self.is_running = False
        self.current_task: Optional[str] = None
        self.screenshot_task: Optional[asyncio.Task] = None

state = AgentState()


class TaskRequest(BaseModel):
    task: str
    url: Optional[str] = None


async def broadcast(message: Dict[str, Any]):
    """Send message to all connected clients."""
    if not state.websockets:
        return

    data = json.dumps(message)
    disconnected = []

    for ws in state.websockets:
        try:
            await ws.send_text(data)
        except Exception:
            disconnected.append(ws)

    for ws in disconnected:
        state.websockets.remove(ws)


async def screenshot_loop():
    """Continuously capture and broadcast screenshots."""
    while state.is_running and state.browser and state.browser.cdp:
        try:
            screenshot = await state.browser.cdp.screenshot()
            b64 = base64.b64encode(screenshot).decode('utf-8')

            await broadcast({
                "type": "screenshot",
                "data": b64,
                "timestamp": time.time(),
            })

            await asyncio.sleep(0.5)  # 2 FPS
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            await asyncio.sleep(1)


async def initialize_agent():
    """Initialize browser and agent."""
    if state.browser:
        return True

    try:
        await broadcast({"type": "status", "message": "Starting browser..."})

        # Create browser
        state.browser = BrowserController(
            headless=False,
            window_width=1280,
            window_height=800,
        )
        await state.browser.start()

        await broadcast({"type": "status", "message": "Connecting to LM Studio..."})

        # Create LLM client
        state.llm = LMStudioClient(
            base_url=config.lm_studio.base_url,
            model=config.lm_studio.model,
        )

        # Check LLM health
        if not await state.llm.check_health():
            await broadcast({
                "type": "error",
                "message": "LM Studio not available. Please start LM Studio and load a model."
            })
            return False

        await broadcast({"type": "status", "message": "Initializing agent..."})

        # Create agent
        state.agent = AgentOrchestrator(state.browser, state.llm)
        await state.agent.initialize()

        await broadcast({"type": "status", "message": "Ready!", "ready": True})

        # Start screenshot loop
        state.is_running = True
        state.screenshot_task = asyncio.create_task(screenshot_loop())

        return True

    except Exception as e:
        logger.error(f"Initialization error: {e}")
        await broadcast({"type": "error", "message": str(e)})
        return False


async def run_agent_task(task: str, url: Optional[str] = None):
    """Run a task with the agent."""
    if not state.agent:
        if not await initialize_agent():
            return

    try:
        # Navigate if URL provided
        if url:
            await broadcast({
                "type": "thinking",
                "thought": f"Navigating to {url}...",
            })
            await state.browser.navigate(url)
            await asyncio.sleep(2)

        state.current_task = task

        await broadcast({
            "type": "task_start",
            "task": task,
        })

        # Action callback
        async def on_action(action: Action, result: ActionResult):
            await broadcast({
                "type": "action",
                "thought": action.thought,
                "action": action.action_type.name,
                "target": action.target,
                "value": action.value,
                "success": result.success,
                "message": result.message,
                "timestamp": time.time(),
            })

        # State change callback
        async def on_state(viewport_state):
            await broadcast({
                "type": "state",
                "url": viewport_state.url,
                "title": viewport_state.title,
                "scroll": viewport_state.scroll_percentage,
                "elements": len(viewport_state.interactive_elements),
            })

        # Run task
        task_config = TaskConfig(
            max_actions=50,
            verbose=True,
            screenshot_on_action=True,
            use_vision=True,
            use_dom=True,
            on_action=lambda a, r: asyncio.create_task(on_action(a, r)),
            on_state_change=lambda s: asyncio.create_task(on_state(s)),
        )

        result = await state.agent.run_task(task, task_config)

        await broadcast({
            "type": "task_complete",
            "success": result.success,
            "message": result.message,
            "actions": result.actions_taken,
            "duration": result.duration,
        })

    except Exception as e:
        logger.error(f"Task error: {e}")
        await broadcast({
            "type": "error",
            "message": str(e),
        })
    finally:
        state.current_task = None


@app.get("/")
async def index():
    """Serve the main UI."""
    ui_path = Path(__file__).parent / "index.html"
    return FileResponse(ui_path)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await websocket.accept()
    state.websockets.append(websocket)

    logger.info(f"Client connected. Total: {len(state.websockets)}")

    # Send initial state
    await websocket.send_json({
        "type": "connected",
        "ready": state.agent is not None,
    })

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "init":
                asyncio.create_task(initialize_agent())

            elif data.get("type") == "task":
                task = data.get("task", "")
                url = data.get("url")
                if task:
                    asyncio.create_task(run_agent_task(task, url))

            elif data.get("type") == "navigate":
                url = data.get("url", "")
                if url and state.browser:
                    await state.browser.navigate(url)
                    await broadcast({
                        "type": "thinking",
                        "thought": f"Navigated to {url}",
                    })

            elif data.get("type") == "stop":
                if state.agent:
                    state.agent.stop()
                    await broadcast({
                        "type": "status",
                        "message": "Task stopped",
                    })

    except WebSocketDisconnect:
        state.websockets.remove(websocket)
        logger.info(f"Client disconnected. Total: {len(state.websockets)}")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    state.is_running = False

    if state.screenshot_task:
        state.screenshot_task.cancel()

    if state.browser:
        await state.browser.stop()

    if state.llm:
        await state.llm.close()


def main():
    """Run the UI server."""
    load_config_from_env()

    print("""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   🌐 Browser Agent UI                                            ║
║   ─────────────────────────────────────────────────────────      ║
║   Open in browser: http://localhost:8000                         ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""")

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
