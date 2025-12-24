"""Browser control module."""

from .controller import BrowserController
from .cdp_client import CDPClient

__all__ = ["BrowserController", "CDPClient"]
