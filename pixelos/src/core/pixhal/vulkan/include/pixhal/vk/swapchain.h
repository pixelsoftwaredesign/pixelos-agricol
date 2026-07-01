#ifndef PIXHAL_VK_SWAPCHAIN_H
#define PIXHAL_VK_SWAPCHAIN_H

#include "types.h"
#include <memory>
#include <vector>

namespace pixhal {
namespace vk {

struct SwapchainConfig {
    uint32_t width  = 800;
    uint32_t height = 600;
    bool vsync      = true;
    uint32_t image_count = 2;  // double or triple buffer
};

// Forward declarations for platform-specific types
struct NativeHandle {
    void* window = nullptr;      // GLFWwindow*, SDL_Window*, HWND, etc.
    void* display = nullptr;     // Wayland/X11 display
    uint64_t surface = 0;        // VkSurfaceKHR
};

class Swapchain {
public:
    static std::unique_ptr<Swapchain> create(const SwapchainConfig& cfg,
                                              const NativeHandle& native);

    virtual ~Swapchain() = default;

    virtual bool acquire_next_image() = 0;
    virtual bool present() = 0;

    virtual uint32_t width() const noexcept = 0;
    virtual uint32_t height() const noexcept = 0;
    virtual uint32_t image_index() const noexcept = 0;
    virtual uint32_t image_count() const noexcept = 0;
    virtual float aspect() const noexcept = 0;

    virtual std::vector<uint8_t> read_pixels() = 0;
};

} // namespace vk
} // namespace pixhal

#endif
