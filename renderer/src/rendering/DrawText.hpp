#pragma once

#include "napi/FrameDescriptor.hpp"

#include <core/SkCanvas.h>
#include <core/SkFont.h>
#include <core/SkFontMgr.h>
#include <core/SkFontStyle.h>
#include <core/SkPaint.h>
#include <core/SkTextBlob.h>

namespace fade::drawing {

/**
 * Draw a text clip onto canvas.
 *
 * @param canvas   Target Skia canvas (already has clip transform applied by
 * caller if needed)
 * @param clip     Full ClipDesc — uses clip.text (TextDesc) + clip.transform +
 * clip.opacity
 * @param canvasW  Compositor output width  (for centering default origin)
 * @param canvasH  Compositor output height
 */
void drawText(SkCanvas *canvas, const ClipDesc &clip, int canvasW, int canvasH);

} // namespace fade::drawing
