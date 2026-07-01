#version 450

layout(location = 0) in vec2 vUV;
layout(location = 1) in vec4 vColor;
layout(location = 2) in vec2 vRes;
layout(location = 3) in float vAlpha;

layout(location = 0) out vec4 fragColor;

void main() {
    fragColor = vec4(vColor.rgb * vColor.a * vAlpha, vColor.a * vAlpha);
}
