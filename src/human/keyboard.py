"""
Human-like keyboard input simulation.
Simulates natural typing patterns with delays and occasional corrections.
"""

import asyncio
import random
from typing import Optional, Dict
import logging

from .timing import HumanTiming

logger = logging.getLogger(__name__)


# Key code mappings for CDP
KEY_DEFINITIONS: Dict[str, Dict] = {
    # Special keys
    "Enter": {"key": "Enter", "code": "Enter", "keyCode": 13},
    "Tab": {"key": "Tab", "code": "Tab", "keyCode": 9},
    "Backspace": {"key": "Backspace", "code": "Backspace", "keyCode": 8},
    "Delete": {"key": "Delete", "code": "Delete", "keyCode": 46},
    "Escape": {"key": "Escape", "code": "Escape", "keyCode": 27},
    "Space": {"key": " ", "code": "Space", "keyCode": 32},

    # Arrow keys
    "ArrowUp": {"key": "ArrowUp", "code": "ArrowUp", "keyCode": 38},
    "ArrowDown": {"key": "ArrowDown", "code": "ArrowDown", "keyCode": 40},
    "ArrowLeft": {"key": "ArrowLeft", "code": "ArrowLeft", "keyCode": 37},
    "ArrowRight": {"key": "ArrowRight", "code": "ArrowRight", "keyCode": 39},

    # Modifier keys
    "Shift": {"key": "Shift", "code": "ShiftLeft", "keyCode": 16},
    "Control": {"key": "Control", "code": "ControlLeft", "keyCode": 17},
    "Alt": {"key": "Alt", "code": "AltLeft", "keyCode": 18},
    "Meta": {"key": "Meta", "code": "MetaLeft", "keyCode": 91},

    # Function keys
    "F1": {"key": "F1", "code": "F1", "keyCode": 112},
    "F2": {"key": "F2", "code": "F2", "keyCode": 113},
    "F3": {"key": "F3", "code": "F3", "keyCode": 114},
    "F4": {"key": "F4", "code": "F4", "keyCode": 115},
    "F5": {"key": "F5", "code": "F5", "keyCode": 116},
    "F6": {"key": "F6", "code": "F6", "keyCode": 117},
    "F7": {"key": "F7", "code": "F7", "keyCode": 118},
    "F8": {"key": "F8", "code": "F8", "keyCode": 119},
    "F9": {"key": "F9", "code": "F9", "keyCode": 120},
    "F10": {"key": "F10", "code": "F10", "keyCode": 121},
    "F11": {"key": "F11", "code": "F11", "keyCode": 122},
    "F12": {"key": "F12", "code": "F12", "keyCode": 123},

    # Other
    "Home": {"key": "Home", "code": "Home", "keyCode": 36},
    "End": {"key": "End", "code": "End", "keyCode": 35},
    "PageUp": {"key": "PageUp", "code": "PageUp", "keyCode": 33},
    "PageDown": {"key": "PageDown", "code": "PageDown", "keyCode": 34},
    "Insert": {"key": "Insert", "code": "Insert", "keyCode": 45},
}

# Common typo neighbors on QWERTY keyboard
KEYBOARD_NEIGHBORS: Dict[str, str] = {
    'a': 'qwsz', 'b': 'vghn', 'c': 'xdfv', 'd': 'erfcxs',
    'e': 'rdsw', 'f': 'rtgvcd', 'g': 'tyhbvf', 'h': 'yujnbg',
    'i': 'ujko', 'j': 'uikmnh', 'k': 'iolmj', 'l': 'opk',
    'm': 'njk', 'n': 'bhjm', 'o': 'iklp', 'p': 'ol',
    'q': 'wa', 'r': 'edft', 's': 'wedxza', 't': 'rfgy',
    'u': 'yhji', 'v': 'cfgb', 'w': 'qeas', 'x': 'zsdc',
    'y': 'tghu', 'z': 'asx',
    '1': '2q', '2': '13qw', '3': '24we', '4': '35er',
    '5': '46rt', '6': '57ty', '7': '68yu', '8': '79ui',
    '9': '80io', '0': '9op',
}


class KeyboardSimulator:
    """
    Human-like keyboard input simulator.
    Uses CDP Input domain for browser control.
    """

    def __init__(
        self,
        cdp_client,
        timing: HumanTiming = None,
        typo_probability: float = 0.02,
        enable_typos: bool = True,
    ):
        self.cdp = cdp_client
        self.timing = timing or HumanTiming()
        self.typo_probability = typo_probability
        self.enable_typos = enable_typos

        self._rng = random.Random()
        self._modifiers = {
            "shift": False,
            "ctrl": False,
            "alt": False,
            "meta": False,
        }

    def seed(self, value: int):
        """Set random seed for reproducibility."""
        self._rng.seed(value)

    def _get_key_definition(self, char: str) -> Dict:
        """Get CDP key definition for a character."""
        # Check special keys first
        if char in KEY_DEFINITIONS:
            return KEY_DEFINITIONS[char].copy()

        # Regular character
        code = f"Key{char.upper()}" if char.isalpha() else ""
        key_code = ord(char.upper()) if char.isalpha() else ord(char)

        return {
            "key": char,
            "code": code,
            "keyCode": key_code,
            "text": char,
        }

    def _get_modifiers(self) -> int:
        """Get current modifier flags."""
        flags = 0
        if self._modifiers["alt"]:
            flags |= 1
        if self._modifiers["ctrl"]:
            flags |= 2
        if self._modifiers["meta"]:
            flags |= 4
        if self._modifiers["shift"]:
            flags |= 8
        return flags

    async def key_down(self, key: str):
        """Press a key down."""
        key_def = self._get_key_definition(key)

        await self.cdp.send("Input.dispatchKeyEvent", {
            "type": "keyDown",
            "key": key_def.get("key", key),
            "code": key_def.get("code", ""),
            "windowsVirtualKeyCode": key_def.get("keyCode", 0),
            "modifiers": self._get_modifiers(),
        })

        # Update modifier state
        if key in ("Shift", "ShiftLeft", "ShiftRight"):
            self._modifiers["shift"] = True
        elif key in ("Control", "ControlLeft", "ControlRight"):
            self._modifiers["ctrl"] = True
        elif key in ("Alt", "AltLeft", "AltRight"):
            self._modifiers["alt"] = True
        elif key in ("Meta", "MetaLeft", "MetaRight"):
            self._modifiers["meta"] = True

    async def key_up(self, key: str):
        """Release a key."""
        key_def = self._get_key_definition(key)

        await self.cdp.send("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": key_def.get("key", key),
            "code": key_def.get("code", ""),
            "windowsVirtualKeyCode": key_def.get("keyCode", 0),
            "modifiers": self._get_modifiers(),
        })

        # Update modifier state
        if key in ("Shift", "ShiftLeft", "ShiftRight"):
            self._modifiers["shift"] = False
        elif key in ("Control", "ControlLeft", "ControlRight"):
            self._modifiers["ctrl"] = False
        elif key in ("Alt", "AltLeft", "AltRight"):
            self._modifiers["alt"] = False
        elif key in ("Meta", "MetaLeft", "MetaRight"):
            self._modifiers["meta"] = False

    async def press_key(self, key: str, hold_time: Optional[float] = None):
        """Press and release a key."""
        await self.key_down(key)
        await asyncio.sleep(hold_time or self.timing.click_delay())
        await self.key_up(key)

    async def type_char(self, char: str):
        """Type a single character."""
        key_def = self._get_key_definition(char)

        # Check if shift is needed
        needs_shift = char.isupper() or char in '!@#$%^&*()_+{}|:"<>?~'

        if needs_shift and not self._modifiers["shift"]:
            await self.key_down("Shift")

        # Key down
        await self.cdp.send("Input.dispatchKeyEvent", {
            "type": "keyDown",
            "key": key_def.get("key", char),
            "code": key_def.get("code", ""),
            "windowsVirtualKeyCode": key_def.get("keyCode", 0),
            "modifiers": self._get_modifiers(),
        })

        # Char event (for text input)
        if key_def.get("text") or (len(char) == 1 and ord(char) >= 32):
            await self.cdp.send("Input.dispatchKeyEvent", {
                "type": "char",
                "key": char,
                "text": char,
                "modifiers": self._get_modifiers(),
            })

        await asyncio.sleep(self.timing.click_delay())

        # Key up
        await self.cdp.send("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": key_def.get("key", char),
            "code": key_def.get("code", ""),
            "windowsVirtualKeyCode": key_def.get("keyCode", 0),
            "modifiers": self._get_modifiers(),
        })

        if needs_shift and not self._modifiers["shift"]:
            await self.key_up("Shift")

    async def type_text(
        self,
        text: str,
        with_typos: Optional[bool] = None,
        delay_multiplier: float = 1.0,
    ):
        """
        Type text with human-like timing and optional typos.

        Args:
            text: Text to type
            with_typos: Override typo behavior (uses instance setting if None)
            delay_multiplier: Multiplier for typing delays
        """
        enable_typos = with_typos if with_typos is not None else self.enable_typos

        i = 0
        while i < len(text):
            char = text[i]

            # Possibly make a typo
            if enable_typos and self._rng.random() < self.typo_probability:
                typo_char = self._get_typo(char)
                if typo_char and typo_char != char:
                    # Type the wrong character
                    await self.type_char(typo_char)
                    await asyncio.sleep(self.timing.typing_delay() * delay_multiplier)

                    # Pause to "notice" the mistake
                    await asyncio.sleep(self._rng.uniform(0.2, 0.5))

                    # Backspace to correct
                    await self.press_key("Backspace")
                    await asyncio.sleep(self.timing.typing_delay() * delay_multiplier)

            # Type the correct character
            await self.type_char(char)

            # Wait before next character
            delay = self.timing.typing_delay() * delay_multiplier

            # Extra pause at word boundaries
            if char == ' ':
                if self._rng.random() < 0.1:
                    delay += self._rng.uniform(0.2, 0.5)

            await asyncio.sleep(delay)
            i += 1

    def _get_typo(self, char: str) -> Optional[str]:
        """Get a realistic typo for a character."""
        lower_char = char.lower()

        if lower_char in KEYBOARD_NEIGHBORS:
            neighbors = KEYBOARD_NEIGHBORS[lower_char]
            typo = self._rng.choice(neighbors)

            # Preserve case
            if char.isupper():
                typo = typo.upper()

            return typo

        return None

    async def shortcut(self, *keys: str):
        """
        Execute a keyboard shortcut.

        Args:
            keys: Keys to press together (e.g., "Control", "c")
        """
        # Press all keys down
        for key in keys:
            await self.key_down(key)
            await asyncio.sleep(self._rng.uniform(0.02, 0.05))

        await asyncio.sleep(self._rng.uniform(0.05, 0.1))

        # Release all keys in reverse order
        for key in reversed(keys):
            await self.key_up(key)
            await asyncio.sleep(self._rng.uniform(0.02, 0.05))

    async def select_all(self):
        """Select all content (Ctrl+A or Cmd+A)."""
        await self.shortcut("Control", "a")

    async def copy(self):
        """Copy selection (Ctrl+C or Cmd+C)."""
        await self.shortcut("Control", "c")

    async def paste(self):
        """Paste clipboard (Ctrl+V or Cmd+V)."""
        await self.shortcut("Control", "v")

    async def cut(self):
        """Cut selection (Ctrl+X or Cmd+X)."""
        await self.shortcut("Control", "x")

    async def undo(self):
        """Undo (Ctrl+Z or Cmd+Z)."""
        await self.shortcut("Control", "z")

    async def redo(self):
        """Redo (Ctrl+Y or Cmd+Shift+Z)."""
        await self.shortcut("Control", "y")

    async def clear_field(self):
        """Clear current input field."""
        await self.select_all()
        await asyncio.sleep(self._rng.uniform(0.1, 0.2))
        await self.press_key("Backspace")

    async def submit(self):
        """Submit form (press Enter)."""
        await asyncio.sleep(self.timing.action_delay())
        await self.press_key("Enter")

    async def type_in_element(
        self,
        selector: str,
        text: str,
        clear_first: bool = True,
        mouse_simulator=None,
    ) -> bool:
        """
        Click on an element and type text into it.

        Args:
            selector: CSS selector of the input element
            text: Text to type
            clear_first: Whether to clear existing content first
            mouse_simulator: MouseSimulator instance for clicking

        Returns:
            True if successful
        """
        # Wait for element to be available (with retry)
        element_ready = await self._wait_for_element(selector, timeout=5.0)
        if not element_ready:
            logger.warning(f"Element not found after waiting: {selector}")
            # Try JavaScript fallback
            return await self._type_via_javascript(selector, text)

        # Click on the element if mouse simulator provided
        if mouse_simulator:
            success = await mouse_simulator.click_element(selector)
            if not success:
                # Try JavaScript fallback
                logger.warning(f"Click failed, trying JavaScript fallback")
                return await self._type_via_javascript(selector, text)
            await asyncio.sleep(self.timing.hover_delay())
        else:
            # Focus via JavaScript
            try:
                await self.cdp.evaluate(f"document.querySelector('{selector}').focus()")
            except Exception as e:
                logger.warning(f"Could not focus element: {e}")
                return await self._type_via_javascript(selector, text)

        if clear_first:
            await self.clear_field()
            await asyncio.sleep(self._rng.uniform(0.1, 0.2))

        await self.type_text(text)
        return True

    async def _wait_for_element(self, selector: str, timeout: float = 5.0) -> bool:
        """Wait for an element to be available in the DOM."""
        import time
        safe_selector = selector.replace("'", "\\'").replace("\\", "\\\\")
        start = time.time()
        while time.time() - start < timeout:
            try:
                result = await self.cdp.evaluate(
                    f"(function() {{ try {{ return document.querySelector('{safe_selector}') !== null; }} catch(e) {{ return false; }} }})()"
                )
                if result:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.2)
        return False

    async def _type_via_javascript(self, selector: str, text: str) -> bool:
        """Fallback: Type text using JavaScript (for when CDP input fails)."""
        try:
            # Escape text and selector for JavaScript
            escaped_text = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
            safe_selector = selector.replace("'", "\\'").replace("\\", "\\\\")

            js_code = f"""
            (function() {{
                try {{
                    var el = document.querySelector('{safe_selector}');
                    if (!el) {{
                        // Try alternative selectors for common search boxes
                        var alternatives = [
                            'input[type="text"]',
                            'input[type="search"]',
                            'textarea[name="q"]',
                            '[role="combobox"]',
                            'input.gLFyf',
                            '#search-input',
                            '.search-input',
                            'textarea',
                            'input'
                        ];
                        for (var i = 0; i < alternatives.length; i++) {{
                            try {{
                                var altEl = document.querySelector(alternatives[i]);
                                if (altEl) {{
                                    el = altEl;
                                    break;
                                }}
                            }} catch(e2) {{}}
                        }}
                    }}
                    if (!el) return false;
                    el.focus();
                    el.value = '{escaped_text}';
                    try {{
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }} catch(e3) {{}}
                    return true;
                }} catch(e) {{
                    return false;
                }}
            }})()
            """
            result = await self.cdp.evaluate(js_code)
            if result:
                logger.info(f"Successfully typed via JavaScript fallback")
                return True
            return False
        except Exception as e:
            logger.error(f"JavaScript typing fallback failed: {e}")
            return False
