#include "rendering/DrawPen.hpp"

// Skia includes
#include "core/SkBlurTypes.h"
#include "core/SkMaskFilter.h"
#include "include/core/SkPathBuilder.h"

#include <cmath>

namespace fade::drawing {

static constexpr float kPI_PEN = 3.14159265358979323846f;

static inline bool isZero(float x, float y) {
  return (x * x + y * y) < 0.0001f;
}

//   Path builder

static SkPath buildFromPoints(const std::vector<ClipDesc::BezierPt> &pts,
                              bool closed) {
  SkPathBuilder builder;
  if (pts.empty())
    return builder.detach();

  builder.moveTo(pts[0].x, pts[0].y);

  for (size_t i = 1; i < pts.size(); ++i) {
    const auto &prev = pts[i - 1];
    const auto &curr = pts[i];

    // Has tangent if either endpoint has a non-zero out/in tangent
    bool hasTangent =
        !isZero(prev.outX, prev.outY) || !isZero(curr.inX, curr.inY);

    if (hasTangent) {

      builder.cubicTo(prev.x + prev.outX, prev.y + prev.outY, curr.x + curr.inX,
                      curr.y + curr.inY, curr.x, curr.y);
    } else {
      builder.lineTo(curr.x, curr.y);
    }
  }

  // Close: connect last point back to first
  if (closed && pts.size() > 1) {
    const auto &last = pts.back();
    const auto &first = pts.front();
    bool hasTangent =
        !isZero(last.outX, last.outY) || !isZero(first.inX, first.inY);
    if (hasTangent) {
      builder.cubicTo(last.x + last.outX, last.y + last.outY,
                      first.x + first.inX, first.y + first.inY, first.x,
                      first.y);
    }
    builder.close();
  }

  return builder.detach();
}

//   Public API

void drawPen(SkCanvas *canvas, const ClipDesc &clip, int canvasW, int canvasH) {
  const ClipDesc::PenDesc &pen = clip.pen;
  const float opacity = clip.opacity;

  if (pen.points.empty())
    return;

  // Apply clip-level transform
  canvas->save();
  {
    const auto &t = clip.transform;
    const float cx = t.anchorX * (float)canvasW;
    const float cy = t.anchorY * (float)canvasH;
    canvas->translate(t.x + cx, t.y + cy);
    canvas->rotate(t.rotation);
    canvas->scale(t.scaleX, t.scaleY);
    canvas->translate(-cx, -cy);
  }

  // Build the bezier path
  const SkPath path = buildFromPoints(pen.points, pen.isClosed);

  //   Drop shadow
  if (pen.shadowEnabled) {
    float angleRad = pen.shadowAngle * (kPI_PEN / 180.f);
    float sdx = std::cos(angleRad) * pen.shadowDistance;
    float sdy = std::sin(angleRad) * pen.shadowDistance;

    SkPaint shadowPaint;
    shadowPaint.setStyle(SkPaint::kFill_Style);
    shadowPaint.setColor4f(
        {pen.shadowR, pen.shadowG, pen.shadowB, pen.shadowA * opacity});
    shadowPaint.setAntiAlias(true);
    shadowPaint.setMaskFilter(
        SkMaskFilter::MakeBlur(kNormal_SkBlurStyle, pen.shadowBlur * 0.5f));

    canvas->save();
    canvas->translate(sdx, sdy);
    canvas->drawPath(path, shadowPaint);
    canvas->restore();
  }

  //   Fill
  if (pen.isClosed && pen.fillOpacity > 0.f && pen.fillA > 0.f) {
    SkPaint fillPaint;
    fillPaint.setStyle(SkPaint::kFill_Style);
    fillPaint.setColor4f({pen.fillR, pen.fillG, pen.fillB,
                          pen.fillA * pen.fillOpacity * opacity});
    fillPaint.setAntiAlias(true);
    canvas->drawPath(path, fillPaint);
  }

  //   Stroke
  if (pen.strokeWidth > 0.f) {
    SkPaint strokePaint;
    strokePaint.setStyle(SkPaint::kStroke_Style);
    strokePaint.setStrokeWidth(pen.strokeWidth);
    strokePaint.setColor4f(
        {pen.strokeR, pen.strokeG, pen.strokeB, pen.strokeA * opacity});
    strokePaint.setStrokeCap(SkPaint::kRound_Cap);
    strokePaint.setStrokeJoin(SkPaint::kRound_Join);
    strokePaint.setAntiAlias(true);
    canvas->drawPath(path, strokePaint);
  }

  canvas->restore();
}

} // namespace fade::drawing
