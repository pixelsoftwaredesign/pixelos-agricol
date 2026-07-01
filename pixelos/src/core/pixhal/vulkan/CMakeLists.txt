cmake_minimum_required(VERSION 3.20)
project(pixhal-vulkan LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(PIXHAL_VK_AVAILABLE "Build with real Vulkan backend" OFF)

if(PIXHAL_VK_AVAILABLE)
    find_package(Vulkan REQUIRED)
    add_compile_definitions(PIXHAL_VK_AVAILABLE=1)
endif()

add_library(pixhal-vulkan STATIC
    src/renderer.cpp
)

target_include_directories(pixhal-vulkan PUBLIC include)

if(PIXHAL_VK_AVAILABLE)
    target_link_libraries(pixhal-vulkan PUBLIC Vulkan::Vulkan)
endif()

# Python bindings (optional)
option(BUILD_PYBIND "Build pybind11 wrappers" OFF)
if(BUILD_PYBIND)
    find_package(pybind11 REQUIRED)
    pybind11_add_module(_pixhal_vulkan_bind python/bindings.cpp)
    target_link_libraries(_pixhal_vulkan_bind PRIVATE pixhal-vulkan)
endif()

# Tests
option(BUILD_TESTS "Build tests" OFF)
if(BUILD_TESTS)
    enable_testing()
    find_package(GTest REQUIRED)
    add_executable(test_pixhal_vulkan test/test_renderer.cpp)
    target_link_libraries(test_pixhal_vulkan PRIVATE pixhal-vulkan GTest::GTest)
    add_test(NAME pixhal_vulkan COMMAND test_pixhal_vulkan)
endif()
