cmake_minimum_required(VERSION 3.20)
project(render_engine VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# skia.lib was built with /MDd (DynamicDebug) — match it to avoid CRT mismatch.
# Node.js addons must use the same CRT as the linked static libs.
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDebugDLL")

# ── Paths ──────────────────────────────────────────────────────────────────────
set(DEPS "${CMAKE_CURRENT_SOURCE_DIR}/deps")
set(SRC  "${CMAKE_CURRENT_SOURCE_DIR}/src")
set(VK_SRC "D:/Qteee-Vulkan/src")

find_package(Vulkan REQUIRED)

# cmake-js provides CMAKE_JS_INC (Node.js headers) and CMAKE_JS_LIB
message(STATUS "cmake-js INC: ${CMAKE_JS_INC}")
message(STATUS "cmake-js LIB: ${CMAKE_JS_LIB}")

# node-addon-api (provides napi.h)
execute_process(
    COMMAND node -e "process.stdout.write(require('node-addon-api').include_dir)"
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    OUTPUT_VARIABLE NAPI_INCLUDE_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
message(STATUS "node-addon-api: ${NAPI_INCLUDE_DIR}")

# ── Source files ───────────────────────────────────────────────────────────────
# Minimal set: no Qteee-Vulkan ecosystem (no Lottie, no imageDecorder,
# no ExpressionEngine, no DecodeScheduler). Python decodes video;
# HeadlessCompositor composites raw RGBA frames on the GPU.

set(SOURCES
    # ── NAPI bridge + compositor ────────────────────────────────────────────────
    src/napi/RenderEngineAddon.cpp
    src/HeadlessCompositor.cpp

    # ── Drawing modules (text, shape, pen) ──────────────────────────────────────
    src/rendering/DrawText.cpp
    src/rendering/DrawShape.cpp
    src/rendering/DrawPen.cpp

    # ── Vulkan GPU (Qt-free) ───────────────────────────────────────────────────
    src/gpu/vulkan/device/DeviceContext.cpp
    src/gpu/vulkan/memory/Buffer.cpp
    src/gpu/vulkan/memory/Texture.cpp
    src/gpu/vulkan/command/CommandBuffer.cpp
    src/gpu/vulkan/command/CommandPool.cpp
    src/gpu/vulkan/skia/SkiaContext.cpp

    # ── Video decode (D3D11VA HW + SW FFmpeg fallback) ────────────────────────
    src/video/HwVideoDecoder.cpp
    src/video/videoDecoder.cpp
    src/video/ClipDecoder.cpp
)

# ── NAPI addon target ──────────────────────────────────────────────────────────
add_library(render_engine SHARED ${SOURCES} ${CMAKE_JS_SRC})
set_target_properties(render_engine PROPERTIES
    PREFIX ""
    SUFFIX ".node"
    OUTPUT_NAME "render_engine"
)

# ── Include directories ────────────────────────────────────────────────────────
target_include_directories(render_engine PRIVATE
    ${SRC}                              # native/src — our modified headers first
    ${DEPS}/include                     # GLM, stb, nlohmann/json
    ${DEPS}/ffmpeg/include              # libavutil/frame.h, libavcodec/avcodec.h etc.
    ${DEPS}/skia                        # skia internal (include/core/...)
    ${DEPS}/skia/include                # skia external API (core/SkCanvas.h etc.)
    ${DEPS}/skia/modules/skcms          # skcms.h required by SkColorSpace.h
    ${DEPS}/vma                         # vk_mem_alloc.h
    ${Vulkan_INCLUDE_DIRS}
    ${CMAKE_JS_INC}                     # Node.js headers
    ${NAPI_INCLUDE_DIR}                 # napi.h from node-addon-api
    ${VK_SRC}                           # D:\Qteee-Vulkan\src — core/ headers
)

target_compile_definitions(render_engine PRIVATE
    NAPI_VERSION=8
    NAPI_DISABLE_CPP_EXCEPTIONS
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    VK_USE_PLATFORM_WIN32_KHR
    SK_VULKAN
    # Do NOT set _ITERATOR_DEBUG_LEVEL — let /MDd default it to 2 (matching skia.lib)
)

if(MSVC)
    target_compile_options(render_engine PRIVATE
        /W1        # Minimal warnings for copied third-party code
        /wd4819    # Code page warnings
        /wd4244    # Conversion warnings
        /wd4267    # size_t conversion warnings
        /wd4005    # Macro redefinition warnings
    )
endif()

# ── Link libraries ─────────────────────────────────────────────────────────────
set(FFMPEG_LIB_DIR "${DEPS}/ffmpeg/lib")

target_link_libraries(render_engine PRIVATE
    ${CMAKE_JS_LIB}
    ${Vulkan_LIBRARIES}
    "${DEPS}/skia/lib/skia.lib"
    "${FFMPEG_LIB_DIR}/avcodec.lib"
    "${FFMPEG_LIB_DIR}/avformat.lib"
    "${FFMPEG_LIB_DIR}/avutil.lib"
    "${FFMPEG_LIB_DIR}/swscale.lib"
    "${FFMPEG_LIB_DIR}/swresample.lib"
    d3d11.lib
    dxgi.lib
    d3dcompiler.lib
    dxguid.lib
)

# Copy FFmpeg DLLs next to the .node file on every build
set(FFMPEG_BIN_DIR "D:/Qteee-Vulkan/dependencies/ffmpeg/bin")
if(EXISTS "${FFMPEG_BIN_DIR}")
    add_custom_command(TARGET render_engine POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_directory
            "${FFMPEG_BIN_DIR}"
            $<TARGET_FILE_DIR:render_engine>
        COMMENT "Copying FFmpeg DLLs..."
    )
endif()
