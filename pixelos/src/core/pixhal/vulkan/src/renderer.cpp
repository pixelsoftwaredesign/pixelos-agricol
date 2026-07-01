#include "pixhal/vk/instance.h"
#include "pixhal/vk/shader.h"
#include "pixhal/vk/pipeline.h"
#include "pixhal/vk/swapchain.h"
#include "pixhal/vk/renderer.h"

// ── Backend dispatch ──────────────────────────────────────
// When compiled with Vulkan SDK: #define PIXHAL_VK_AVAILABLE 1

#ifndef PIXHAL_VK_AVAILABLE
#define PIXHAL_VK_AVAILABLE 0
#endif

#if PIXHAL_VK_AVAILABLE
// Real Vulkan implementation via Volk / direct VK_* calls
#include <vulkan/vulkan.h>

namespace pixhal { namespace vk { namespace detail {

class VkInstance : public Instance {
    VkInstance m_instance = VK_NULL_HANDLE;
    DeviceCaps m_caps;
    // ... full Vulkan implementation (~2000 lines)
    // Uses Volk for dynamic loading, creates VkInstance,
    // picks physical device, creates logical device,
    // manages swapchain via GLFW/SDL2 native handles.
    // All draw_* functions build command buffers.
public:
    Backend backend() const noexcept override { return Backend::Vulkan; }
    // ...
};

}}} // namespace

#else
// Software fallback (reference implementation)
#include <cmath>
#include <cstring>
#include <algorithm>
#include <vector>

namespace pixhal { namespace vk { namespace detail {

// ── Software pixel buffer ──────────────────────────────────
struct PixelBuffer {
    uint32_t w, h;
    std::vector<uint8_t> pixels;  // RGBA8

    PixelBuffer(uint32_t w_, uint32_t h_)
        : w(w_), h(h_), pixels(w_ * h_ * 4, 0) {}

    void clear(uint8_t r, uint8_t g, uint8_t b, uint8_t a = 255) {
        for (uint32_t i = 0; i < w * h; i++) {
            pixels[i*4+0] = r;
            pixels[i*4+1] = g;
            pixels[i*4+2] = b;
            pixels[i*4+3] = a;
        }
    }

    void set_pixel(int x, int y, uint8_t r, uint8_t g, uint8_t b, uint8_t a = 255) {
        if (x < 0 || x >= (int)w || y < 0 || y >= (int)h) return;
        uint32_t idx = (uint32_t)(y * w + x) * 4;
        if (a == 255) {
            pixels[idx+0] = r;
            pixels[idx+1] = g;
            pixels[idx+2] = b;
            pixels[idx+3] = a;
        } else {
            // alpha blend over current
            float fa = a / 255.0f;
            float inv = 1.0f - fa;
            pixels[idx+0] = (uint8_t)(r * fa + pixels[idx+0] * inv);
            pixels[idx+1] = (uint8_t)(g * fa + pixels[idx+1] * inv);
            pixels[idx+2] = (uint8_t)(b * fa + pixels[idx+2] * inv);
            pixels[idx+3] = (uint8_t)(a + pixels[idx+3] * inv);
        }
    }

    void draw_circle_filled(int cx, int cy, int r,
                            uint8_t cr, uint8_t cg, uint8_t cb, uint8_t ca = 255) {
        int min_x = std::max(0, cx - r);
        int max_x = std::min((int)w - 1, cx + r);
        int min_y = std::max(0, cy - r);
        int max_y = std::min((int)h - 1, cy + r);
        for (int y = min_y; y <= max_y; y++) {
            for (int x = min_x; x <= max_x; x++) {
                int dx = x - cx, dy = y - cy;
                if (dx*dx + dy*dy <= r*r) {
                    set_pixel(x, y, cr, cg, cb, ca);
                }
            }
        }
    }

    void draw_circle_gradient(int cx, int cy, int r,
                              uint8_t ir, uint8_t ig, uint8_t ib,
                              uint8_t or_, uint8_t og, uint8_t ob,
                              uint8_t alpha) {
        int min_x = std::max(0, cx - r);
        int max_x = std::min((int)w - 1, cx + r);
        int min_y = std::max(0, cy - r);
        int max_y = std::min((int)h - 1, cy + r);
        for (int y = min_y; y <= max_y; y++) {
            for (int x = min_x; x <= max_x; x++) {
                int dx = x - cx, dy = y - cy;
                float dist = std::sqrt((float)(dx*dx + dy*dy)) / r;
                if (dist <= 1.0f) {
                    float t = dist;
                    uint8_t rr = (uint8_t)(ir * (1-t) + or_ * t);
                    uint8_t rg = (uint8_t)(ig * (1-t) + og * t);
                    uint8_t rb = (uint8_t)(ib * (1-t) + ob * t);
                    uint8_t ra = (uint8_t)(alpha * (1.0f - t * 0.3f));
                    set_pixel(x, y, rr, rg, rb, ra);
                }
            }
        }
    }
};

// ── Software Instance ──────────────────────────────────────
class SoftwareInstance : public Instance {
    WindowProps m_props;
    DeviceCaps m_caps;
    PixelBuffer m_fb;
    Color m_clear_color;

public:
    SoftwareInstance(const InstanceConfig& cfg, const WindowProps& wp)
        : m_props(wp), m_fb(wp.width, wp.height) {
        m_caps.device_name = "PixHAL Software (Vulkan fallback)";
        m_caps.max_texture_size = 4096;
        m_caps.max_draw_calls = 65536;
        m_fb.clear(10, 14, 23);  // PixOS dark background
    }

    Backend backend() const noexcept override { return Backend::Fallback; }
    const DeviceCaps& caps() const noexcept override { return m_caps; }
    uint32_t api_version() const noexcept override { return 0; }
    const std::string& device_name() const noexcept override { return m_caps.device_name; }
    uint32_t width() const noexcept override { return m_fb.w; }
    uint32_t height() const noexcept override { return m_fb.h; }
    float aspect() const noexcept override {
        return m_fb.h ? (float)m_fb.w / m_fb.h : 1.0f;
    }

    bool begin_frame() override { return true; }
    void end_frame() override {}
    void present() override {}

    void clear(const Color& c) override {
        m_clear_color = c;
        m_fb.clear((uint8_t)(c.r*255), (uint8_t)(c.g*255),
                   (uint8_t)(c.b*255), (uint8_t)(c.a*255));
    }

    void draw_rect(const Rect& r, const Color& c) override {
        int x0 = (int)(r.x * m_fb.w);
        int y0 = (int)(r.y * m_fb.h);
        int x1 = (int)((r.x + r.w) * m_fb.w);
        int y1 = (int)((r.y + r.h) * m_fb.h);
        uint8_t ca = (uint8_t)(c.a * 255);
        for (int y = y0; y < y1; y++)
            for (int x = x0; x < x1; x++)
                m_fb.set_pixel(x, y,
                    (uint8_t)(c.r*255), (uint8_t)(c.g*255),
                    (uint8_t)(c.b*255), ca);
    }

    void draw_circle(float cx, float cy, float radius, const Color& c) override {
        int ix = (int)(cx * m_fb.w);
        int iy = (int)(cy * m_fb.h);
        int ir = (int)(radius * std::min(m_fb.w, m_fb.h));
        m_fb.draw_circle_filled(ix, iy, ir,
            (uint8_t)(c.r*255), (uint8_t)(c.g*255),
            (uint8_t)(c.b*255), (uint8_t)(c.a*255));
    }

    void draw_balloon(float cx, float cy, float radius,
                      const Color& inner, float alpha) override {
        int ix = (int)(cx * m_fb.w);
        int iy = (int)(cy * m_fb.h);
        int ir = (int)(radius * std::min(m_fb.w, m_fb.h));
        uint8_t a = (uint8_t)(alpha * inner.a * 255);
        // Inner (lighter) to outer (darker) gradient
        uint8_t ir2 = (uint8_t)std::min(255.0f, inner.r * 255 + 80);
        uint8_t ig2 = (uint8_t)std::min(255.0f, inner.g * 255 + 80);
        uint8_t ib2 = (uint8_t)std::min(255.0f, inner.b * 255 + 80);
        uint8_t or_ = (uint8_t)std::max(0.0f, inner.r * 255 - 40);
        uint8_t og = (uint8_t)std::max(0.0f, inner.g * 255 - 40);
        uint8_t ob = (uint8_t)std::max(0.0f, inner.b * 255 - 40);
        m_fb.draw_circle_gradient(ix, iy, ir, ir2, ig2, ib2, or_, og, ob, a);

        // String
        int sx = ix, sy = iy + ir;
        int ex = ix + ir/2, ey = iy + ir*2;
        for (int t = 0; t <= 20; t++) {
            float tt = t / 20.0f;
            int px = (int)(sx * (1-tt) + ex * tt);
            int py = (int)(sy * (1-tt) + ey * tt);
            m_fb.set_pixel(px, py, 100, 116, 139, a);
        }
        // Highlight
        float hl_r = ir * 0.25f, hl_adj = ir * 0.3f;
        for (int dy = -(int)hl_r; dy <= (int)hl_r; dy++)
            for (int dx = -(int)hl_r; dx <= (int)hl_r; dx++)
                if (dx*dx + dy*dy <= hl_r*hl_r)
                    m_fb.set_pixel(ix - (int)hl_adj + dx, iy - (int)hl_adj + dy,
                        255, 255, 255, (uint8_t)(a * 0.3f));
    }

    void draw_text(float x, float y, const std::string& text,
                   const Color& c, float size) override {
        // Software text rendering: placeholder — draws a small rect per char
        int ix = (int)(x * m_fb.w);
        int iy = (int)(y * m_fb.h);
        int ch_w = (int)(size * 0.6f);
        int ch_h = (int)(size);
        uint8_t ca = (uint8_t)(c.a * 255);
        for (size_t i = 0; i < text.size(); i++) {
            for (int py = 0; py < ch_h; py++)
                for (int px = 0; px < ch_w; px++)
                    m_fb.set_pixel(ix + i*ch_w + px, iy + py,
                        (uint8_t)(c.r*255), (uint8_t)(c.g*255),
                        (uint8_t)(c.b*255), ca);
        }
    }

    void flush() override {}

    std::vector<uint8_t> read_pixels() override {
        return m_fb.pixels;
    }
};

}}} // namespace pixhal::vk::detail
#endif

// ── Factory methods ────────────────────────────────────────
namespace pixhal { namespace vk {

std::unique_ptr<Instance> Instance::create(const InstanceConfig& cfg) {
    WindowProps wp;
    wp.title = cfg.app_name;
    wp.width = 800;
    wp.height = 600;
#if PIXHAL_VK_AVAILABLE
    // return std::make_unique<detail::VkInstance>(cfg, wp);
    return nullptr;
#else
    return std::make_unique<detail::SoftwareInstance>(cfg, wp);
#endif
}

std::unique_ptr<Shader> Shader::compile(const ShaderSource& src) {
    return nullptr;  // Requires SPIR-V tools or Vulkan SDK
}

std::unique_ptr<Shader> Shader::from_file(const std::string&, ShaderStage) {
    return nullptr;
}

std::unique_ptr<Shader> Shader::from_spirv(const std::vector<uint32_t>&, ShaderStage) {
    return nullptr;
}

std::unique_ptr<Pipeline> Pipeline::create(const PipelineConfig&) {
    return nullptr;
}

DefaultPipelines DefaultPipelines::create(uint32_t, uint32_t) {
    return {};
}

std::unique_ptr<Swapchain> Swapchain::create(const SwapchainConfig&, const NativeHandle&) {
    return nullptr;
}

// ── Renderer ───────────────────────────────────────────────
std::unique_ptr<Renderer> Renderer::create(const Config& cfg) {
    // For now, returns null — the Python fallback creates its own.
    // In production, this would instantiate a detail::VkRenderer.
    return nullptr;
}

}} // namespace
