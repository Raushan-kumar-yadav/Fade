#pragma once
// DrawSvg.hpp — renders an SVG file onto a Skia canvas.
// Mirrors Qteee-Vulkan SvgDrawNode / SvgAssest adapted for Fade's
// canvas-based compositor (no Vulkan push-constants, no GLM).

#include "napi/FrameDescriptor.hpp"
#include "include/core/SkCanvas.h"

namespace fade::drawing {

// Load (or cache) the SVG DOM for `clip.file` and render it to `canvas`.
// Applies the clip's transform (x/y/scale/rotation/anchor), opacity, blend mode,
// and optional tint color filter exactly as Qteee-Vulkan's SvgDrawNode does.
// `canvasW` / `canvasH` are the compositor output dimensions.
void drawSvg(SkCanvas* canvas, const ClipDesc& clip, int canvasW, int canvasH);

// Clear the SVG DOM cache (call when a project is closed / asset is reimported).
void clearSvgCache();

} // namespace fade::drawing
