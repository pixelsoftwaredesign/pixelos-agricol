#ifndef PIXHAL_VK_SHADER_H
#define PIXHAL_VK_SHADER_H

#include "types.h"
#include <vector>
#include <string>
#include <memory>

namespace pixhal {
namespace vk {

enum class ShaderStage : uint8_t {
    Vertex   = 0,
    Fragment = 1,
    Compute  = 2,
};

struct ShaderSource {
    ShaderStage stage;
    std::string glsl;           // GLSL source
    std::vector<uint32_t> spirv; // pre-compiled SPIR-V (optional)
};

class Shader {
public:
    static std::unique_ptr<Shader> compile(const ShaderSource& src);
    static std::unique_ptr<Shader> from_file(const std::string& path, ShaderStage stage);
    static std::unique_ptr<Shader> from_spirv(const std::vector<uint32_t>& code,
                                               ShaderStage stage);

    virtual ~Shader() = default;
    virtual ShaderStage stage() const noexcept = 0;
    virtual const std::string& source() const noexcept = 0;
    virtual bool valid() const noexcept = 0;
};

// ── Built-in shaders ──────────────────────────────────────
struct BuiltinShaders {
    std::unique_ptr<Shader> triangle_vert;
    std::unique_ptr<Shader> triangle_frag;
    std::unique_ptr<Shader> balloon_vert;
    std::unique_ptr<Shader> balloon_frag;
    std::unique_ptr<Shader> rect_vert;
    std::unique_ptr<Shader> rect_frag;

    static BuiltinShaders load();
};

} // namespace vk
} // namespace pixhal

#endif
