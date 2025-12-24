"""
Human-like timing and delay generation.
Uses various distributions to create natural, unpredictable delays.
"""

import random
import math
import asyncio
from typing import Tuple
from dataclasses import dataclass


@dataclass
class TimingConfig:
    """Configuration for human-like timing."""
    # Action delays
    action_delay_min: float = 0.5
    action_delay_max: float = 1.5

    # Typing
    typing_delay_min: float = 0.05
    typing_delay_max: float = 0.15
    typing_pause_probability: float = 0.1
    typing_pause_min: float = 0.3
    typing_pause_max: float = 0.8

    # Mouse
    mouse_move_speed_min: float = 0.1
    mouse_move_speed_max: float = 0.4
    hover_delay_min: float = 0.2
    hover_delay_max: float = 0.5
    click_delay_min: float = 0.05
    click_delay_max: float = 0.15

    # Scrolling
    scroll_delay_min: float = 0.3
    scroll_delay_max: float = 0.8

    # Reading
    reading_speed_wpm: int = 250


class HumanTiming:
    """
    Generate human-like timing delays using various probability distributions.
    """

    def __init__(self, config: TimingConfig = None):
        self.config = config or TimingConfig()
        self._rng = random.Random()

    def seed(self, value: int):
        """Set random seed for reproducibility."""
        self._rng.seed(value)

    def uniform(self, min_val: float, max_val: float) -> float:
        """Uniform distribution delay."""
        return self._rng.uniform(min_val, max_val)

    def gaussian(self, mean: float, std: float, min_val: float = 0) -> float:
        """Gaussian/normal distribution delay with minimum clamp."""
        value = self._rng.gauss(mean, std)
        return max(min_val, value)

    def exponential(self, lambd: float, min_val: float = 0, max_val: float = float('inf')) -> float:
        """Exponential distribution delay (good for reaction times)."""
        value = self._rng.expovariate(1 / lambd)
        return max(min_val, min(max_val, value))

    def log_normal(self, mean: float, sigma: float, min_val: float = 0) -> float:
        """Log-normal distribution (good for human response times)."""
        value = self._rng.lognormvariate(math.log(mean), sigma)
        return max(min_val, value)

    def pareto(self, alpha: float, min_val: float = 0.1) -> float:
        """Pareto distribution (occasional long pauses)."""
        return min_val * (self._rng.paretovariate(alpha))

    # Specific timing methods

    def action_delay(self) -> float:
        """Delay between major actions (clicking, typing, etc.)."""
        # Use log-normal for natural variation
        mean = (self.config.action_delay_min + self.config.action_delay_max) / 2
        return self.log_normal(mean, 0.3, self.config.action_delay_min)

    def typing_delay(self) -> float:
        """Delay between keystrokes."""
        # Gaussian with occasional longer pauses
        base_delay = self.gaussian(
            (self.config.typing_delay_min + self.config.typing_delay_max) / 2,
            0.03,
            self.config.typing_delay_min,
        )

        # Occasional pause between words
        if self._rng.random() < self.config.typing_pause_probability:
            base_delay += self.uniform(
                self.config.typing_pause_min,
                self.config.typing_pause_max,
            )

        return base_delay

    def hover_delay(self) -> float:
        """Delay for hovering before clicking."""
        return self.uniform(
            self.config.hover_delay_min,
            self.config.hover_delay_max,
        )

    def click_delay(self) -> float:
        """Delay between mouse down and mouse up."""
        return self.uniform(
            self.config.click_delay_min,
            self.config.click_delay_max,
        )

    def scroll_delay(self) -> float:
        """Delay between scroll steps."""
        return self.uniform(
            self.config.scroll_delay_min,
            self.config.scroll_delay_max,
        )

    def mouse_move_duration(self, distance: float) -> float:
        """
        Calculate mouse movement duration based on Fitts's Law.

        Args:
            distance: Distance to travel in pixels.

        Returns:
            Duration in seconds.
        """
        # Fitts's Law: MT = a + b * log2(2D/W)
        # Simplified version with some randomness
        base_time = self.config.mouse_move_speed_min
        distance_factor = math.log2(max(1, distance / 50) + 1) * 0.1
        random_factor = self.uniform(0.9, 1.1)

        duration = (base_time + distance_factor) * random_factor
        return min(duration, self.config.mouse_move_speed_max)

    def reading_time(self, text: str) -> float:
        """
        Calculate time to "read" text based on WPM.

        Args:
            text: Text to read.

        Returns:
            Time in seconds.
        """
        word_count = len(text.split())
        minutes = word_count / self.config.reading_speed_wpm
        # Add some variation
        return minutes * 60 * self.uniform(0.8, 1.2)

    def reaction_time(self) -> float:
        """Human reaction time (200-400ms typically)."""
        return self.log_normal(0.25, 0.2, 0.15)

    def double_click_interval(self) -> float:
        """Interval between clicks in a double-click."""
        return self.uniform(0.08, 0.12)

    def micro_pause(self) -> float:
        """Very short pause (50-150ms)."""
        return self.uniform(0.05, 0.15)

    # Async convenience methods

    async def wait_action(self):
        """Async wait for action delay."""
        await asyncio.sleep(self.action_delay())

    async def wait_typing(self):
        """Async wait for typing delay."""
        await asyncio.sleep(self.typing_delay())

    async def wait_hover(self):
        """Async wait for hover delay."""
        await asyncio.sleep(self.hover_delay())

    async def wait_click(self):
        """Async wait for click delay."""
        await asyncio.sleep(self.click_delay())

    async def wait_scroll(self):
        """Async wait for scroll delay."""
        await asyncio.sleep(self.scroll_delay())

    async def wait_reading(self, text: str):
        """Async wait for reading time."""
        await asyncio.sleep(self.reading_time(text))

    async def wait_reaction(self):
        """Async wait for reaction time."""
        await asyncio.sleep(self.reaction_time())


# Perlin noise implementation for smooth random movement
class PerlinNoise:
    """Simple 1D Perlin noise for smooth random variations."""

    def __init__(self, seed: int = None):
        self._rng = random.Random(seed)
        self._permutation = list(range(256))
        self._rng.shuffle(self._permutation)
        self._permutation = self._permutation * 2

    def _fade(self, t: float) -> float:
        return t * t * t * (t * (t * 6 - 15) + 10)

    def _lerp(self, a: float, b: float, t: float) -> float:
        return a + t * (b - a)

    def _grad(self, hash_val: int, x: float) -> float:
        h = hash_val & 15
        grad = 1 + (h & 7)
        if h & 8:
            grad = -grad
        return grad * x

    def noise(self, x: float) -> float:
        """Get 1D Perlin noise value at position x."""
        xi = int(x) & 255
        xf = x - int(x)

        u = self._fade(xf)

        a = self._permutation[xi]
        b = self._permutation[xi + 1]

        return self._lerp(
            self._grad(a, xf),
            self._grad(b, xf - 1),
            u
        )

    def octave_noise(self, x: float, octaves: int = 4, persistence: float = 0.5) -> float:
        """Multi-octave Perlin noise for more natural variation."""
        total = 0
        frequency = 1
        amplitude = 1
        max_value = 0

        for _ in range(octaves):
            total += self.noise(x * frequency) * amplitude
            max_value += amplitude
            amplitude *= persistence
            frequency *= 2

        return total / max_value


# Global timing instance
human_timing = HumanTiming()
