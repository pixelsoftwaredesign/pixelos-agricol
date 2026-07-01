#version 450

layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aUV;
layout(location = 2) in vec4 aColor;

layout(push_constant) uniform PushConstants {
    vec2 uResolution;
    float uTime;
    float uGlobalAlpha;
} pc;

layout(location = 0) out vec2 vUV;
layout(location = 1) out vec4 vColor;
layout(location = 2) out vec2 vRes;
layout(location = 3) out float vAlpha;

void main() {
    vUV     = aUV;
    vColor  = aColor;
    vRes    = pc.uResolution;
    vAlpha  = pc.uGlobalAlpha;
    gl_Position = vec4(aPos, 0.0, 1.0);
}
