#ifndef PIXHAL_VK_TYPES_H
#define PIXHAL_VK_TYPES_H

#include <cstdint>
#include <vector>
#include <string>
#include <array>

namespace pixhal {
namespace vk {

// ── Backend selection ──────────────────────────────────────
enum class Backend : uint8_t {
    Vulkan  = 0,
    Fallback = 1,
};

// ── Color ──────────────────────────────────────────────────
struct Color {
    float r = 1.0f, g = 1.0f, b = 1.0f, a = 1.0f;

    Color() = default;
    Color(float r, float g, float b, float a = 1.0f)
        : r(r), g(g), b(b), a(a) {}

    static Color from_rgba8(uint8_t r, uint8_t g, uint8_t b, uint8_t a = 255) {
        return { r / 255.0f, g / 255.0f, b / 255.0f, a / 255.0f };
    }
};

// ── Rect ───────────────────────────────────────────────────
struct Rect {
    float x = 0, y = 0, w = 0, h = 0;
};

// ── Vertex ─────────────────────────────────────────────────
struct Vertex2D {
    float x, y;       // position
    float u, v;       // texcoord
    uint8_t r, g, b, a; // color (premultiplied)
};

// ── Draw call ──────────────────────────────────────────────
struct DrawCmd {
    enum Type : uint8_t {
        Triangle    = 0,
        Rect        = 1,
        Circle      = 2,
        Text        = 3,
        Balloon     = 4,
    };
    Type type = Triangle;
    float x = 0, y = 0, w = 0, h = 0;
    float radius = 0;
    Color color;
    float alpha = 1.0f;
    uint32_t texture_id = 0;
};

// ── Window props ───────────────────────────────────────────
struct WindowProps {
    std::string title = "PixHAL";
    uint32_t width = 800;
    uint32_t height = 600;
    bool vsync = true;
    bool resizable = false;
};

// ── Caps ───────────────────────────────────────────────────
struct DeviceCaps {
    std::string device_name;
    uint32_t max_texture_size = 4096;
    uint32_t max_draw_calls = 65536;
    bool has_compute = false;
    float max_anisotropy = 16.0f;
};

} // namespace vk
} // namespace pixhal

#endif
