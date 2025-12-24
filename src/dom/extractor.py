"""
DOM extraction via Chrome DevTools Protocol.
Extracts interactive elements and their properties from the page.
"""

import asyncio
import json
import logging
from typing import List, Dict, Any, Optional, Set

from .elements import (
    Element,
    InteractiveElement,
    ElementType,
    BoundingBox,
    ViewportState,
)

logger = logging.getLogger(__name__)


# Tag to ElementType mapping
TAG_TYPE_MAP: Dict[str, ElementType] = {
    "button": ElementType.BUTTON,
    "a": ElementType.LINK,
    "textarea": ElementType.TEXTAREA,
    "select": ElementType.SELECT,
    "option": ElementType.OPTION,
    "form": ElementType.FORM,
    "img": ElementType.IMAGE,
    "video": ElementType.VIDEO,
    "iframe": ElementType.IFRAME,
    "h1": ElementType.HEADING,
    "h2": ElementType.HEADING,
    "h3": ElementType.HEADING,
    "h4": ElementType.HEADING,
    "h5": ElementType.HEADING,
    "h6": ElementType.HEADING,
    "p": ElementType.PARAGRAPH,
    "li": ElementType.LIST_ITEM,
    "table": ElementType.TABLE,
    "tr": ElementType.TABLE_ROW,
    "td": ElementType.TABLE_CELL,
    "th": ElementType.TABLE_CELL,
    "nav": ElementType.NAV,
    "menu": ElementType.MENU,
    "dialog": ElementType.DIALOG,
}

INPUT_TYPE_MAP: Dict[str, ElementType] = {
    "text": ElementType.INPUT_TEXT,
    "password": ElementType.INPUT_PASSWORD,
    "email": ElementType.INPUT_EMAIL,
    "number": ElementType.INPUT_NUMBER,
    "search": ElementType.INPUT_SEARCH,
    "tel": ElementType.INPUT_TEL,
    "url": ElementType.INPUT_URL,
    "date": ElementType.INPUT_DATE,
    "datetime-local": ElementType.INPUT_DATE,
    "checkbox": ElementType.INPUT_CHECKBOX,
    "radio": ElementType.INPUT_RADIO,
    "file": ElementType.INPUT_FILE,
    "hidden": ElementType.INPUT_HIDDEN,
    "submit": ElementType.INPUT_SUBMIT,
    "reset": ElementType.INPUT_RESET,
    "button": ElementType.BUTTON,
}


class DOMExtractor:
    """
    Extract DOM elements and their properties via CDP.
    Focuses on interactive and visible elements.
    """

    def __init__(self, cdp_client):
        self.cdp = cdp_client
        self._cache: Dict[int, Element] = {}

    async def extract_viewport_state(
        self,
        include_screenshot: bool = False,
    ) -> ViewportState:
        """
        Extract complete viewport state for agent consumption.

        Args:
            include_screenshot: Whether to include base64 screenshot

        Returns:
            ViewportState with all relevant information
        """
        # Get page info
        url = await self.cdp.evaluate("window.location.href")
        title = await self.cdp.evaluate("document.title")

        # Get viewport and scroll info
        viewport = await self.cdp.get_viewport_size()
        scroll = await self.cdp.get_scroll_position()
        page_size = await self.cdp.get_page_size()

        # Get visible text
        visible_text = await self._get_visible_text()

        # Get interactive elements
        elements = await self.extract_interactive_elements(
            viewport_only=True,
            viewport_width=viewport["width"],
            viewport_height=viewport["height"],
        )

        # Optional screenshot
        screenshot_b64 = None
        if include_screenshot:
            import base64
            screenshot_bytes = await self.cdp.screenshot()
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        return ViewportState(
            url=url,
            title=title,
            viewport_width=viewport["width"],
            viewport_height=viewport["height"],
            scroll_x=scroll["x"],
            scroll_y=scroll["y"],
            page_width=page_size["width"],
            page_height=page_size["height"],
            visible_text=visible_text,
            interactive_elements=elements,
            screenshot_base64=screenshot_b64,
        )

    async def extract_interactive_elements(
        self,
        viewport_only: bool = True,
        viewport_width: int = 1920,
        viewport_height: int = 1080,
    ) -> List[InteractiveElement]:
        """
        Extract all interactive elements from the page.

        Args:
            viewport_only: Only include elements visible in viewport
            viewport_width: Viewport width for visibility check
            viewport_height: Viewport height for visibility check

        Returns:
            List of interactive elements
        """
        # JavaScript to extract interactive elements
        extract_js = """
        (function() {
            const results = [];
            const seen = new Set();

            // Selectors for interactive elements
            const selectors = [
                'a[href]',
                'button',
                'input:not([type="hidden"])',
                'select',
                'textarea',
                '[role="button"]',
                '[role="link"]',
                '[role="menuitem"]',
                '[role="tab"]',
                '[role="checkbox"]',
                '[role="radio"]',
                '[role="textbox"]',
                '[role="combobox"]',
                '[role="listbox"]',
                '[role="option"]',
                '[onclick]',
                '[tabindex]:not([tabindex="-1"])',
                'label[for]',
                'summary',
                '[contenteditable="true"]',
            ];

            // Query all interactive elements
            const elements = document.querySelectorAll(selectors.join(','));

            for (const el of elements) {
                // Skip if already processed
                if (seen.has(el)) continue;
                seen.add(el);

                // Skip hidden elements
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') continue;
                if (el.offsetWidth === 0 && el.offsetHeight === 0) continue;

                // Get bounding rect
                const rect = el.getBoundingClientRect();

                // Get element info
                const info = {
                    tag: el.tagName.toLowerCase(),
                    id: el.id || '',
                    className: el.className || '',
                    text: (el.textContent || '').trim().substring(0, 200),
                    innerText: (el.innerText || '').trim().substring(0, 200),
                    type: el.type || '',
                    name: el.name || '',
                    value: el.value || '',
                    href: el.href || '',
                    placeholder: el.placeholder || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    role: el.getAttribute('role') || '',
                    disabled: el.disabled || false,
                    checked: el.checked || false,
                    required: el.required || false,
                    bounds: {
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height,
                    },
                };

                // Get options for select elements
                if (el.tagName.toLowerCase() === 'select') {
                    info.options = Array.from(el.options).map(o => ({
                        value: o.value,
                        text: o.text,
                        selected: o.selected,
                    }));
                }

                results.push(info);
            }

            return JSON.stringify(results);
        })()
        """

        try:
            result = await self.cdp.evaluate(extract_js)
            raw_elements = json.loads(result) if result else []
        except Exception as e:
            logger.error(f"Failed to extract elements: {e}")
            return []

        # Convert to InteractiveElement objects
        elements = []
        for raw in raw_elements:
            try:
                element = self._parse_element(raw)
                if element:
                    # Filter by viewport if requested
                    if viewport_only and element.bounding_box:
                        if not element.bounding_box.is_visible_in_viewport(
                            viewport_width, viewport_height
                        ):
                            continue

                    elements.append(element)
            except Exception as e:
                logger.debug(f"Failed to parse element: {e}")

        # Sort by position (top to bottom, left to right)
        elements.sort(key=lambda e: (
            e.bounding_box.y if e.bounding_box else 0,
            e.bounding_box.x if e.bounding_box else 0,
        ))

        return elements

    def _parse_element(self, raw: Dict[str, Any]) -> Optional[InteractiveElement]:
        """Parse raw element data into InteractiveElement."""
        tag = raw.get("tag", "").lower()

        # Determine element type
        if tag == "input":
            input_type = raw.get("type", "text").lower()
            element_type = INPUT_TYPE_MAP.get(input_type, ElementType.INPUT_TEXT)
        else:
            element_type = TAG_TYPE_MAP.get(tag, ElementType.OTHER)

        # Handle role-based type detection
        role = raw.get("role", "")
        if role == "button":
            element_type = ElementType.BUTTON
        elif role == "link":
            element_type = ElementType.LINK
        elif role == "textbox":
            element_type = ElementType.INPUT_TEXT
        elif role in ("checkbox", "radio"):
            element_type = ElementType.INPUT_CHECKBOX if role == "checkbox" else ElementType.INPUT_RADIO

        # Build bounding box
        bounds_data = raw.get("bounds", {})
        bounding_box = None
        if bounds_data and bounds_data.get("width", 0) > 0:
            bounding_box = BoundingBox(
                x=bounds_data.get("x", 0),
                y=bounds_data.get("y", 0),
                width=bounds_data.get("width", 0),
                height=bounds_data.get("height", 0),
            )

        # Build attributes dict
        attributes = {
            "id": raw.get("id", ""),
            "class": raw.get("className", ""),
            "type": raw.get("type", ""),
            "name": raw.get("name", ""),
            "value": raw.get("value", ""),
            "href": raw.get("href", ""),
            "placeholder": raw.get("placeholder", ""),
            "aria-label": raw.get("ariaLabel", ""),
            "role": raw.get("role", ""),
        }
        attributes = {k: v for k, v in attributes.items() if v}

        # Get best text content
        text = raw.get("innerText", "") or raw.get("text", "")

        return InteractiveElement(
            tag_name=tag,
            node_id=0,  # Not using node_id for JS-extracted elements
            text=text,
            attributes=attributes,
            bounding_box=bounding_box,
            element_type=element_type,
            is_enabled=not raw.get("disabled", False),
            is_visible=True,  # Already filtered for visibility
            value=raw.get("value", ""),
            placeholder=raw.get("placeholder", ""),
            aria_label=raw.get("ariaLabel", ""),
            role=raw.get("role", ""),
            href=raw.get("href", ""),
            name=raw.get("name", ""),
            required=raw.get("required", False),
            checked=raw.get("checked", False),
            options=[o.get("text", "") for o in raw.get("options", [])],
        )

    async def _get_visible_text(self) -> str:
        """Extract visible text from the viewport."""
        extract_text_js = """
        (function() {
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                {
                    acceptNode: function(node) {
                        const parent = node.parentElement;
                        if (!parent) return NodeFilter.FILTER_REJECT;

                        const tag = parent.tagName.toLowerCase();
                        if (['script', 'style', 'noscript', 'template'].includes(tag)) {
                            return NodeFilter.FILTER_REJECT;
                        }

                        const style = window.getComputedStyle(parent);
                        if (style.display === 'none' || style.visibility === 'hidden') {
                            return NodeFilter.FILTER_REJECT;
                        }

                        const rect = parent.getBoundingClientRect();
                        if (rect.bottom < 0 || rect.top > window.innerHeight) {
                            return NodeFilter.FILTER_REJECT;
                        }

                        const text = node.textContent.trim();
                        if (!text) return NodeFilter.FILTER_REJECT;

                        return NodeFilter.FILTER_ACCEPT;
                    }
                }
            );

            const texts = [];
            let node;
            while (node = walker.nextNode()) {
                const text = node.textContent.trim();
                if (text) texts.push(text);
            }

            return texts.join(' ').substring(0, 10000);
        })()
        """

        try:
            return await self.cdp.evaluate(extract_text_js) or ""
        except Exception as e:
            logger.error(f"Failed to extract visible text: {e}")
            return ""

    async def find_element_by_text(
        self,
        text: str,
        element_type: Optional[ElementType] = None,
        exact: bool = False,
    ) -> Optional[InteractiveElement]:
        """
        Find an interactive element by its text content.

        Args:
            text: Text to search for
            element_type: Optional filter by element type
            exact: Require exact match (default: contains)

        Returns:
            First matching element or None
        """
        elements = await self.extract_interactive_elements(viewport_only=False)

        for elem in elements:
            if element_type and elem.element_type != element_type:
                continue

            label = elem.label.lower()
            search_text = text.lower()

            if exact:
                if label == search_text:
                    return elem
            else:
                if search_text in label:
                    return elem

        return None

    async def find_elements_by_type(
        self,
        element_type: ElementType,
        viewport_only: bool = True,
    ) -> List[InteractiveElement]:
        """
        Find all elements of a specific type.

        Args:
            element_type: Type to filter by
            viewport_only: Only include visible elements

        Returns:
            List of matching elements
        """
        elements = await self.extract_interactive_elements(viewport_only=viewport_only)
        return [e for e in elements if e.element_type == element_type]

    async def get_form_fields(self) -> List[InteractiveElement]:
        """Get all form input fields."""
        elements = await self.extract_interactive_elements(viewport_only=False)
        return [e for e in elements if e.is_input]

    async def get_clickable_elements(self) -> List[InteractiveElement]:
        """Get all clickable elements."""
        elements = await self.extract_interactive_elements(viewport_only=True)
        return [e for e in elements if e.is_clickable]
