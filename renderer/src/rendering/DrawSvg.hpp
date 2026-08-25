#pragma once

#include "include/core/SkCanvas.h"
#include "napi/FrameDescriptor.hpp"

namespace fade::drawing {

void drawSvg(SkCanvas *canvas, const ClipDesc &clip, int canvasW, int canvasH);

void clearSvgCache();

} // namespace fade::drawing
