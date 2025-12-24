"""
Configuration settings for the local browser automation agent.
"""

from dataclasses import dataclass, field
from typing import Optional
import os


@dataclass
class LMStudioConfig:
    """LM Studio API configuration."""
    base_url: str = "http://localhost:1234/v1"
    model: str = "gemma-3-12b"  # Adjust based on your loaded model
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout: int = 60


@dataclass
class BrowserConfig:
    """Chrome browser configuration."""
    chrome_path: str = ""  # Auto-detect if empty
    remote_debugging_port: int = 9222
    user_data_dir: Optional[str] = None  # Use default profile if None
    headless: bool = False  # Must be False for stealth
    window_width: int = 1920
    window_height: int = 1080

    def __post_init__(self):
        if not self.chrome_path:
            self.chrome_path = self._detect_chrome_path()

    def _detect_chrome_path(self) -> str:
        """Auto-detect Chrome installation path."""
        possible_paths = [
            # Windows
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            # Linux
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            # macOS
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        return "chrome"  # Fallback to PATH


@dataclass
class HumanBehaviorConfig:
    """Human-like behavior simulation settings."""
    # Mouse movement
    mouse_speed_min: float = 0.1  # seconds
    mouse_speed_max: float = 0.4
    mouse_curve_deviation: float = 50  # pixels
    mouse_micro_movements: bool = True

    # Clicking
    click_delay_min: float = 0.05
    click_delay_max: float = 0.15
    double_click_interval: float = 0.1
    hover_before_click_min: float = 0.2
    hover_before_click_max: float = 0.5

    # Typing
    typing_delay_min: float = 0.05  # seconds per character
    typing_delay_max: float = 0.15
    typing_mistake_probability: float = 0.02  # 2% chance of typo
    typing_pause_probability: float = 0.1  # 10% chance of pause between words
    typing_pause_duration_min: float = 0.3
    typing_pause_duration_max: float = 0.8

    # Scrolling
    scroll_amount_min: int = 200  # pixels
    scroll_amount_max: int = 400
    scroll_delay_min: float = 0.3
    scroll_delay_max: float = 0.8
    scroll_smooth: bool = True

    # General timing
    action_delay_min: float = 0.5  # delay between actions
    action_delay_max: float = 1.5
    reading_speed_wpm: int = 250  # words per minute for "reading" pauses


@dataclass
class VisionConfig:
    """Vision/screenshot configuration."""
    screenshot_format: str = "png"
    screenshot_quality: int = 90
    ocr_enabled: bool = True
    ocr_language: str = "en"
    element_highlight: bool = False  # Debug: highlight detected elements


@dataclass
class AgentConfig:
    """Main agent configuration."""
    lm_studio: LMStudioConfig = field(default_factory=LMStudioConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    human_behavior: HumanBehaviorConfig = field(default_factory=HumanBehaviorConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)

    # Agent behavior
    max_actions_per_task: int = 100
    screenshot_before_action: bool = True
    dom_extraction_enabled: bool = True
    verbose_logging: bool = True
    save_session_recording: bool = False
    session_recording_path: str = "./recordings"


# Global config instance
config = AgentConfig()


def load_config_from_env():
    """Load configuration overrides from environment variables."""
    global config

    if os.getenv("LM_STUDIO_URL"):
        config.lm_studio.base_url = os.getenv("LM_STUDIO_URL")

    if os.getenv("LM_STUDIO_MODEL"):
        config.lm_studio.model = os.getenv("LM_STUDIO_MODEL")

    if os.getenv("CHROME_PATH"):
        config.browser.chrome_path = os.getenv("CHROME_PATH")

    if os.getenv("CHROME_DEBUG_PORT"):
        config.browser.remote_debugging_port = int(os.getenv("CHROME_DEBUG_PORT"))

    return config
