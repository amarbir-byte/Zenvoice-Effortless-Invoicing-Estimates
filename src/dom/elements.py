"""
DOM element data structures.
Defines typed elements for agent consumption.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum, auto


class ElementType(Enum):
    """Types of interactive elements."""
    BUTTON = auto()
    LINK = auto()
    INPUT_TEXT = auto()
    INPUT_PASSWORD = auto()
    INPUT_EMAIL = auto()
    INPUT_NUMBER = auto()
    INPUT_SEARCH = auto()
    INPUT_TEL = auto()
    INPUT_URL = auto()
    INPUT_DATE = auto()
    INPUT_CHECKBOX = auto()
    INPUT_RADIO = auto()
    INPUT_FILE = auto()
    INPUT_HIDDEN = auto()
    INPUT_SUBMIT = auto()
    INPUT_RESET = auto()
    TEXTAREA = auto()
    SELECT = auto()
    OPTION = auto()
    FORM = auto()
    IMAGE = auto()
    VIDEO = auto()
    IFRAME = auto()
    DIV = auto()
    SPAN = auto()
    HEADING = auto()
    PARAGRAPH = auto()
    LIST_ITEM = auto()
    TABLE = auto()
    TABLE_ROW = auto()
    TABLE_CELL = auto()
    NAV = auto()
    MENU = auto()
    DIALOG = auto()
    OTHER = auto()


@dataclass
class BoundingBox:
    """Element bounding box."""
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple:
        """Get center point."""
        return (self.x + self.width / 2, self.y + self.height / 2)

    @property
    def top_left(self) -> tuple:
        return (self.x, self.y)

    @property
    def bottom_right(self) -> tuple:
        return (self.x + self.width, self.y + self.height)

    def contains_point(self, x: float, y: float) -> bool:
        """Check if point is inside bounding box."""
        return (
            self.x <= x <= self.x + self.width and
            self.y <= y <= self.y + self.height
        )

    def is_visible_in_viewport(self, viewport_width: int, viewport_height: int) -> bool:
        """Check if element is at least partially visible in viewport."""
        return (
            self.x + self.width > 0 and
            self.x < viewport_width and
            self.y + self.height > 0 and
            self.y < viewport_height
        )

    def to_dict(self) -> Dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class Element:
    """Base DOM element."""
    tag_name: str
    node_id: int
    text: str = ""
    attributes: Dict[str, str] = field(default_factory=dict)
    bounding_box: Optional[BoundingBox] = None
    children: List['Element'] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.attributes.get("id", "")

    @property
    def class_name(self) -> str:
        return self.attributes.get("class", "")

    @property
    def classes(self) -> List[str]:
        return self.class_name.split() if self.class_name else []

    @property
    def selector(self) -> str:
        """Generate a CSS selector for this element."""
        if self.id:
            return f"#{self.id}"

        parts = [self.tag_name.lower()]

        # Add classes (first 2 for specificity)
        for cls in self.classes[:2]:
            if cls and not cls.startswith("_"):  # Skip generated class names
                parts.append(f".{cls}")

        return "".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tag": self.tag_name,
            "node_id": self.node_id,
            "text": self.text[:100] if self.text else "",
            "id": self.id,
            "class": self.class_name,
            "bounds": self.bounding_box.to_dict() if self.bounding_box else None,
        }


@dataclass
class InteractiveElement(Element):
    """Interactive DOM element (button, input, link, etc.)."""
    element_type: ElementType = ElementType.OTHER
    is_enabled: bool = True
    is_visible: bool = True
    is_focusable: bool = True
    value: str = ""
    placeholder: str = ""
    aria_label: str = ""
    role: str = ""
    href: str = ""
    name: str = ""
    required: bool = False
    checked: bool = False
    selected: bool = False
    options: List[str] = field(default_factory=list)

    @classmethod
    def from_element(cls, element: Element, element_type: ElementType) -> 'InteractiveElement':
        """Create InteractiveElement from base Element."""
        return cls(
            tag_name=element.tag_name,
            node_id=element.node_id,
            text=element.text,
            attributes=element.attributes,
            bounding_box=element.bounding_box,
            children=element.children,
            element_type=element_type,
            value=element.attributes.get("value", ""),
            placeholder=element.attributes.get("placeholder", ""),
            aria_label=element.attributes.get("aria-label", ""),
            role=element.attributes.get("role", ""),
            href=element.attributes.get("href", ""),
            name=element.attributes.get("name", ""),
            required="required" in element.attributes,
            checked="checked" in element.attributes,
            selected="selected" in element.attributes,
        )

    @property
    def label(self) -> str:
        """Get the best available label for this element."""
        # Priority: aria-label > text > placeholder > name > value
        if self.aria_label:
            return self.aria_label
        if self.text and self.text.strip():
            return self.text.strip()
        if self.placeholder:
            return self.placeholder
        if self.name:
            return self.name
        if self.value:
            return self.value
        return ""

    @property
    def is_input(self) -> bool:
        """Check if this is an input element."""
        return self.element_type in (
            ElementType.INPUT_TEXT,
            ElementType.INPUT_PASSWORD,
            ElementType.INPUT_EMAIL,
            ElementType.INPUT_NUMBER,
            ElementType.INPUT_SEARCH,
            ElementType.INPUT_TEL,
            ElementType.INPUT_URL,
            ElementType.INPUT_DATE,
            ElementType.TEXTAREA,
        )

    @property
    def is_clickable(self) -> bool:
        """Check if this element is clickable."""
        return self.element_type in (
            ElementType.BUTTON,
            ElementType.LINK,
            ElementType.INPUT_CHECKBOX,
            ElementType.INPUT_RADIO,
            ElementType.INPUT_SUBMIT,
            ElementType.INPUT_RESET,
            ElementType.SELECT,
            ElementType.OPTION,
        ) or self.role in ("button", "link", "menuitem", "tab", "option")

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "type": self.element_type.name,
            "enabled": self.is_enabled,
            "visible": self.is_visible,
            "label": self.label,
            "value": self.value,
            "placeholder": self.placeholder,
            "href": self.href if self.href else None,
            "required": self.required,
            "checked": self.checked if self.element_type in (ElementType.INPUT_CHECKBOX, ElementType.INPUT_RADIO) else None,
        })
        return {k: v for k, v in base.items() if v is not None}

    def __str__(self) -> str:
        """Human-readable string representation."""
        parts = [f"[{self.element_type.name}]"]

        if self.label:
            parts.append(f'"{self.label[:30]}"')

        if self.href:
            parts.append(f"-> {self.href[:50]}")

        if self.bounding_box:
            x, y = self.bounding_box.center
            parts.append(f"@({int(x)},{int(y)})")

        return " ".join(parts)


@dataclass
class ViewportState:
    """Complete viewport state for agent consumption."""
    url: str
    title: str
    viewport_width: int
    viewport_height: int
    scroll_x: int
    scroll_y: int
    page_width: int
    page_height: int
    visible_text: str
    interactive_elements: List[InteractiveElement]
    screenshot_base64: Optional[str] = None

    @property
    def scroll_percentage(self) -> float:
        """Get vertical scroll percentage."""
        if self.page_height <= self.viewport_height:
            return 100.0
        return (self.scroll_y / (self.page_height - self.viewport_height)) * 100

    @property
    def can_scroll_down(self) -> bool:
        """Check if page can scroll down more."""
        return self.scroll_y + self.viewport_height < self.page_height

    @property
    def can_scroll_up(self) -> bool:
        """Check if page can scroll up."""
        return self.scroll_y > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "viewport": {
                "width": self.viewport_width,
                "height": self.viewport_height,
            },
            "scroll": {
                "x": self.scroll_x,
                "y": self.scroll_y,
                "percentage": round(self.scroll_percentage, 1),
                "can_scroll_down": self.can_scroll_down,
                "can_scroll_up": self.can_scroll_up,
            },
            "page_size": {
                "width": self.page_width,
                "height": self.page_height,
            },
            "visible_text": self.visible_text[:5000] if self.visible_text else "",
            "elements": [e.to_dict() for e in self.interactive_elements],
            "element_count": len(self.interactive_elements),
        }

    def to_prompt(self) -> str:
        """Convert to a string suitable for LLM prompt."""
        lines = [
            f"URL: {self.url}",
            f"Title: {self.title}",
            f"Viewport: {self.viewport_width}x{self.viewport_height}",
            f"Scroll: {self.scroll_y}px ({self.scroll_percentage:.0f}%)",
            "",
            "=== VISIBLE TEXT ===",
            self.visible_text[:3000] if self.visible_text else "(no text)",
            "",
            "=== INTERACTIVE ELEMENTS ===",
        ]

        for i, elem in enumerate(self.interactive_elements[:50]):  # Limit elements
            lines.append(f"{i+1}. {elem}")

        if len(self.interactive_elements) > 50:
            lines.append(f"... and {len(self.interactive_elements) - 50} more elements")

        return "\n".join(lines)
