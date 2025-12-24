"""
Human-like mouse movement simulation.
Uses Bezier curves and natural timing for organic mouse behavior.
"""

import asyncio
import math
import random
from typing import List, Tuple, Optional
from dataclasses import dataclass
import logging

from .timing import HumanTiming, PerlinNoise

logger = logging.getLogger(__name__)


@dataclass
class Point:
    """2D point."""
    x: float
    y: float

    def distance_to(self, other: 'Point') -> float:
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)

    def __add__(self, other: 'Point') -> 'Point':
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other: 'Point') -> 'Point':
        return Point(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> 'Point':
        return Point(self.x * scalar, self.y * scalar)

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)


class BezierCurve:
    """Cubic Bezier curve for smooth mouse paths."""

    @staticmethod
    def cubic(t: float, p0: Point, p1: Point, p2: Point, p3: Point) -> Point:
        """
        Calculate point on cubic Bezier curve at parameter t.

        Args:
            t: Parameter from 0 to 1
            p0: Start point
            p1: First control point
            p2: Second control point
            p3: End point

        Returns:
            Point on the curve
        """
        u = 1 - t
        tt = t * t
        uu = u * u
        uuu = uu * u
        ttt = tt * t

        point = p0 * uuu
        point = point + p1 * (3 * uu * t)
        point = point + p2 * (3 * u * tt)
        point = point + p3 * ttt

        return point

    @staticmethod
    def generate_path(
        start: Point,
        end: Point,
        num_points: int = 50,
        deviation: float = 50,
        rng: random.Random = None
    ) -> List[Point]:
        """
        Generate a curved path between two points.

        Args:
            start: Starting point
            end: Ending point
            num_points: Number of points in the path
            deviation: Maximum deviation for control points
            rng: Random number generator

        Returns:
            List of points forming the path
        """
        rng = rng or random.Random()

        # Calculate distance and direction
        dx = end.x - start.x
        dy = end.y - start.y
        distance = math.sqrt(dx * dx + dy * dy)

        # Generate control points with random deviation
        # Control points are perpendicular to the line
        mid_x = (start.x + end.x) / 2
        mid_y = (start.y + end.y) / 2

        # Perpendicular direction
        if distance > 0:
            perp_x = -dy / distance
            perp_y = dx / distance
        else:
            perp_x, perp_y = 0, 1

        # Random deviations for control points
        dev1 = rng.uniform(-deviation, deviation)
        dev2 = rng.uniform(-deviation, deviation)

        # Control point 1 (closer to start)
        cp1 = Point(
            start.x + dx * 0.25 + perp_x * dev1,
            start.y + dy * 0.25 + perp_y * dev1
        )

        # Control point 2 (closer to end)
        cp2 = Point(
            start.x + dx * 0.75 + perp_x * dev2,
            start.y + dy * 0.75 + perp_y * dev2
        )

        # Generate path points
        points = []
        for i in range(num_points):
            t = i / (num_points - 1)
            point = BezierCurve.cubic(t, start, cp1, cp2, end)
            points.append(point)

        return points


class MouseSimulator:
    """
    Human-like mouse movement simulator.
    Uses CDP Input domain for browser control.
    """

    def __init__(
        self,
        cdp_client,
        timing: HumanTiming = None,
        curve_deviation: float = 50,
        micro_movements: bool = True,
    ):
        self.cdp = cdp_client
        self.timing = timing or HumanTiming()
        self.curve_deviation = curve_deviation
        self.micro_movements = micro_movements

        self.current_position = Point(0, 0)
        self._rng = random.Random()
        self._perlin = PerlinNoise()

    def seed(self, value: int):
        """Set random seed for reproducibility."""
        self._rng.seed(value)
        self._perlin = PerlinNoise(value)

    async def move_to(
        self,
        x: float,
        y: float,
        duration: Optional[float] = None,
    ) -> List[Tuple[float, float]]:
        """
        Move mouse to target position with human-like curve.

        Args:
            x: Target X coordinate
            y: Target Y coordinate
            duration: Optional movement duration (auto-calculated if None)

        Returns:
            List of points traversed
        """
        start = self.current_position
        end = Point(x, y)
        distance = start.distance_to(end)

        if distance < 1:
            return [start.to_tuple()]

        # Calculate duration based on distance if not specified
        if duration is None:
            duration = self.timing.mouse_move_duration(distance)

        # Determine number of steps based on duration
        # Aim for ~60 FPS equivalent
        num_steps = max(10, int(duration * 60))

        # Generate curved path
        path = BezierCurve.generate_path(
            start, end,
            num_points=num_steps,
            deviation=self.curve_deviation * (distance / 500),  # Scale deviation with distance
            rng=self._rng
        )

        # Add micro-movements (small random variations)
        if self.micro_movements:
            path = self._add_micro_movements(path)

        # Execute the movement
        step_delay = duration / len(path)
        traversed = []

        for i, point in enumerate(path):
            # Add slight timing variation
            actual_delay = step_delay * self._rng.uniform(0.8, 1.2)

            await self._dispatch_mouse_move(point.x, point.y)
            self.current_position = point
            traversed.append(point.to_tuple())

            if i < len(path) - 1:
                await asyncio.sleep(actual_delay)

        return traversed

    def _add_micro_movements(self, path: List[Point]) -> List[Point]:
        """Add small random variations to simulate hand tremor."""
        result = []
        time = 0

        for point in path:
            # Use Perlin noise for smooth micro-movements
            noise_x = self._perlin.noise(time * 5) * 2
            noise_y = self._perlin.noise(time * 5 + 100) * 2

            new_point = Point(
                point.x + noise_x,
                point.y + noise_y
            )
            result.append(new_point)
            time += 0.1

        # Ensure exact start and end points
        if result:
            result[0] = path[0]
            result[-1] = path[-1]

        return result

    async def _dispatch_mouse_move(self, x: float, y: float):
        """Send mouse move event via CDP."""
        await self.cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": x,
            "y": y,
        })

    async def click(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        button: str = "left",
        click_count: int = 1,
    ):
        """
        Perform a click at the specified or current position.

        Args:
            x: Target X (uses current position if None)
            y: Target Y (uses current position if None)
            button: Mouse button ("left", "right", "middle")
            click_count: Number of clicks (1 for single, 2 for double)
        """
        # Move to position if specified
        if x is not None and y is not None:
            await self.move_to(x, y)
            await asyncio.sleep(self.timing.hover_delay())

        click_x = self.current_position.x
        click_y = self.current_position.y

        # Map button name to CDP button value
        button_map = {"left": "left", "right": "right", "middle": "middle"}
        cdp_button = button_map.get(button, "left")

        for i in range(click_count):
            if i > 0:
                await asyncio.sleep(self.timing.double_click_interval())

            # Mouse down
            await self.cdp.send("Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "x": click_x,
                "y": click_y,
                "button": cdp_button,
                "clickCount": i + 1,
            })

            # Small delay between down and up
            await asyncio.sleep(self.timing.click_delay())

            # Mouse up
            await self.cdp.send("Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "x": click_x,
                "y": click_y,
                "button": cdp_button,
                "clickCount": i + 1,
            })

    async def double_click(self, x: Optional[float] = None, y: Optional[float] = None):
        """Perform a double click."""
        await self.click(x, y, click_count=2)

    async def right_click(self, x: Optional[float] = None, y: Optional[float] = None):
        """Perform a right click."""
        await self.click(x, y, button="right")

    async def scroll(
        self,
        delta_x: float = 0,
        delta_y: float = 0,
        x: Optional[float] = None,
        y: Optional[float] = None,
        smooth: bool = True,
    ):
        """
        Scroll at the current or specified position.

        Args:
            delta_x: Horizontal scroll amount (positive = right)
            delta_y: Vertical scroll amount (positive = down)
            x: X position to scroll at
            y: Y position to scroll at
            smooth: Whether to perform smooth scrolling
        """
        scroll_x = x if x is not None else self.current_position.x
        scroll_y = y if y is not None else self.current_position.y

        if smooth and abs(delta_y) > 100:
            # Break into smaller scroll steps
            steps = max(3, int(abs(delta_y) / 100))
            step_delta = delta_y / steps

            for i in range(steps):
                await self.cdp.send("Input.dispatchMouseEvent", {
                    "type": "mouseWheel",
                    "x": scroll_x,
                    "y": scroll_y,
                    "deltaX": delta_x / steps,
                    "deltaY": step_delta,
                })

                if i < steps - 1:
                    await asyncio.sleep(self.timing.scroll_delay() / steps)
        else:
            await self.cdp.send("Input.dispatchMouseEvent", {
                "type": "mouseWheel",
                "x": scroll_x,
                "y": scroll_y,
                "deltaX": delta_x,
                "deltaY": delta_y,
            })

    async def scroll_to_element(
        self,
        selector: str,
        offset_y: int = 0,
    ) -> bool:
        """
        Scroll until an element is visible.

        Args:
            selector: CSS selector of the target element
            offset_y: Additional offset from top of viewport

        Returns:
            True if element was found and scrolled to
        """
        max_scrolls = 20
        scroll_amount = 300

        for _ in range(max_scrolls):
            # Check if element is in viewport
            bounds = await self.cdp.get_element_bounds(selector)
            if bounds:
                viewport = await self.cdp.get_viewport_size()

                # Check if element is visible
                if 0 <= bounds["y"] <= viewport["height"] - 50:
                    return True

                # Scroll towards element
                if bounds["y"] < 0:
                    await self.scroll(delta_y=-scroll_amount)
                else:
                    await self.scroll(delta_y=scroll_amount)

                await asyncio.sleep(self.timing.scroll_delay())
            else:
                # Element not in DOM, try scrolling down
                await self.scroll(delta_y=scroll_amount)
                await asyncio.sleep(self.timing.scroll_delay())

        return False

    async def hover(
        self,
        x: float,
        y: float,
        duration: Optional[float] = None,
    ):
        """
        Move to position and hover.

        Args:
            x: Target X
            y: Target Y
            duration: How long to hover (random if None)
        """
        await self.move_to(x, y)

        hover_time = duration if duration else self.timing.hover_delay()
        await asyncio.sleep(hover_time)

    async def drag_and_drop(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
    ):
        """
        Perform a drag and drop operation.

        Args:
            start_x: Starting X
            start_y: Starting Y
            end_x: Ending X
            end_y: Ending Y
        """
        # Move to start
        await self.move_to(start_x, start_y)
        await asyncio.sleep(self.timing.hover_delay())

        # Mouse down
        await self.cdp.send("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": start_x,
            "y": start_y,
            "button": "left",
            "clickCount": 1,
        })

        await asyncio.sleep(self.timing.micro_pause())

        # Drag to end with curve
        await self.move_to(end_x, end_y)

        await asyncio.sleep(self.timing.micro_pause())

        # Mouse up
        await self.cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": end_x,
            "y": end_y,
            "button": "left",
            "clickCount": 1,
        })

    async def click_element(self, selector: str) -> bool:
        """
        Click on an element by selector.

        Args:
            selector: CSS selector

        Returns:
            True if element was found and clicked
        """
        bounds = await self.cdp.get_element_bounds(selector)
        if not bounds:
            logger.warning(f"Element not found: {selector}")
            return False

        # Click in center with slight random offset
        center_x = bounds["x"] + bounds["width"] / 2
        center_y = bounds["y"] + bounds["height"] / 2

        # Add small random offset (up to 25% of element size)
        offset_x = self._rng.uniform(-0.25, 0.25) * bounds["width"]
        offset_y = self._rng.uniform(-0.25, 0.25) * bounds["height"]

        await self.click(center_x + offset_x, center_y + offset_y)
        return True
