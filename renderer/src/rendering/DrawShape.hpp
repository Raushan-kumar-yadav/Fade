#pragma once

#include "napi/FrameDescriptor.hpp"

#include <core/SkCanvas.h>
#include <core/SkPaint.h>
#include <core/SkPath.h>

namespace fade::drawing {

/**
 * Draw a shape clip onto canvas.
 *
 * @param canvas   Target Skia canvas
 * @param clip     Full ClipDesc — uses clip.shape (ShapeDesc) + clip.transform
 * + clip.opacity
 * @param canvasW  Compositor output width  (shape origin defaults to canvas
 * center)
 * @param canvasH  Compositor output height
 */
void drawShape(SkCanvas *canvas, const ClipDesc &clip, int canvasW,
               int canvasH);

} // namespace fade::drawing
