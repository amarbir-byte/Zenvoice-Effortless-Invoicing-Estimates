"""
Vision processing for screenshot analysis.
Handles OCR and element detection from images.
"""

import io
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Try to import OCR library
OCR_AVAILABLE = False
try:
    import easyocr
    OCR_AVAILABLE = True
    OCR_ENGINE = "easyocr"
except ImportError:
    try:
        import pytesseract
        OCR_AVAILABLE = True
        OCR_ENGINE = "tesseract"
    except ImportError:
        logger.warning("No OCR engine available. Install easyocr or pytesseract.")
        OCR_ENGINE = None


@dataclass
class TextRegion:
    """Detected text region from OCR."""
    text: str
    x: float
    y: float
    width: float
    height: float
    confidence: float

    @property
    def center(self) -> Tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "confidence": self.confidence,
        }


class VisionProcessor:
    """
    Process screenshots for text and element detection.
    Provides fallback when DOM extraction is insufficient.
    """

    def __init__(self, language: str = "en"):
        self.language = language
        self._ocr_reader = None

        if OCR_AVAILABLE and OCR_ENGINE == "easyocr":
            self._init_easyocr()

    def _init_easyocr(self):
        """Initialize EasyOCR reader."""
        try:
            import easyocr
            self._ocr_reader = easyocr.Reader(
                [self.language],
                gpu=False,  # Use CPU for compatibility
                verbose=False,
            )
            logger.info("EasyOCR initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize EasyOCR: {e}")

    async def extract_text(
        self,
        image_bytes: bytes,
        min_confidence: float = 0.5,
    ) -> List[TextRegion]:
        """
        Extract text regions from an image using OCR.

        Args:
            image_bytes: PNG or JPEG image bytes
            min_confidence: Minimum confidence threshold

        Returns:
            List of TextRegion objects
        """
        if not OCR_AVAILABLE:
            logger.warning("OCR not available")
            return []

        if not PIL_AVAILABLE:
            logger.warning("PIL required for OCR")
            return []

        img = Image.open(io.BytesIO(image_bytes))

        if OCR_ENGINE == "easyocr":
            return await self._extract_with_easyocr(img, min_confidence)
        elif OCR_ENGINE == "tesseract":
            return await self._extract_with_tesseract(img, min_confidence)

        return []

    async def _extract_with_easyocr(
        self,
        img: 'Image.Image',
        min_confidence: float,
    ) -> List[TextRegion]:
        """Extract text using EasyOCR."""
        import numpy as np

        if not self._ocr_reader:
            self._init_easyocr()
            if not self._ocr_reader:
                return []

        # Convert PIL to numpy array
        img_array = np.array(img)

        # Run OCR
        results = self._ocr_reader.readtext(img_array)

        regions = []
        for bbox, text, confidence in results:
            if confidence < min_confidence:
                continue

            # bbox is [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
            x1, y1 = bbox[0]
            x2, y2 = bbox[2]

            regions.append(TextRegion(
                text=text,
                x=x1,
                y=y1,
                width=x2 - x1,
                height=y2 - y1,
                confidence=confidence,
            ))

        return regions

    async def _extract_with_tesseract(
        self,
        img: 'Image.Image',
        min_confidence: float,
    ) -> List[TextRegion]:
        """Extract text using Tesseract."""
        import pytesseract

        # Get detailed output
        data = pytesseract.image_to_data(
            img,
            output_type=pytesseract.Output.DICT,
            lang=self.language,
        )

        regions = []
        n_boxes = len(data['text'])

        for i in range(n_boxes):
            text = data['text'][i].strip()
            conf = float(data['conf'][i]) / 100.0

            if not text or conf < min_confidence:
                continue

            regions.append(TextRegion(
                text=text,
                x=data['left'][i],
                y=data['top'][i],
                width=data['width'][i],
                height=data['height'][i],
                confidence=conf,
            ))

        return regions

    async def find_text_location(
        self,
        image_bytes: bytes,
        search_text: str,
        exact: bool = False,
    ) -> Optional[TextRegion]:
        """
        Find the location of specific text in an image.

        Args:
            image_bytes: Image to search
            search_text: Text to find
            exact: Require exact match

        Returns:
            TextRegion if found, None otherwise
        """
        regions = await self.extract_text(image_bytes)

        search_lower = search_text.lower()

        for region in regions:
            region_text = region.text.lower()

            if exact:
                if region_text == search_lower:
                    return region
            else:
                if search_lower in region_text:
                    return region

        return None

    async def get_text_near_point(
        self,
        image_bytes: bytes,
        x: float,
        y: float,
        radius: float = 100,
    ) -> List[TextRegion]:
        """
        Get text regions near a specific point.

        Args:
            image_bytes: Image to search
            x: X coordinate
            y: Y coordinate
            radius: Search radius in pixels

        Returns:
            List of nearby TextRegion objects
        """
        regions = await self.extract_text(image_bytes)

        nearby = []
        for region in regions:
            center_x, center_y = region.center
            distance = ((center_x - x) ** 2 + (center_y - y) ** 2) ** 0.5

            if distance <= radius:
                nearby.append(region)

        # Sort by distance
        nearby.sort(key=lambda r: (
            ((r.center[0] - x) ** 2 + (r.center[1] - y) ** 2) ** 0.5
        ))

        return nearby

    async def detect_buttons(
        self,
        image_bytes: bytes,
    ) -> List[Dict[str, Any]]:
        """
        Detect button-like elements in an image.
        Uses simple heuristics based on text regions.

        Args:
            image_bytes: Image to analyze

        Returns:
            List of potential button regions
        """
        regions = await self.extract_text(image_bytes)

        buttons = []
        button_keywords = [
            'submit', 'send', 'ok', 'cancel', 'save', 'next', 'back',
            'continue', 'login', 'sign', 'register', 'buy', 'add',
            'delete', 'remove', 'edit', 'update', 'confirm', 'yes', 'no',
            'accept', 'decline', 'close', 'open', 'start', 'stop',
        ]

        for region in regions:
            text_lower = region.text.lower().strip()

            # Check if text looks like a button
            is_button = False

            # Short text (1-3 words)
            word_count = len(text_lower.split())
            if 1 <= word_count <= 3:
                # Check for button keywords
                for keyword in button_keywords:
                    if keyword in text_lower:
                        is_button = True
                        break

            if is_button:
                buttons.append({
                    "text": region.text,
                    "x": region.x,
                    "y": region.y,
                    "width": region.width,
                    "height": region.height,
                    "center": region.center,
                })

        return buttons

    async def analyze_page_structure(
        self,
        image_bytes: bytes,
    ) -> Dict[str, Any]:
        """
        Analyze overall page structure from screenshot.

        Args:
            image_bytes: Screenshot to analyze

        Returns:
            Dict with page structure info
        """
        if not PIL_AVAILABLE:
            return {}

        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size

        # Get text regions
        regions = await self.extract_text(image_bytes, min_confidence=0.3)

        # Analyze layout
        top_regions = [r for r in regions if r.y < height * 0.15]
        middle_regions = [r for r in regions if height * 0.15 <= r.y <= height * 0.85]
        bottom_regions = [r for r in regions if r.y > height * 0.85]

        # Detect potential form fields (regions with low confidence might be input hints)
        potential_inputs = [r for r in regions if r.confidence < 0.7 and r.width > 100]

        return {
            "dimensions": {"width": width, "height": height},
            "text_regions_count": len(regions),
            "header_text": " ".join(r.text for r in top_regions[:5]),
            "footer_text": " ".join(r.text for r in bottom_regions[:5]),
            "has_form": len(potential_inputs) > 0,
            "potential_input_count": len(potential_inputs),
            "main_content_regions": len(middle_regions),
        }

    def combine_with_dom(
        self,
        dom_elements: List[Dict[str, Any]],
        vision_regions: List[TextRegion],
    ) -> List[Dict[str, Any]]:
        """
        Combine DOM extraction with vision results for better accuracy.

        Args:
            dom_elements: Elements from DOM extraction
            vision_regions: Text regions from OCR

        Returns:
            Combined and enriched element list
        """
        combined = []

        for elem in dom_elements:
            # Find matching vision regions
            bounds = elem.get("bounds", {})
            if not bounds:
                combined.append(elem)
                continue

            elem_center = (
                bounds.get("x", 0) + bounds.get("width", 0) / 2,
                bounds.get("y", 0) + bounds.get("height", 0) / 2,
            )

            # Find OCR text near this element
            nearby_text = []
            for region in vision_regions:
                distance = (
                    (region.center[0] - elem_center[0]) ** 2 +
                    (region.center[1] - elem_center[1]) ** 2
                ) ** 0.5

                if distance < 50:  # Within 50 pixels
                    nearby_text.append(region.text)

            if nearby_text:
                elem["ocr_text"] = " ".join(nearby_text)
                elem["ocr_verified"] = True

            combined.append(elem)

        # Add vision-only elements (not in DOM)
        for region in vision_regions:
            # Check if this region overlaps with any DOM element
            is_new = True
            for elem in dom_elements:
                bounds = elem.get("bounds", {})
                if not bounds:
                    continue

                # Simple overlap check
                if (
                    abs(region.center[0] - (bounds["x"] + bounds["width"] / 2)) < 30 and
                    abs(region.center[1] - (bounds["y"] + bounds["height"] / 2)) < 30
                ):
                    is_new = False
                    break

            if is_new:
                combined.append({
                    "source": "vision",
                    "text": region.text,
                    "bounds": {
                        "x": region.x,
                        "y": region.y,
                        "width": region.width,
                        "height": region.height,
                    },
                    "confidence": region.confidence,
                })

        return combined
