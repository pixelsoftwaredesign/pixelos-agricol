#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
#include <pybind11/numpy.h>
#include "pixhal/vk/instance.h"
#include "pixhal/vk/shader.h"
#include "pixhal/vk/pipeline.h"
#include "pixhal/vk/swapchain.h"
#include "pixhal/vk/renderer.h"
#include <memory>
#include <string>
#include <vector>

namespace py = pybind11;
namespace vk = pixhal::vk;

// ── Python-facing Renderer wrapper ──────────────────────────
// Bridges Python callables to C++ std::function callbacks.

class PyRenderWrapper {
public:
    vk::Renderer::Config cfg;
    std::unique_ptr<vk::Renderer> renderer;

    py::object py_on_frame;
    py::object py_on_click;
    py::object py_on_resize;

    PyRenderWrapper(uint32_t w, uint32_t h, const std::string& title, int fps)
        : py_on_frame(py::none()), py_on_click(py::none()), py_on_resize(py::none())
    {
        cfg.title = title;
        cfg.width = w;
        cfg.height = h;
        cfg.target_fps = fps;

        cfg.frame_callback = [this](float dt) {
            if (!py_on_frame.is_none()) {
                py::gil_scoped_acquire gil;
                try { py_on_frame(dt); }
                catch (py::error_already_set& e) { py::print("on_frame error:", e.what()); }
            }
        };

        cfg.click_callback = [this](float x, float y) {
            if (!py_on_click.is_none()) {
                py::gil_scoped_acquire gil;
                try { py_on_click(x, y); }
                catch (py::error_already_set& e) { py::print("on_click error:", e.what()); }
            }
        };

        cfg.resize_callback = [this](uint32_t w, uint32_t h) {
            if (!py_on_resize.is_none()) {
                py::gil_scoped_acquire gil;
                try { py_on_resize(w, h); }
                catch (py::error_already_set& e) { py::print("on_resize error:", e.what()); }
            }
        };

        renderer = vk::Renderer::create(cfg);
        if (!renderer) {
            throw std::runtime_error(
                "PixHAL Vulkan native renderer not compiled. "
                "Use SoftwareRenderer from py_fallback instead.");
        }
    }

    void clear(const vk::Color& c) { renderer->clear(c); }
    void draw_rect(const vk::Rect& r, const vk::Color& c) { renderer->draw_rect(r, c); }
    void draw_circle(float cx, float cy, float radius, const vk::Color& c) {
        renderer->draw_circle(cx, cy, radius, c);
    }
    void draw_balloon(float cx, float cy, float radius, const vk::Color& inner, float alpha) {
        renderer->draw_balloon(cx, cy, radius, inner, alpha);
    }
    void draw_text(float x, float y, const std::string& text, const vk::Color& c, float size) {
        renderer->draw_text(x, y, text, c, size);
    }

    void run() { renderer->run(); }
    bool tick() { return renderer->tick(); }
    void close() { renderer->close(); }

    bool running() const { return renderer->running(); }
    uint32_t width() const { return renderer->width(); }
    uint32_t height() const { return renderer->height(); }
    float aspect() const { return renderer->aspect(); }
    float fps() const { return renderer->fps(); }
    vk::Backend backend() const { return renderer->backend(); }
    vk::DeviceCaps caps() const { return renderer->caps(); }

    py::array_t<uint8_t> read_pixels() {
        auto pixels = renderer->read_pixels();
        if (pixels.empty()) return py::array();
        return py::array_t<uint8_t>(
            {(py::ssize_t)renderer->height(), (py::ssize_t)renderer->width(), 4},
            {(py::ssize_t)renderer->width() * 4, 4, 1},
            pixels.data(),
            py::capsule(pixels.data(), [](void*) {})
        );
    }
};

// ── Module ──────────────────────────────────────────────────

PYBIND11_MODULE(_pixhal_vulkan_bind, m) {
    m.doc() = "PixHAL Vulkan native rendering engine";

    // Backend enum
    py::enum_<vk::Backend>(m, "Backend")
        .value("Vulkan", vk::Backend::Vulkan)
        .value("Fallback", vk::Backend::Fallback);

    // Color
    py::class_<vk::Color>(m, "Color")
        .def(py::init<>())
        .def(py::init<float, float, float, float>(),
             py::arg("r")=1.0f, py::arg("g")=1.0f,
             py::arg("b")=1.0f, py::arg("a")=1.0f)
        .def_readwrite("r", &vk::Color::r)
        .def_readwrite("g", &vk::Color::g)
        .def_readwrite("b", &vk::Color::b)
        .def_readwrite("a", &vk::Color::a)
        .def_static("from_rgba8", &vk::Color::from_rgba8);

    // Rect
    py::class_<vk::Rect>(m, "Rect")
        .def(py::init<>())
        .def(py::init<float, float, float, float>(),
             py::arg("x")=0.0f, py::arg("y")=0.0f,
             py::arg("w")=0.0f, py::arg("h")=0.0f)
        .def_readwrite("x", &vk::Rect::x)
        .def_readwrite("y", &vk::Rect::y)
        .def_readwrite("w", &vk::Rect::w)
        .def_readwrite("h", &vk::Rect::h);

    // DeviceCaps
    py::class_<vk::DeviceCaps>(m, "DeviceCaps")
        .def(py::init<>())
        .def_readwrite("device_name", &vk::DeviceCaps::device_name)
        .def_readwrite("max_texture_size", &vk::DeviceCaps::max_texture_size)
        .def_readwrite("max_draw_calls", &vk::DeviceCaps::max_draw_calls)
        .def_readwrite("has_compute", &vk::DeviceCaps::has_compute)
        .def_readwrite("max_anisotropy", &vk::DeviceCaps::max_anisotropy);

    // Forward declare Instance
    py::class_<vk::Instance>(m, "Instance")
        .def_static("create", [](const vk::InstanceConfig& cfg) {
            auto inst = vk::Instance::create(cfg);
            if (!inst) throw std::runtime_error("Instance::create returned null");
            return inst;
        }, py::arg("cfg")=vk::InstanceConfig{})
        .def("backend", &vk::Instance::backend)
        .def("caps", &vk::Instance::caps, py::return_value_policy::reference_internal)
        .def("begin_frame", &vk::Instance::begin_frame)
        .def("end_frame", &vk::Instance::end_frame)
        .def("present", &vk::Instance::present)
        .def("clear", &vk::Instance::clear, py::arg("color")=vk::Color{})
        .def("draw_rect", &vk::Instance::draw_rect)
        .def("draw_circle", &vk::Instance::draw_circle)
        .def("draw_balloon", &vk::Instance::draw_balloon)
        .def("draw_text", &vk::Instance::draw_text, py::arg("x"), py::arg("y"),
             py::arg("text"), py::arg("color")=vk::Color{1,1,1,1},
             py::arg("size")=14.0f)
        .def("flush", &vk::Instance::flush)
        .def("read_pixels", &vk::Instance::read_pixels)
        .def("width", &vk::Instance::width)
        .def("height", &vk::Instance::height)
        .def("aspect", &vk::Instance::aspect)
        .def("device_name", &vk::Instance::device_name);

    // Renderer wrapper (Python-facing with callbacks)
    py::class_<PyRenderWrapper>(m, "Renderer")
        .def(py::init<uint32_t, uint32_t, const std::string&, int>(),
             py::arg("width")=800, py::arg("height")=600,
             py::arg("title")="PixHAL", py::arg("target_fps")=60)
        .def_readwrite("on_frame", &PyRenderWrapper::py_on_frame)
        .def_readwrite("on_click", &PyRenderWrapper::py_on_click)
        .def_readwrite("on_resize", &PyRenderWrapper::py_on_resize)
        .def("clear", &PyRenderWrapper::clear, py::arg("color")=vk::Color{})
        .def("draw_rect", &PyRenderWrapper::draw_rect)
        .def("draw_circle", &PyRenderWrapper::draw_circle)
        .def("draw_balloon", &PyRenderWrapper::draw_balloon)
        .def("draw_text", &PyRenderWrapper::draw_text, py::arg("x"), py::arg("y"),
             py::arg("text"), py::arg("color")=vk::Color{1,1,1,1},
             py::arg("size")=14.0f)
        .def("run", &PyRenderWrapper::run)
        .def("tick", &PyRenderWrapper::tick)
        .def("close", &PyRenderWrapper::close)
        .def_property_readonly("running", &PyRenderWrapper::running)
        .def_property_readonly("width", &PyRenderWrapper::width)
        .def_property_readonly("height", &PyRenderWrapper::height)
        .def_property_readonly("aspect", &PyRenderWrapper::aspect)
        .def_property_readonly("fps", &PyRenderWrapper::fps)
        .def_property_readonly("backend", &PyRenderWrapper::backend)
        .def_property_readonly("caps", &PyRenderWrapper::caps)
        .def("read_pixels", &PyRenderWrapper::read_pixels);
}
