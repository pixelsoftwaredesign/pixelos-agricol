"""
PixHAL Vulkan abstraction layer.

Auto-detects available backend:
1. Native C++ Vulkan extension (if compiled with PIXHAL_VK_AVAILABLE)
2. Pure-Python software fallback (numpy + PIL)

Usage:
    from core.pixhal.vulkan import SoftwareInstance, SoftwareRenderer, Color, Rect
"""

# ── Auto-detect native extension ───────────────────────────
_HAS_NATIVE_VK = False
_NATIVE_MODULE = None
try:
    from . import _pixhal_vulkan_bind as _NATIVE_MODULE
    _HAS_NATIVE_VK = True
except ImportError:
    pass

# ── Fallback: always available ─────────────────────────────
from .py_fallback import (
    SoftwareInstance,
    SoftwareRenderer,
    PixelBuffer,
    Color,
    Rect,
    Backend,
    DeviceCaps,
)

# ── When native is available, also expose native classes ───
if _HAS_NATIVE_VK:
    NativeRenderer = _NATIVE_MODULE.Renderer
    NativeInstance = _NATIVE_MODULE.Instance
    NativeColor = _NATIVE_MODULE.Color
    NativeRect = _NATIVE_MODULE.Rect
    NativeBackend = _NATIVE_MODULE.Backend
    NativeDeviceCaps = _NATIVE_MODULE.DeviceCaps
else:
    NativeRenderer = None
    NativeInstance = None
    NativeColor = None
    NativeRect = None
    NativeBackend = None
    NativeDeviceCaps = None

# ── Detection helper ───────────────────────────────────────
def has_vulkan() -> bool:
    """Returns True if native Vulkan backend is available."""
    return _HAS_NATIVE_VK

def preferred_backend() -> Backend:
    return Backend.Vulkan if _HAS_NATIVE_VK else Backend.Fallback

def caps() -> DeviceCaps:
    if _HAS_NATIVE_VK:
        pass
    return DeviceCaps()

__all__ = [
    "SoftwareInstance", "SoftwareRenderer", "PixelBuffer",
    "Color", "Rect", "Backend", "DeviceCaps",
    "has_vulkan", "preferred_backend", "caps",
    "NativeRenderer", "NativeInstance",
]
