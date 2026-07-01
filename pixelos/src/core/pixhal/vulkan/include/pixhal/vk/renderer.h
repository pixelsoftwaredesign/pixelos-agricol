#ifndef PIXHAL_VK_RENDERER_H
#define PIXHAL_VK_RENDERER_H

#include "instance.h"
#include "shader.h"
#include "pipeline.h"
#include "types.h"
#include <memory>
#include <string>
#include <functional>

namespace pixhal {
namespace vk {

// ── High-level Renderer ──────────────────────────────────
// Wraps Instance + Pipelines + Shaders into one object.
// This is what PixHAL exposes to the rest of Pixel OS.

class Renderer {
public:
    struct Config {
        std::string title = "PixHAL";
        uint32_t width  = 800;
        uint32_t height = 600;
        bool vsync      = true;
        bool validation = false;
        int target_fps  = 60;

        // Callback: called every frame with elapsed seconds
        std::function<void(float dt)> frame_callback = nullptr;
        // Callback: called on mouse click (x, y normalized 0..1)
        std::function<void(float x, float y)> click_callback = nullptr;
        // Callback: called on resize
        std::function<void(uint32_t w, uint32_t h)> resize_callback = nullptr;
    };

    static std::unique_ptr<Renderer> create(const Config& cfg);

    virtual ~Renderer() = default;

    // Run the render loop (blocks until window closed)
    virtual void run() = 0;

    // Single frame (for embedding in existing event loop)
    virtual bool tick() = 0;

    // Drawing API (intended for game logic callbacks)
    virtual void clear(const Color& c = {}) = 0;
    virtual void draw_balloon(float cx, float cy, float radius,
                              const Color& inner, float alpha) = 0;
    virtual void draw_rect(const Rect& r, const Color& c) = 0;
    virtual void draw_circle(float cx, float cy, float radius,
                             const Color& c) = 0;
    virtual void draw_text(float x, float y, const std::string& text,
                           const Color& c = {1,1,1,1}, float size = 14.0f) = 0;

    // State
    virtual bool running() const noexcept = 0;
    virtual uint32_t width() const noexcept = 0;
    virtual uint32_t height() const noexcept = 0;
    virtual float aspect() const noexcept = 0;
    virtual float fps() const noexcept = 0;
    virtual Backend backend() const noexcept = 0;
    virtual const DeviceCaps& caps() const noexcept = 0;

    // Screenshot
    virtual std::vector<uint8_t> read_pixels() = 0;

    // Close
    virtual void close() = 0;
};

} // namespace vk
} // namespace pixhal

#endif
