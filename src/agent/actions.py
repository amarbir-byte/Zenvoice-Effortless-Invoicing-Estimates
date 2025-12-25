"""
Action definitions and parsing for the browser agent.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any
from enum import Enum, auto
import json
import logging

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Types of actions the agent can perform."""
    SCROLL = auto()
    CLICK = auto()
    DOUBLE_CLICK = auto()
    RIGHT_CLICK = auto()
    TYPE = auto()
    PRESS_KEY = auto()
    MOVE_MOUSE = auto()
    HOVER = auto()
    DRAG = auto()
    SELECT = auto()
    WAIT = auto()
    NAVIGATE = auto()
    SCREENSHOT = auto()
    DONE = auto()
    ERROR = auto()


@dataclass
class Action:
    """Represents an action to be performed by the agent."""
    action_type: ActionType
    thought: str = ""
    target: str = ""  # CSS selector or element identifier
    value: str = ""  # Text to type, URL to navigate, etc.
    scroll_amount: int = 0  # Pixels to scroll (positive=down)
    mouse_path: List[Tuple[float, float]] = field(default_factory=list)
    coordinates: Optional[Tuple[float, float]] = None  # x, y for mouse actions
    options: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Action':
        """Create Action from dictionary (LLM output)."""
        action_str = data.get("action", "wait").lower().strip()

        # Map action string to ActionType
        action_map = {
            "scroll": ActionType.SCROLL,
            "click": ActionType.CLICK,
            "double_click": ActionType.DOUBLE_CLICK,
            "doubleclick": ActionType.DOUBLE_CLICK,
            "right_click": ActionType.RIGHT_CLICK,
            "rightclick": ActionType.RIGHT_CLICK,
            "type": ActionType.TYPE,
            "press_key": ActionType.PRESS_KEY,
            "presskey": ActionType.PRESS_KEY,
            "key": ActionType.PRESS_KEY,
            "move_mouse": ActionType.MOVE_MOUSE,
            "movemouse": ActionType.MOVE_MOUSE,
            "move": ActionType.MOVE_MOUSE,
            "hover": ActionType.HOVER,
            "drag": ActionType.DRAG,
            "select": ActionType.SELECT,
            "wait": ActionType.WAIT,
            "pause": ActionType.WAIT,
            "navigate": ActionType.NAVIGATE,
            "goto": ActionType.NAVIGATE,
            "screenshot": ActionType.SCREENSHOT,
            "done": ActionType.DONE,
            "complete": ActionType.DONE,
            "finished": ActionType.DONE,
            "error": ActionType.ERROR,
        }

        action_type = action_map.get(action_str, ActionType.WAIT)

        # Parse mouse path if provided
        mouse_path = []
        raw_path = data.get("mouse_path", [])
        if raw_path:
            for point in raw_path:
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    mouse_path.append((float(point[0]), float(point[1])))
                elif isinstance(point, dict):
                    mouse_path.append((
                        float(point.get("x", 0)),
                        float(point.get("y", 0)),
                    ))

        # Parse coordinates
        coordinates = None
        if "x" in data and "y" in data:
            coordinates = (float(data["x"]), float(data["y"]))
        elif "coordinates" in data:
            coords = data["coordinates"]
            if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                coordinates = (float(coords[0]), float(coords[1]))

        # Handle scroll_amount safely (might be None or missing)
        scroll_amount_raw = data.get("scroll_amount")
        scroll_amount = int(scroll_amount_raw) if scroll_amount_raw is not None else 0

        return cls(
            action_type=action_type,
            thought=data.get("thought", ""),
            target=data.get("target", "") or data.get("selector", "") or "",
            value=data.get("value", "") or data.get("text", "") or "",
            scroll_amount=scroll_amount,
            mouse_path=mouse_path,
            coordinates=coordinates,
            options=data.get("options", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> 'Action':
        """Create Action from JSON string."""
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse action JSON: {e}")
            return cls(
                action_type=ActionType.ERROR,
                thought=f"JSON parse error: {e}",
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert Action to dictionary."""
        return {
            "action": self.action_type.name.lower(),
            "thought": self.thought,
            "target": self.target,
            "value": self.value,
            "scroll_amount": self.scroll_amount,
            "mouse_path": self.mouse_path,
            "coordinates": self.coordinates,
            "options": self.options,
        }

    def to_json(self) -> str:
        """Convert Action to JSON string."""
        return json.dumps(self.to_dict())

    @property
    def is_terminal(self) -> bool:
        """Check if this action ends the task."""
        return self.action_type in (ActionType.DONE, ActionType.ERROR)

    @property
    def requires_target(self) -> bool:
        """Check if this action requires a target element."""
        return self.action_type in (
            ActionType.CLICK,
            ActionType.DOUBLE_CLICK,
            ActionType.RIGHT_CLICK,
            ActionType.TYPE,
            ActionType.HOVER,
            ActionType.SELECT,
        )

    @property
    def requires_value(self) -> bool:
        """Check if this action requires a value."""
        return self.action_type in (
            ActionType.TYPE,
            ActionType.PRESS_KEY,
            ActionType.NAVIGATE,
            ActionType.SELECT,
        )

    def validate(self) -> Tuple[bool, str]:
        """
        Validate the action.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if self.requires_target and not self.target:
            return False, f"Action {self.action_type.name} requires a target"

        if self.requires_value and not self.value:
            return False, f"Action {self.action_type.name} requires a value"

        if self.action_type == ActionType.SCROLL and self.scroll_amount == 0:
            return False, "Scroll action requires non-zero scroll_amount"

        return True, ""

    def __str__(self) -> str:
        """Human-readable string representation."""
        parts = [f"[{self.action_type.name}]"]

        if self.target:
            parts.append(f"target='{self.target[:30]}'")

        if self.value:
            parts.append(f"value='{self.value[:30]}'")

        if self.scroll_amount:
            parts.append(f"scroll={self.scroll_amount}px")

        if self.coordinates:
            parts.append(f"@({self.coordinates[0]:.0f},{self.coordinates[1]:.0f})")

        if self.thought:
            parts.append(f"// {self.thought[:50]}")

        return " ".join(parts)


@dataclass
class ActionResult:
    """Result of executing an action."""
    success: bool
    action: Action
    message: str = ""
    screenshot: Optional[bytes] = None
    duration: float = 0.0  # seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action.to_dict(),
            "message": self.message,
            "duration": self.duration,
            "has_screenshot": self.screenshot is not None,
        }


class ActionHistory:
    """Tracks action history for the agent."""

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._actions: List[ActionResult] = []

    def add(self, result: ActionResult):
        """Add an action result to history."""
        self._actions.append(result)

        # Trim if exceeds max size
        if len(self._actions) > self.max_size:
            self._actions = self._actions[-self.max_size:]

    def get_last(self, n: int = 1) -> List[ActionResult]:
        """Get last N action results."""
        return self._actions[-n:]

    def get_summary(self, last_n: int = 10) -> str:
        """Get a text summary of recent actions."""
        recent = self.get_last(last_n)

        lines = ["=== RECENT ACTIONS ==="]
        for i, result in enumerate(recent, 1):
            status = "OK" if result.success else "FAIL"
            lines.append(f"{i}. [{status}] {result.action}")

        return "\n".join(lines)

    def clear(self):
        """Clear action history."""
        self._actions.clear()

    def __len__(self) -> int:
        return len(self._actions)

    def __iter__(self):
        return iter(self._actions)
