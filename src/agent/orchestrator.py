"""
Agent Orchestrator - Ties together all components for browser automation.
Coordinates between LLM, browser, and input simulation.
"""

import asyncio
import logging
import re
import time
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field

from ..browser.controller import BrowserController
from ..browser.cdp_client import CDPClient
from ..human.mouse import MouseSimulator
from ..human.keyboard import KeyboardSimulator
from ..human.timing import HumanTiming
from ..dom.extractor import DOMExtractor
from ..dom.elements import ViewportState
from ..vision.screenshot import ScreenshotCapture
from ..vision.processor import VisionProcessor
from .llm import LMStudioClient, BROWSER_AGENT_PROMPT
from .actions import Action, ActionType, ActionResult, ActionHistory

logger = logging.getLogger(__name__)


@dataclass
class TaskConfig:
    """Configuration for a task execution."""
    max_actions: int = 100
    action_timeout: float = 30.0
    screenshot_on_action: bool = True
    use_vision: bool = True
    use_dom: bool = True
    verbose: bool = True
    on_action: Optional[Callable[[Action, ActionResult], None]] = None
    on_state_change: Optional[Callable[[ViewportState], None]] = None


@dataclass
class TaskResult:
    """Result of a completed task."""
    success: bool
    message: str
    actions_taken: int
    duration: float
    final_url: str = ""
    final_screenshot: Optional[bytes] = None
    history: List[ActionResult] = field(default_factory=list)


class AgentOrchestrator:
    """
    Main orchestrator that coordinates all agent components.
    Manages the perception-reasoning-action loop.
    """

    def __init__(
        self,
        browser: BrowserController,
        llm: LMStudioClient,
        system_prompt: str = BROWSER_AGENT_PROMPT,
    ):
        self.browser = browser
        self.llm = llm
        self.system_prompt = system_prompt

        # These will be initialized when browser starts
        self.cdp: Optional[CDPClient] = None
        self.mouse: Optional[MouseSimulator] = None
        self.keyboard: Optional[KeyboardSimulator] = None
        self.timing: Optional[HumanTiming] = None
        self.dom_extractor: Optional[DOMExtractor] = None
        self.screenshot: Optional[ScreenshotCapture] = None
        self.vision: Optional[VisionProcessor] = None

        self.history = ActionHistory()
        self._running = False
        self._current_task: Optional[str] = None

    async def initialize(self):
        """Initialize all components after browser is started."""
        if not self.browser.cdp:
            raise RuntimeError("Browser not started. Call browser.start() first.")

        self.cdp = self.browser.cdp
        self.timing = HumanTiming()
        self.mouse = MouseSimulator(self.cdp, self.timing)
        self.keyboard = KeyboardSimulator(self.cdp, self.timing)
        self.dom_extractor = DOMExtractor(self.cdp)
        self.screenshot = ScreenshotCapture(self.cdp)
        self.vision = VisionProcessor()

        logger.info("Agent orchestrator initialized")

    async def run_task(
        self,
        task: str,
        config: Optional[TaskConfig] = None,
    ) -> TaskResult:
        """
        Execute a task using the agent loop.

        Args:
            task: Natural language task description
            config: Optional task configuration

        Returns:
            TaskResult with execution details
        """
        config = config or TaskConfig()
        self._current_task = task
        self._running = True
        self.history.clear()

        start_time = time.time()
        actions_taken = 0
        last_error = ""

        logger.info(f"Starting task: {task}")

        try:
            while self._running and actions_taken < config.max_actions:
                # 1. PERCEIVE - Get current state
                state = await self._get_state(config)

                if config.on_state_change:
                    config.on_state_change(state)

                if config.verbose:
                    logger.debug(f"State: {state.url} - {len(state.interactive_elements)} elements")

                # 2. REASON - Get next action from LLM
                action = await self._get_next_action(state, task)

                if config.verbose:
                    logger.info(f"Action {actions_taken + 1}: {action}")

                # Check for terminal action
                if action.is_terminal:
                    if action.action_type == ActionType.DONE:
                        return TaskResult(
                            success=True,
                            message=action.thought or "Task completed successfully",
                            actions_taken=actions_taken,
                            duration=time.time() - start_time,
                            final_url=state.url,
                            final_screenshot=await self.cdp.screenshot() if config.screenshot_on_action else None,
                            history=list(self.history),
                        )
                    else:  # ERROR
                        return TaskResult(
                            success=False,
                            message=action.thought or "Task failed",
                            actions_taken=actions_taken,
                            duration=time.time() - start_time,
                            final_url=state.url,
                            history=list(self.history),
                        )

                # 3. ACT - Execute the action
                result = await self._execute_action(action, config)
                self.history.add(result)
                actions_taken += 1

                if config.on_action:
                    config.on_action(action, result)

                if not result.success:
                    last_error = result.message
                    logger.warning(f"Action failed: {result.message}")

                # Brief pause between actions
                await self.timing.wait_action()

        except asyncio.CancelledError:
            logger.info("Task cancelled")
            return TaskResult(
                success=False,
                message="Task was cancelled",
                actions_taken=actions_taken,
                duration=time.time() - start_time,
                history=list(self.history),
            )

        except Exception as e:
            logger.error(f"Task error: {e}", exc_info=True)
            return TaskResult(
                success=False,
                message=f"Task error: {str(e)}",
                actions_taken=actions_taken,
                duration=time.time() - start_time,
                history=list(self.history),
            )

        finally:
            self._running = False
            self._current_task = None

        # Max actions reached
        return TaskResult(
            success=False,
            message=f"Max actions ({config.max_actions}) reached. Last error: {last_error}",
            actions_taken=actions_taken,
            duration=time.time() - start_time,
            history=list(self.history),
        )

    async def _get_state(self, config: TaskConfig) -> ViewportState:
        """Get current viewport state using DOM and/or vision."""
        state = await self.dom_extractor.extract_viewport_state(
            include_screenshot=config.use_vision,
        )

        # Optionally enhance with vision
        if config.use_vision and state.screenshot_base64:
            import base64
            screenshot_bytes = base64.b64decode(state.screenshot_base64)

            # Get OCR text regions
            vision_regions = await self.vision.extract_text(screenshot_bytes)

            # Combine with DOM elements
            if vision_regions:
                dom_dicts = [e.to_dict() for e in state.interactive_elements]
                combined = self.vision.combine_with_dom(dom_dicts, vision_regions)

                # Add OCR-enhanced text to visible_text
                ocr_text = " ".join(r.text for r in vision_regions)
                if ocr_text:
                    state.visible_text = f"{state.visible_text}\n\n[OCR]: {ocr_text[:2000]}"

        return state

    async def _get_next_action(
        self,
        state: ViewportState,
        task: str,
    ) -> Action:
        """Get the next action from the LLM."""
        # Build simple history for context
        history = []

        # Add last few actions as simple strings
        last_actions = self.history.get_last(5)
        for result in last_actions:
            action_str = f"{result.action.action_type.value}"
            if result.action.target:
                action_str += f" on {result.action.target}"
            if result.action.value:
                action_str += f" = {result.action.value[:30]}"
            status = "✓" if result.success else "✗"
            history.append({
                "role": "user",
                "content": f"{status} {action_str}",
            })

        # Detect if stuck in a loop (same action 3+ times)
        if len(last_actions) >= 3:
            recent_types = [r.action.action_type for r in last_actions[-3:]]
            if len(set(recent_types)) == 1:  # All same action type
                logger.warning(f"Loop detected: {recent_types[0].value} repeated 3 times")
                # Add a hint to break out
                history.append({
                    "role": "user",
                    "content": "⚠️ LOOP DETECTED! You've done the same action 3 times. TRY SOMETHING COMPLETELY DIFFERENT like clicking a link or using search!",
                })

        # Get action from LLM
        action_dict = await self.llm.get_action(
            system_prompt=self.system_prompt,
            viewport_state=state.to_prompt(),
            task=task,
            history=history if history else None,
        )

        return Action.from_dict(action_dict)

    async def _execute_action(
        self,
        action: Action,
        config: TaskConfig,
    ) -> ActionResult:
        """Execute an action and return the result."""
        start_time = time.time()

        try:
            # Validate action
            is_valid, error = action.validate()
            if not is_valid and action.requires_target:
                return ActionResult(
                    success=False,
                    action=action,
                    message=error,
                    duration=time.time() - start_time,
                )

            # Execute based on action type
            if action.action_type == ActionType.SCROLL:
                await self.mouse.scroll(
                    delta_y=action.scroll_amount,
                    smooth=True,
                )

            elif action.action_type == ActionType.CLICK:
                if action.target:
                    success = await self.mouse.click_element(action.target)
                    if not success:
                        return ActionResult(
                            success=False,
                            action=action,
                            message=f"Element not found: {action.target}",
                            duration=time.time() - start_time,
                        )
                elif action.coordinates:
                    await self.mouse.click(*action.coordinates)

            elif action.action_type == ActionType.DOUBLE_CLICK:
                if action.coordinates:
                    await self.mouse.double_click(*action.coordinates)
                else:
                    await self.mouse.double_click()

            elif action.action_type == ActionType.RIGHT_CLICK:
                if action.coordinates:
                    await self.mouse.right_click(*action.coordinates)
                else:
                    await self.mouse.right_click()

            elif action.action_type == ActionType.TYPE:
                if action.target:
                    success = await self.keyboard.type_in_element(
                        action.target,
                        action.value,
                        mouse_simulator=self.mouse,
                    )
                    if not success:
                        return ActionResult(
                            success=False,
                            action=action,
                            message=f"Failed to type in element: {action.target}",
                            duration=time.time() - start_time,
                        )
                else:
                    await self.keyboard.type_text(action.value)

            elif action.action_type == ActionType.PRESS_KEY:
                await self.keyboard.press_key(action.value)

            elif action.action_type == ActionType.MOVE_MOUSE:
                if action.coordinates:
                    await self.mouse.move_to(*action.coordinates)
                elif action.mouse_path:
                    for x, y in action.mouse_path:
                        await self.mouse.move_to(x, y)

            elif action.action_type == ActionType.HOVER:
                if action.target:
                    bounds = await self.cdp.get_element_bounds(action.target)
                    if bounds:
                        center_x = bounds["x"] + bounds["width"] / 2
                        center_y = bounds["y"] + bounds["height"] / 2
                        await self.mouse.hover(center_x, center_y)
                elif action.coordinates:
                    await self.mouse.hover(*action.coordinates)

            elif action.action_type == ActionType.SELECT:
                # For select elements
                if action.target and action.value:
                    await self.cdp.evaluate(f"""
                        (function() {{
                            const select = document.querySelector('{action.target}');
                            if (select) {{
                                select.value = '{action.value}';
                                select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            }}
                        }})()
                    """)

            elif action.action_type == ActionType.NAVIGATE:
                url = self._normalize_url(action.value)
                await self.browser.navigate(url)

            elif action.action_type == ActionType.WAIT:
                await asyncio.sleep(action.options.get("duration", 1.0))

            elif action.action_type == ActionType.SCREENSHOT:
                # Just capture, result will include screenshot
                pass

            # Capture screenshot if configured
            screenshot = None
            if config.screenshot_on_action:
                screenshot = await self.cdp.screenshot()

            return ActionResult(
                success=True,
                action=action,
                message="Action executed successfully",
                screenshot=screenshot,
                duration=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Action execution error: {e}")
            return ActionResult(
                success=False,
                action=action,
                message=str(e),
                duration=time.time() - start_time,
            )

    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL to fix common LLM truncation issues.

        Args:
            url: The URL from LLM (may be truncated)

        Returns:
            Normalized URL with proper protocol and domain
        """
        if not url:
            return url

        url = url.strip()

        # Add https:// if no protocol
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Common truncated domain fixes
        truncated_fixes = {
            ".c/": ".com/",
            ".co/": ".com/",
            ".or/": ".org/",
            ".ne/": ".net/",
            ".ed/": ".edu/",
            ".go/": ".gov/",
            ".io/": ".io/",  # Already correct
        }

        for truncated, fixed in truncated_fixes.items():
            if truncated in url:
                url = url.replace(truncated, fixed)

        # Fix domain endings at end of URL (no trailing slash)
        domain_fixes = {
            ".c": ".com",
            ".co": ".com",
            ".or": ".org",
            ".ne": ".net",
            ".ed": ".edu",
            ".go": ".gov",
        }

        for truncated, fixed in domain_fixes.items():
            if url.endswith(truncated):
                url = url[:-len(truncated)] + fixed

        # Also check for truncated TLDs before path/query
        # Match patterns like google.c/search or facebook.co?q=
        pattern = r'(\.)(c|co|or|ne|ed|go)([/?#])'

        def replace_tld(match):
            dot = match.group(1)
            tld = match.group(2)
            after = match.group(3)
            tld_map = {"c": "com", "co": "com", "or": "org", "ne": "net", "ed": "edu", "go": "gov"}
            return dot + tld_map.get(tld, tld) + after

        url = re.sub(pattern, replace_tld, url)

        return url

    def stop(self):
        """Stop the current task."""
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if a task is currently running."""
        return self._running

    @property
    def current_task(self) -> Optional[str]:
        """Get the current task description."""
        return self._current_task


async def create_agent(
    lm_studio_url: str = "http://localhost:1234/v1",
    model: str = "gemma-3-12b",
    chrome_path: str = "",
    headless: bool = False,
) -> tuple[BrowserController, LMStudioClient, AgentOrchestrator]:
    """
    Create and initialize all agent components.

    Args:
        lm_studio_url: URL to LM Studio API
        model: Model name in LM Studio
        chrome_path: Path to Chrome executable
        headless: Run Chrome headless (not recommended for stealth)

    Returns:
        Tuple of (browser, llm, agent)
    """
    # Create components
    browser = BrowserController(
        chrome_path=chrome_path,
        headless=headless,
    )

    llm = LMStudioClient(
        base_url=lm_studio_url,
        model=model,
    )

    # Check LM Studio health
    if not await llm.check_health():
        logger.warning("LM Studio not available. Agent will not be able to reason.")

    # Start browser
    await browser.start()

    # Create and initialize agent
    agent = AgentOrchestrator(browser, llm)
    await agent.initialize()

    return browser, llm, agent
