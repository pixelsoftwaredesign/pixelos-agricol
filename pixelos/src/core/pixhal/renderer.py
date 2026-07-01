"""
PixHAL Unified Renderer.

Single API for all Pixel OS graphics:
  - Vulkan (native, via C++ pybind11)
  - Software fallback (numpy + PIL)

Modules should import this, never the vulkan/ subpackage directly.
"""

import time
from typing import Optional, Callable
from dataclasses import dataclass, field

from core.pixhal.vulkan import (
    SoftwareInstance,
    SoftwareRenderer,
    Color,
    Rect,
    Backend,
    DeviceCaps,
    has_vulkan,
    preferred_backend,
    NativeRenderer,
)


# ── Unified Renderer ───────────────────────────────────────

class Renderer:
    """
    High-level Pixel OS renderer.

    Auto-selects Vulkan when the compiled module is available,
    falls back to software (numpy+PIL). Provides the same API
    regardless of backend.
    """

    def __init__(self, width: int = 800, height: int = 600,
                 title: str = "PixHAL", target_fps: int = 60):
        self._width = width
        self._height = height
        self._title = title
        self._target_fps = target_fps
        self._backend_name = "Vulkan" if has_vulkan() else "Software"

        # Create backend
        if has_vulkan() and NativeRenderer is not None:
            self._impl = NativeRenderer(width, height, title, target_fps)
            self._backend = Backend.Vulkan
            self._backend_name = "Vulkan (native)"
        else:
            self._impl = SoftwareRenderer(width, height, title, target_fps)
            self._backend = Backend.Fallback

        self._running = True

        # Callbacks
        self.on_frame: Optional[Callable[[float], None]] = None
        self.on_click: Optional[Callable[[float, float], None]] = None
        self.on_resize: Optional[Callable[[int, int], None]] = None

        # Wire callbacks
        if self._impl:
            if hasattr(self._impl, 'on_frame') and self._backend == Backend.Fallback:
                self._impl.on_frame = self._frame_proxy
            elif self._backend == Backend.Vulkan:
                self._impl.on_frame = self._frame_proxy
            if hasattr(self._impl, 'on_click') and self._backend == Backend.Fallback:
                self._impl.on_click = self._click_proxy
            elif self._backend == Backend.Vulkan:
                self._impl.on_click = self._click_proxy

    def _frame_proxy(self, dt: float):
        if self.on_frame:
            self.on_frame(dt)

    def _click_proxy(self, x: float, y: float):
        if self.on_click:
            self.on_click(x, y)

    # ── Properties ─────────────────────────────────────────

    @property
    def width(self) -> int:
        return self._impl.width if self._impl else self._width

    @property
    def height(self) -> int:
        return self._impl.height if self._impl else self._height

    @property
    def aspect(self) -> float:
        return self._impl.aspect if self._impl else self._width / self._height

    @property
    def fps(self) -> float:
        return self._impl.fps if self._impl else 0.0

    @property
    def running(self) -> bool:
        return self._running and (self._impl.running if self._impl else True)

    @property
    def backend(self) -> Backend:
        return self._backend

    @property
    def backend_name(self) -> str:
        return self._backend_name

    @property
    def caps(self) -> DeviceCaps:
        return self._impl.caps if self._impl else DeviceCaps()

    # ── Drawing ────────────────────────────────────────────

    def clear(self, color: Optional[Color] = None):
        if self._impl:
            self._impl.clear(color)

    def draw_rect(self, rect: Rect, color: Color):
        if self._impl:
            self._impl.draw_rect(rect, color)

    def draw_circle(self, cx: float, cy: float, radius: float, color: Color):
        if self._impl:
            self._impl.draw_circle(cx, cy, radius, color)

    def draw_balloon(self, cx: float, cy: float, radius: float,
                     inner: Color, alpha: float):
        if self._impl:
            self._impl.draw_balloon(cx, cy, radius, inner, alpha)

    def draw_text(self, x: float, y: float, text: str,
                  color: Optional[Color] = None, size: float = 14.0):
        if self._impl:
            self._impl.draw_text(x, y, text, color, size)

    # ── Lifecycle ──────────────────────────────────────────

    def tick(self) -> bool:
        if not self._running:
            return False
        if self._impl:
            return self._impl.tick()
        return True

    def run(self):
        """Blocking render loop."""
        while self.tick():
            frame_time = 0  # computed by backend
            sleep_needed = (1.0 / self._target_fps) - frame_time
            if sleep_needed > 0:
                time.sleep(sleep_needed)

    def handle_click(self, x: float, y: float):
        if self._impl:
            self._impl.handle_click(x, y)

    def close(self):
        self._running = False
        if self._impl:
            self._impl.close()

    def screenshot(self, path: str) -> str:
        if self._impl and hasattr(self._impl, 'screenshot'):
            return self._impl.screenshot(path)
        return ""

    def read_pixels(self) -> bytes:
        if self._impl:
            return self._impl.read_pixels()
        return b""


# ── Convenience ────────────────────────────────────────────

def create_renderer(width: int = 800, height: int = 600,
                    title: str = "PixHAL") -> Renderer:
    return Renderer(width, height, title)


__all__ = [
    "Renderer", "create_renderer",
    "Color", "Rect", "Backend",
]
