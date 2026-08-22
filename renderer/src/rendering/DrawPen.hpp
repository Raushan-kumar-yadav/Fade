#pragma once
#include "../napi/FrameDescriptor.hpp"
#include "core/SkCanvas.h"

namespace fade::drawing {

void drawPen(SkCanvas *canvas, const ClipDesc &clip, int canvasW, int canvasH);

} // namespace fade::drawing
