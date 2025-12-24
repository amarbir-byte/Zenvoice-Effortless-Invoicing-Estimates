"""
Screenshot capture and processing.
Handles viewport screenshots for vision-based navigation.
"""

import asyncio
import base64
import io
import logging
from typing import Optional, Tuple, List
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL not available. Some vision features will be limited.")


@dataclass
class ScreenshotResult:
    """Result of a screenshot capture."""
    image_bytes: bytes
    width: int
    height: int
    format: str = "png"

    @property
    def base64(self) -> str:
        """Get base64-encoded image."""
        return base64.b64encode(self.image_bytes).decode("utf-8")

    @property
    def data_url(self) -> str:
        """Get data URL for embedding."""
        mime = "image/png" if self.format == "png" else "image/jpeg"
        return f"data:{mime};base64,{self.base64}"

    def save(self, path: str):
        """Save screenshot to file."""
        Path(path).write_bytes(self.image_bytes)

    def to_pil(self) -> Optional['Image.Image']:
        """Convert to PIL Image."""
        if not PIL_AVAILABLE:
            return None
        return Image.open(io.BytesIO(self.image_bytes))


class ScreenshotCapture:
    """
    Capture and process browser screenshots.
    """

    def __init__(self, cdp_client, format: str = "png", quality: int = 90):
        self.cdp = cdp_client
        self.format = format
        self.quality = quality

    async def capture(
        self,
        full_page: bool = False,
        clip: Optional[dict] = None,
    ) -> ScreenshotResult:
        """
        Capture a screenshot of the current viewport or full page.

        Args:
            full_page: Capture entire page (not just viewport)
            clip: Optional region to capture {x, y, width, height, scale}

        Returns:
            ScreenshotResult with image data
        """
        params = {"format": self.format}

        if self.format == "jpeg":
            params["quality"] = self.quality

        if full_page:
            params["captureBeyondViewport"] = True

        if clip:
            params["clip"] = {
                "x": clip.get("x", 0),
                "y": clip.get("y", 0),
                "width": clip.get("width", 800),
                "height": clip.get("height", 600),
                "scale": clip.get("scale", 1),
            }

        result = await self.cdp.send("Page.captureScreenshot", params)
        image_bytes = base64.b64decode(result["data"])

        # Get dimensions
        width, height = await self._get_image_dimensions(image_bytes)

        return ScreenshotResult(
            image_bytes=image_bytes,
            width=width,
            height=height,
            format=self.format,
        )

    async def capture_element(self, selector: str) -> Optional[ScreenshotResult]:
        """
        Capture a screenshot of a specific element.

        Args:
            selector: CSS selector of element to capture

        Returns:
            ScreenshotResult or None if element not found
        """
        bounds = await self.cdp.get_element_bounds(selector)
        if not bounds:
            logger.warning(f"Element not found for screenshot: {selector}")
            return None

        return await self.capture(clip={
            "x": bounds["x"],
            "y": bounds["y"],
            "width": bounds["width"],
            "height": bounds["height"],
            "scale": 1,
        })

    async def _get_image_dimensions(self, image_bytes: bytes) -> Tuple[int, int]:
        """Get image dimensions."""
        if PIL_AVAILABLE:
            img = Image.open(io.BytesIO(image_bytes))
            return img.size
        else:
            # Fallback: parse PNG header
            if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
                width = int.from_bytes(image_bytes[16:20], 'big')
                height = int.from_bytes(image_bytes[20:24], 'big')
                return width, height
            return 0, 0

    async def annotate_elements(
        self,
        screenshot: ScreenshotResult,
        elements: List[dict],
        output_path: Optional[str] = None,
    ) -> Optional[ScreenshotResult]:
        """
        Annotate screenshot with element bounding boxes.
        Useful for debugging and visualization.

        Args:
            screenshot: Original screenshot
            elements: List of elements with bounds
            output_path: Optional path to save annotated image

        Returns:
            Annotated ScreenshotResult or None if PIL not available
        """
        if not PIL_AVAILABLE:
            logger.warning("PIL required for annotation")
            return None

        img = screenshot.to_pil()
        draw = ImageDraw.Draw(img)

        # Try to use a font, fallback to default
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        except Exception:
            font = ImageFont.load_default()

        colors = [
            "#FF6B6B",  # Red
            "#4ECDC4",  # Teal
            "#45B7D1",  # Blue
            "#96CEB4",  # Green
            "#FFEAA7",  # Yellow
            "#DDA0DD",  # Plum
            "#98D8C8",  # Mint
            "#F7DC6F",  # Gold
        ]

        for i, elem in enumerate(elements):
            bounds = elem.get("bounds") or elem.get("bounding_box")
            if not bounds:
                continue

            x = bounds.get("x", 0)
            y = bounds.get("y", 0)
            w = bounds.get("width", 0)
            h = bounds.get("height", 0)

            color = colors[i % len(colors)]

            # Draw rectangle
            draw.rectangle(
                [x, y, x + w, y + h],
                outline=color,
                width=2,
            )

            # Draw label
            label = elem.get("label", "") or elem.get("text", "")[:20]
            if label:
                # Background for text
                text_bbox = draw.textbbox((x, y - 15), label, font=font)
                draw.rectangle(text_bbox, fill=color)
                draw.text((x, y - 15), label, fill="white", font=font)

        # Convert back to bytes
        output = io.BytesIO()
        img.save(output, format=self.format.upper())
        annotated_bytes = output.getvalue()

        if output_path:
            Path(output_path).write_bytes(annotated_bytes)

        return ScreenshotResult(
            image_bytes=annotated_bytes,
            width=screenshot.width,
            height=screenshot.height,
            format=self.format,
        )

    async def compare_screenshots(
        self,
        before: ScreenshotResult,
        after: ScreenshotResult,
        threshold: float = 0.05,
    ) -> Tuple[bool, float]:
        """
        Compare two screenshots to detect changes.

        Args:
            before: First screenshot
            after: Second screenshot
            threshold: Difference threshold (0-1)

        Returns:
            Tuple of (changed, difference_ratio)
        """
        if not PIL_AVAILABLE:
            logger.warning("PIL required for comparison")
            return True, 1.0

        img1 = before.to_pil().convert("L")  # Grayscale
        img2 = after.to_pil().convert("L")

        # Resize to same dimensions if needed
        if img1.size != img2.size:
            img2 = img2.resize(img1.size)

        # Calculate difference
        import numpy as np
        arr1 = np.array(img1)
        arr2 = np.array(img2)

        diff = np.abs(arr1.astype(float) - arr2.astype(float))
        diff_ratio = np.mean(diff) / 255.0

        changed = diff_ratio > threshold
        return changed, diff_ratio

    async def get_viewport_with_annotations(
        self,
        elements: List[dict],
    ) -> ScreenshotResult:
        """
        Capture viewport and annotate with interactive elements.

        Args:
            elements: List of elements to annotate

        Returns:
            Annotated ScreenshotResult
        """
        screenshot = await self.capture()

        if PIL_AVAILABLE and elements:
            annotated = await self.annotate_elements(screenshot, elements)
            if annotated:
                return annotated

        return screenshot
