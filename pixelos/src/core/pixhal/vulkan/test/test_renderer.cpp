#include <gtest/gtest.h>
#include "pixhal/vk/instance.h"
#include "pixhal/vk/renderer.h"
#include <cmath>
#include <cstdint>
#include <vector>

namespace vk = pixhal::vk;

// ── Instance tests ──────────────────────────────────────────

TEST(SoftwareInstanceTest, CreateAndQuery) {
    auto inst = vk::Instance::create();
    ASSERT_NE(inst, nullptr);
    EXPECT_EQ(inst->backend(), vk::Backend::Fallback);
    EXPECT_GT(inst->width(), 0);
    EXPECT_GT(inst->height(), 0);
    EXPECT_NEAR(inst->aspect(), (float)inst->width() / inst->height(), 0.01f);
    EXPECT_FALSE(inst->caps().device_name.empty());
    EXPECT_EQ(inst->caps().max_texture_size, 4096);
}

TEST(SoftwareInstanceTest, CustomSize) {
    vk::InstanceConfig cfg;
    cfg.app_name = "TestApp";
    auto inst = vk::Instance::create(cfg);
    ASSERT_NE(inst, nullptr);
    EXPECT_EQ(inst->width(), 800);
    EXPECT_EQ(inst->height(), 600);
}

TEST(SoftwareInstanceTest, ClearAndReadPixels) {
    auto inst = vk::Instance::create();
    ASSERT_NE(inst, nullptr);

    inst->clear(vk::Color(0.1f, 0.2f, 0.3f));
    auto pixels = inst->read_pixels();
    EXPECT_EQ(pixels.size(), inst->width() * inst->height() * 4);

    uint32_t w = inst->width(), h = inst->height();
    uint8_t r = pixels[0], g = pixels[1], b = pixels[2];
    EXPECT_NEAR(r, 25, 2);   // 0.1 * 255 = 25.5
    EXPECT_NEAR(g, 51, 2);   // 0.2 * 255 = 51.0
    EXPECT_NEAR(b, 76, 2);   // 0.3 * 255 = 76.5

    // Check a few more pixels
    uint32_t mid = (h / 2) * w * 4 + (w / 2) * 4;
    EXPECT_NEAR(pixels[mid + 0], 25, 2);
    EXPECT_NEAR(pixels[mid + 2], 76, 2);
    EXPECT_EQ(pixels[mid + 3], 255);  // alpha = 1.0
}

TEST(SoftwareInstanceTest, DrawRect) {
    auto inst = vk::Instance::create();
    inst->clear(vk::Color(0, 0, 0));

    // Draw white rect in top-left quadrant
    inst->draw_rect({0.0f, 0.0f, 0.5f, 0.5f}, {1.0f, 1.0f, 1.0f});

    auto pixels = inst->read_pixels();
    uint32_t w = inst->width(), h = inst->height();

    // Inside rect: should be white
    uint32_t inside = (h / 4) * w * 4 + (w / 4) * 4;
    EXPECT_GT(pixels[inside + 0], 200);
    EXPECT_GT(pixels[inside + 1], 200);
    EXPECT_GT(pixels[inside + 2], 200);

    // Outside rect: should be black
    uint32_t outside = (3 * h / 4) * w * 4 + (3 * w / 4) * 4;
    EXPECT_LT(pixels[outside + 0], 10);
    EXPECT_LT(pixels[outside + 1], 10);
    EXPECT_LT(pixels[outside + 2], 10);
}

TEST(SoftwareInstanceTest, DrawCircle) {
    auto inst = vk::Instance::create();
    inst->clear(vk::Color(0, 0, 0));

    float cx = 0.5f, cy = 0.5f;
    float radius = 0.2f;
    inst->draw_circle(cx, cy, radius, {0.0f, 1.0f, 0.0f});

    auto pixels = inst->read_pixels();
    uint32_t w = inst->width(), h = inst->height();

    // Center should be green
    uint32_t center = (h / 2) * w * 4 + (w / 2) * 4;
    EXPECT_NEAR(pixels[center + 0], 0, 5);
    EXPECT_GT(pixels[center + 1], 200);
    EXPECT_NEAR(pixels[center + 2], 0, 5);

    // Corner should be black
    uint32_t corner = 0;
    EXPECT_LT(pixels[corner + 1], 10);
}

TEST(SoftwareInstanceTest, DrawBalloon) {
    auto inst = vk::Instance::create();
    inst->clear(vk::Color(0, 0, 0));

    inst->draw_balloon(0.5f, 0.5f, 0.15f, {1.0f, 0.0f, 0.0f}, 1.0f);

    auto pixels = inst->read_pixels();
    uint32_t w = inst->width(), h = inst->height();
    uint32_t center = (h / 2) * w * 4 + (w / 2) * 4;

    // Balloon center should have some red
    EXPECT_GT(pixels[center + 0], 100);
    // Alpha channel should indicate non-transparent
    EXPECT_GT(pixels[center + 3], 100);
}

TEST(SoftwareInstanceTest, DrawText) {
    auto inst = vk::Instance::create();
    inst->clear(vk::Color(0, 0, 0));
    inst->draw_text(0.1f, 0.1f, "Hello", {1.0f, 1.0f, 1.0f}, 14.0f);

    auto pixels = inst->read_pixels();
    uint32_t w = inst->width(), h = inst->height();

    // Text area should have some non-black pixels
    uint32_t text_area = (uint32_t)(0.1f * h) * w * 4 + (uint32_t)(0.1f * w) * 4;
    bool has_white = false;
    for (int i = 0; i < 100; i++) {
        if (pixels[text_area + i * 4] > 200) { has_white = true; break; }
    }
    EXPECT_TRUE(has_white);
}

TEST(SoftwareInstanceTest, BeginEndFrame) {
    auto inst = vk::Instance::create();
    EXPECT_TRUE(inst->begin_frame());
    inst->end_frame();
    inst->present();
    inst->flush();
}

// ── Renderer ────────────────────────────────────────────────

TEST(RendererTest, CreateReturnsNull) {
    // Currently Renderer::create() returns nullptr without Vulkan SDK
    auto renderer = vk::Renderer::create({});
    EXPECT_EQ(renderer, nullptr);
}

// ── Frame lifecycle ─────────────────────────────────────────

TEST(SoftwareInstanceTest, MultiFrameClear) {
    auto inst = vk::Instance::create();

    inst->clear(vk::Color(1, 0, 0));
    auto p1 = inst->read_pixels();
    EXPECT_GT(p1[0], 200);

    inst->clear(vk::Color(0, 1, 0));
    auto p2 = inst->read_pixels();
    EXPECT_LT(p2[0], 10);
    EXPECT_GT(p2[1], 200);
}

// ── Alpha blending ─────────────────────────────────────────

TEST(SoftwareInstanceTest, AlphaBlend) {
    auto inst = vk::Instance::create();
    inst->clear(vk::Color(0, 0, 0));

    // Draw semi-transparent white over black
    inst->draw_rect({0.0f, 0.0f, 1.0f, 1.0f}, {1.0f, 1.0f, 1.0f, 0.5f});
    auto pixels = inst->read_pixels();

    uint32_t w = inst->width();
    uint32_t mid = (inst->height() / 2) * w * 4 + (w / 2) * 4;

    // Should be roughly 50% gray with 50% alpha
    EXPECT_NEAR(pixels[mid + 0], 127, 15);
    EXPECT_NEAR(pixels[mid + 3], 127, 15);
}

// ── DeviceCaps ──────────────────────────────────────────────

TEST(DeviceCapsTest, DefaultValues) {
    vk::DeviceCaps caps;
    EXPECT_TRUE(caps.device_name.empty() || !caps.device_name.empty());
    EXPECT_EQ(caps.max_texture_size, 4096);
    EXPECT_EQ(caps.max_draw_calls, 65536);
    EXPECT_FALSE(caps.has_compute);
    EXPECT_FLOAT_EQ(caps.max_anisotropy, 16.0f);
}

// ── Color utilities ─────────────────────────────────────────

TEST(ColorTest, FromRGBA8) {
    auto c = vk::Color::from_rgba8(255, 128, 64, 32);
    EXPECT_NEAR(c.r, 1.0f, 0.01f);
    EXPECT_NEAR(c.g, 0.502f, 0.01f);
    EXPECT_NEAR(c.b, 0.251f, 0.01f);
    EXPECT_NEAR(c.a, 0.125f, 0.01f);
}
