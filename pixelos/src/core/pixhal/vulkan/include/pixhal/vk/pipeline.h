#ifndef PIXHAL_VK_PIPELINE_H
#define PIXHAL_VK_PIPELINE_H

#include "types.h"
#include "shader.h"
#include <memory>
#include <vector>

namespace pixhal {
namespace vk {

struct PipelineConfig {
    std::unique_ptr<Shader> vert_shader;
    std::unique_ptr<Shader> frag_shader;
    uint32_t width  = 800;
    uint32_t height = 600;
    bool alpha_blend = true;
    bool depth_test  = false;
    float line_width = 1.0f;
};

class Pipeline {
public:
    static std::unique_ptr<Pipeline> create(const PipelineConfig& cfg);

    virtual ~Pipeline() = default;

    virtual void bind() = 0;
    virtual void push_constant(const void* data, uint32_t size, uint32_t offset = 0) = 0;
    virtual void draw(uint32_t vertex_count, uint32_t instance_count = 1) = 0;
    virtual void draw_indexed(uint32_t index_count, uint32_t instance_count = 1) = 0;

    virtual bool valid() const noexcept = 0;
    virtual const PipelineConfig& config() const noexcept = 0;
};

// ── Default pipelines for PixHAL ──────────────────────────
struct DefaultPipelines {
    std::unique_ptr<Pipeline> triangle;
    std::unique_ptr<Pipeline> balloon;
    std::unique_ptr<Pipeline> rect;

    static DefaultPipelines create(uint32_t w, uint32_t h);
};

} // namespace vk
} // namespace pixhal

#endif
