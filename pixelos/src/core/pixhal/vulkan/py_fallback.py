"""
PixHAL Vulkan — Pure-Python software fallback.

Mirrors the C++ pixhal::vk::Instance and Renderer API using numpy + PIL.
Used when Vulkan SDK is not available (development, CI, deployment on
robots without GPU).
"""

import math
import time
import struct
import numpy as np
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Optional, Callable
from pathlib import Path


# ── Types (mirrors pixhal/vk/types.h) ──────────────────────

class Backend(IntEnum):
    Vulkan = 0
    Fallback = 1


@dataclass
class Color:
    r: float = 1.0
    g: float = 1.0
    b: float = 1.0
    a: float = 1.0

    @staticmethod
    def from_rgba8(r, g, b, a=255):
        return Color(r / 255.0, g / 255.0, b / 255.0, a / 255.0)

    def to_rgba8(self):
        return (
            int(max(0, min(255, self.r * 255))),
            int(max(0, min(255, self.g * 255))),
            int(max(0, min(255, self.b * 255))),
            int(max(0, min(255, self.a * 255))),
        )


@dataclass
class Rect:
    x: float = 0
    y: float = 0
    w: float = 0
    h: float = 0


@dataclass
class DeviceCaps:
    device_name: str = "PixHAL Software (numpy+PIL)"
    max_texture_size: int = 4096
    max_draw_calls: int = 65536
    has_compute: bool = False
    max_anisotropy: float = 0.0


# ── PixelBuffer (software framebuffer) ─────────────────────

class PixelBuffer:
    """RGBA8 framebuffer with software drawing primitives."""

    def __init__(self, width: int, height: int):
        self.w = width
        self.h = height
        self.data = np.zeros((height, width, 4), dtype=np.uint8)
        self.data[:] = [10, 14, 23, 255]  # PixOS dark

    def clear(self, r: int = 10, g: int = 14, b: int = 23, a: int = 255):
        self.data[:] = [r, g, b, a]

    def set_pixel(self, x: int, y: int, r: int, g: int, b: int, a: int = 255):
        if 0 <= x < self.w and 0 <= y < self.h:
            if a >= 254:
                self.data[y, x] = [r, g, b, 255]
            else:
                fa = a / 255.0
                inv = 1.0 - fa
                px = self.data[y, x]
                self.data[y, x] = [
                    int(r * fa + px[0] * inv),
                    int(g * fa + px[1] * inv),
                    int(b * fa + px[2] * inv),
                    min(255, int(a + px[3] * (1 - fa))),
                ]

    def draw_circle_filled(self, cx: int, cy: int, radius: int,
                           r: int, g: int, b: int, a: int = 255):
        min_x = max(0, cx - radius)
        max_x = min(self.w - 1, cx + radius)
        min_y = max(0, cy - radius)
        max_y = min(self.h - 1, cy + radius)
        rr = radius * radius
        for y in range(min_y, max_y + 1):
            dy = y - cy
            for x in range(min_x, max_x + 1):
                dx = x - cx
                if dx * dx + dy * dy <= rr:
                    self.set_pixel(x, y, r, g, b, a)

    def draw_circle_gradient(self, cx: int, cy: int, radius: int,
                             ir: int, ig: int, ib: int,
                             or_: int, og: int, ob: int,
                             alpha: int):
        min_x = max(0, cx - radius)
        max_x = min(self.w - 1, cx + radius)
        min_y = max(0, cy - radius)
        max_y = min(self.h - 1, cy + radius)
        for y in range(min_y, max_y + 1):
            dy = y - cy
            for x in range(min_x, max_x + 1):
                dx = x - cx
                dist = math.sqrt(dx * dx + dy * dy) / radius
                if dist <= 1.0:
                    t = dist
                    self.set_pixel(x, y,
                        int(ir * (1 - t) + or_ * t),
                        int(ig * (1 - t) + og * t),
                        int(ib * (1 - t) + ob * t),
                        int(alpha * (1.0 - t * 0.3)))

    def to_pil(self):
        from PIL import Image
        return Image.fromarray(self.data, 'RGBA')


# ── Instance (software, mirrors C++ Instance) ──────────────

class SoftwareInstance:
    """Pure-Python implementation of pixhal::vk::Instance."""

    def __init__(self, width: int = 800, height: int = 600, title: str = "PixHAL"):
        self._w = width
        self._h = height
        self._title = title
        self._caps = DeviceCaps()
        self._fb = PixelBuffer(width, height)
        self._running = True
        self._frame_count = 0

    @property
    def backend(self) -> Backend:
        return Backend.Fallback

    @property
    def caps(self) -> DeviceCaps:
        return self._caps

    @property
    def width(self) -> int:
        return self._w

    @property
    def height(self) -> int:
        return self._h

    @property
    def aspect(self) -> float:
        return self._w / self._h if self._h else 1.0

    def begin_frame(self) -> bool:
        return self._running

    def end_frame(self):
        pass

    def present(self):
        self._frame_count += 1

    def clear(self, color: Optional[Color] = None):
        if color is None:
            color = Color(0.04, 0.055, 0.09)
        self._fb.clear(
            int(color.r * 255), int(color.g * 255),
            int(color.b * 255), int(color.a * 255),
        )

    def draw_rect(self, rect: Rect, color: Color):
        x0 = int(rect.x * self._w)
        y0 = int(rect.y * self._h)
        x1 = int((rect.x + rect.w) * self._w)
        y1 = int((rect.y + rect.h) * self._h)
        cr, cg, cb, ca = color.to_rgba8()
        for y in range(y0, y1):
            for x in range(x0, x1):
                self._fb.set_pixel(x, y, cr, cg, cb, ca)

    def draw_circle(self, cx: float, cy: float, radius: float, color: Color):
        ix = int(cx * self._w)
        iy = int(cy * self._h)
        ir = int(radius * min(self._w, self._h))
        cr, cg, cb, ca = color.to_rgba8()
        self._fb.draw_circle_filled(ix, iy, ir, cr, cg, cb, ca)

    def draw_balloon(self, cx: float, cy: float, radius: float,
                     inner: Color, alpha: float):
        ix = int(cx * self._w)
        iy = int(cy * self._h)
        ir = int(radius * min(self._w, self._h))
        a = int(alpha * inner.a * 255)
        inner_r = min(255, int(inner.r * 255 + 80))
        inner_g = min(255, int(inner.g * 255 + 80))
        inner_b = min(255, int(inner.b * 255 + 80))
        outer_r = max(0, int(inner.r * 255 - 40))
        outer_g = max(0, int(inner.g * 255 - 40))
        outer_b = max(0, int(inner.b * 255 - 40))
        self._fb.draw_circle_gradient(ix, iy, ir,
            inner_r, inner_g, inner_b,
            outer_r, outer_g, outer_b, a)
        # string
        sx, sy = ix, iy + ir
        ex, ey = ix + ir // 2, iy + ir * 2
        for t in range(21):
            tt = t / 20.0
            px = int(sx * (1 - tt) + ex * tt)
            py = int(sy * (1 - tt) + ey * tt)
            self._fb.set_pixel(px, py, 100, 116, 139, a)
        # highlight
        hl_r = int(ir * 0.25)
        hl_adj = int(ir * 0.3)
        for dy in range(-hl_r, hl_r + 1):
            for dx in range(-hl_r, hl_r + 1):
                if dx * dx + dy * dy <= hl_r * hl_r:
                    self._fb.set_pixel(
                        ix - hl_adj + dx, iy - hl_adj + dy,
                        255, 255, 255, int(a * 0.3))

    def draw_text(self, x: float, y: float, text: str,
                  color: Optional[Color] = None, size: float = 14.0):
        if color is None:
            color = Color(1, 1, 1)
        ix = int(x * self._w)
        iy = int(y * self._h)
        ch_w = int(size * 0.6)
        ch_h = int(size)
        cr, cg, cb, ca = color.to_rgba8()
        for i, ch in enumerate(text):
            for py in range(ch_h):
                for px in range(ch_w):
                    self._fb.set_pixel(ix + i * ch_w + px, iy + py,
                                       cr, cg, cb, ca)

    def flush(self):
        pass

    def read_pixels(self):
        return self._fb.data.tobytes()

    def read_pil(self):
        return self._fb.to_pil()

    def close(self):
        self._running = False


# ── High-level Renderer ────────────────────────────────────

class SoftwareRenderer:
    """Pure-Python renderer with game loop, frame callback, and input."""

    def __init__(self, width: int = 800, height: int = 600,
                 title: str = "PixHAL", target_fps: int = 60):
        self.instance = SoftwareInstance(width, height, title)
        self._title = title
        self._target_fps = target_fps
        self._frame_dt = 1.0 / target_fps
        self._running = True
        self._frame_count = 0
        self._last_time = time.monotonic()
        self._fps_counter = 0
        self._fps_time = 0
        self._current_fps = 0.0

        # Callbacks
        self.on_frame: Optional[Callable] = None
        self.on_click: Optional[Callable] = None
        self.on_resize: Optional[Callable] = None

    @property
    def width(self) -> int:
        return self.instance._w

    @property
    def height(self) -> int:
        return self.instance._h

    @property
    def aspect(self) -> float:
        return self.instance.aspect

    @property
    def fps(self) -> float:
        return self._current_fps

    @property
    def running(self) -> bool:
        return self._running

    @property
    def backend(self) -> Backend:
        return Backend.Fallback

    @property
    def caps(self) -> DeviceCaps:
        return self.instance._caps

    def clear(self, color: Optional[Color] = None):
        self.instance.clear(color)

    def draw_rect(self, rect: Rect, color: Color):
        self.instance.draw_rect(rect, color)

    def draw_circle(self, cx: float, cy: float, radius: float, color: Color):
        self.instance.draw_circle(cx, cy, radius, color)

    def draw_balloon(self, cx: float, cy: float, radius: float,
                     inner: Color, alpha: float):
        self.instance.draw_balloon(cx, cy, radius, inner, alpha)

    def draw_text(self, x: float, y: float, text: str,
                  color: Optional[Color] = None, size: float = 14.0):
        self.instance.draw_text(x, y, text, color, size)

    def read_pixels(self):
        return self.instance.read_pixels()

    def tick(self) -> bool:
        """Advance one frame. Returns False when done."""
        if not self._running:
            return False

        now = time.monotonic()
        dt = now - self._last_time
        self._last_time = now

        # FPS counter
        self._fps_counter += 1
        if now - self._fps_time >= 1.0:
            self._current_fps = self._fps_counter / (now - self._fps_time)
            self._fps_counter = 0
            self._fps_time = now

        self.instance.begin_frame()
        if self.on_frame:
            self.on_frame(dt)
        self.instance.end_frame()
        self.instance.present()
        self._frame_count += 1

        return True

    def run(self):
        """Blocking render loop."""
        while self.tick():
            frame_time = time.monotonic() - self._last_time
            sleep_needed = self._frame_dt - frame_time
            if sleep_needed > 0:
                time.sleep(sleep_needed)

    def handle_click(self, x: float, y: float):
        if self.on_click:
            self.on_click(x, y)

    def close(self):
        self._running = False
        self.instance.close()

    def screenshot(self, path: str):
        img = self.instance.read_pil()
        img.save(path)
        return path
