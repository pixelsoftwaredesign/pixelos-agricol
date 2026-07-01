#ifndef PIXHAL_VK_INSTANCE_H
#define PIXHAL_VK_INSTANCE_H

#include "types.h"
#include <memory>
#include <vector>
#include <string>

namespace pixhal {
namespace vk {

struct InstanceConfig {
    std::string app_name = "PixHAL";
    uint32_t app_version = 1;
    bool enable_validation = false;
    std::vector<const char*> extensions;
    std::vector<const char*> layers;
};

class Instance {
public:
    static std::unique_ptr<Instance> create(const InstanceConfig& cfg = {});

    virtual ~Instance() = default;

    virtual Backend backend() const noexcept = 0;
    virtual const DeviceCaps& caps() const noexcept = 0;
    virtual uint32_t api_version() const noexcept = 0;
    virtual const std::string& device_name() const noexcept = 0;

    // Frame lifecycle
    virtual bool begin_frame() = 0;
    virtual void end_frame() = 0;
    virtual void present() = 0;

    // Drawing
    virtual void clear(const Color& color = {}) = 0;
    virtual void draw_rect(const Rect& r, const Color& c) = 0;
    virtual void draw_circle(float cx, float cy, float radius, const Color& c) = 0;
    virtual void draw_balloon(float cx, float cy, float radius,
                              const Color& inner, float alpha) = 0;
    virtual void draw_text(float x, float y, const std::string& text,
                           const Color& c, float size = 14.0f) = 0;

    // Batch
    virtual void flush() = 0;

    // Screenshot
    virtual std::vector<uint8_t> read_pixels() = 0;

    // Window
    virtual uint32_t width() const noexcept = 0;
    virtual uint32_t height() const noexcept = 0;
    virtual float aspect() const noexcept = 0;
};

} // namespace vk
} // namespace pixhal

#endif
