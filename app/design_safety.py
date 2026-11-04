"""Zero-token art-direction safety checks before Elementor compilation."""
from __future__ import annotations

import re

from .models import DesignSystem

COLORS = ("primary", "accent", "background", "surface", "text", "muted")


def luminance(color: str) -> float:
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError(f"Unsupported design color {color!r}; expected #RRGGBB")
    channels = [int(color[i:i+2], 16) / 255.0 for i in (1, 3, 5)]
    linear = [x / 12.92 if x <= 0.04045 else ((x + .055)/1.055)**2.4 for x in channels]
    return sum(x*y for x,y in zip(linear, (.2126, .7152, .0722)))


def contrast(a: str, b: str) -> float:
    x, y = sorted((luminance(a), luminance(b)), reverse=True)
    return (x+.05)/(y+.05)


def _blend(hex_color: str, target: str, amount: float) -> str:
    a = [int(hex_color[i:i+2], 16) for i in (1, 3, 5)]
    b = [int(target[i:i+2], 16) for i in (1, 3, 5)]
    channels = [round(x * (1.0 - amount) + y * amount) for x, y in zip(a, b)]
    return "#" + "".join(f"{x:02X}" for x in channels)


def _ink_with_contrast(color: str, backgrounds: list[str]) -> str:
    if all(contrast(color, bg) >= 4.5 for bg in backgrounds):
        return color
    target = "#101015" if all(luminance(bg) > .28 for bg in backgrounds) else "#FFFFFF"
    for step in range(1, 11):
        trial = _blend(color, target, step / 10)
        if all(contrast(trial, bg) >= 4.5 for bg in backgrounds):
            return trial
    raise ValueError("The background/surface palette cannot support readable text")


def accessible_design_palette(ds: DesignSystem) -> DesignSystem:
    """Safe deterministic contrast repair; never invents copy or design geometry."""
    assert_design_palette(ds)
    backgrounds = [ds.background, ds.surface]
    return ds.model_copy(update={
        "text": _ink_with_contrast(ds.text, backgrounds),
        "muted": _ink_with_contrast(ds.muted, backgrounds),
        "primary": _ink_with_contrast(ds.primary, backgrounds),
        "accent": _ink_with_contrast(ds.accent, backgrounds),
    })


def assert_design_palette(ds: DesignSystem) -> None:
    for item in COLORS:
        luminance(getattr(ds, item))
    for font in (ds.heading_font, ds.body_font):
        if not re.fullmatch(r"[\w\- ]{2,48}", font, flags=re.UNICODE):
            raise ValueError("Invalid font family in design system")
    if not (720 <= ds.container_width <= 1440 and 36 <= ds.section_spacing <= 168 and 0 <= ds.radius <= 48):
        raise ValueError("Design system geometry is outside supported Elementor bounds")
