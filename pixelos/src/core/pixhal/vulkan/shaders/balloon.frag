#version 450

layout(location = 0) in vec2 vUV;
layout(location = 1) in vec4 vColor;
layout(location = 2) in vec2 vRes;
layout(location = 3) in float vAlpha;

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 center = vec2(0.5, 0.5);
    float dist  = distance(vUV, center);
    float alpha = 1.0 - smoothstep(0.0, 0.5, dist);
    // highlight
    float hl = smoothstep(0.3, 0.0, distance(vUV, vec2(0.35, 0.35)));
    vec3 col = vColor.rgb + hl * 0.4;
    fragColor = vec4(col, alpha * vColor.a * vAlpha);
}
