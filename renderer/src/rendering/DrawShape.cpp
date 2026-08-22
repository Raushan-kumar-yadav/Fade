#include "rendering/DrawShape.hpp"

#include "core/SkBlurTypes.h"
#include "core/SkM44.h"
#include "core/SkMaskFilter.h"
#include "core/SkPath.h"
#include "include/core/SkPathBuilder.h" // only needed for polygon / star

#include <algorithm>
#include <cmath>

namespace fade::drawing {

static constexpr float kPI = 3.14159265358979323846f;

static SkPath buildRect(const ClipDesc::ShapeDesc &ss, float cx, float cy) {
  SkRect rect = SkRect::MakeXYWH(cx - ss.width * 0.5f, cy - ss.height * 0.5f,
                                 ss.width, ss.height);
  if (ss.cornerRadius > 0.f)
    return SkPath::RRect(rect, ss.cornerRadius, ss.cornerRadius);
  else
    return SkPath::Rect(rect);
}

static SkPath buildCircle(const ClipDesc::ShapeDesc &ss, float cx, float cy) {
  return SkPath::Circle(cx, cy, ss.radiusX);
}

static SkPath buildEllipse(const ClipDesc::ShapeDesc &ss, float cx, float cy) {
  return SkPath::Oval(SkRect::MakeXYWH(cx - ss.radiusX, cy - ss.radiusY,
                                       ss.radiusX * 2.f, ss.radiusY * 2.f));
}

static SkPath buildLine(const ClipDesc::ShapeDesc &ss, float cx, float cy) {
  SkPathBuilder b;
  b.moveTo(cx + ss.x1, cy + ss.y1);
  b.lineTo(cx + ss.x2, cy + ss.y2);
  return b.detach();
}

static SkPath buildArc(const ClipDesc::ShapeDesc &ss, float cx, float cy) {
  SkPathBuilder b;
  SkRect oval = SkRect::MakeXYWH(cx - ss.arcRadius, cy - ss.arcRadius,
                                 ss.arcRadius * 2.f, ss.arcRadius * 2.f);
  b.addArc(oval, ss.arcStartAngle, ss.arcSweepAngle);
  return b.detach();
}

// Regular N-sided polygon
static SkPath buildPolygon(const ClipDesc::ShapeDesc &ss, float cx, float cy) {
  int numSides = std::max(3, ss.numSides);
  float r = ss.polygonRadius;
  if (r <= 0.f)
    return SkPath{};

  SkPathBuilder b;
  for (int i = 0; i < numSides; ++i) {
    float angle = i * (2.f * kPI / numSides) - (kPI / 2.f);
    float x = cx + std::cos(angle) * r;
    float y = cy + std::sin(angle) * r;
    if (i == 0)
      b.moveTo(x, y);
    else
      b.lineTo(x, y);
  }
  b.close();
  return b.detach();
}

// N-pointed star
static SkPath buildStar(const ClipDesc::ShapeDesc &ss, float cx, float cy) {
  SkPathBuilder b;
  const int pts = ss.numPoints * 2;
  for (int i = 0; i < pts; ++i) {
    float r = (i % 2 == 0) ? ss.outerRadius : ss.innerRadius;
    float angle = (i * kPI / ss.numPoints) - (kPI / 2.f);
    float x = cx + std::cos(angle) * r;
    float y = cy + std::sin(angle) * r;
    if (i == 0)
      b.moveTo(x, y);
    else
      b.lineTo(x, y);
  }
  b.close();
  return b.detach();
}

static SkPath buildPath(const ClipDesc::ShapeDesc &ss, float cx, float cy) {
  if (ss.shapeType == "rect")
    return buildRect(ss, cx, cy);
  else if (ss.shapeType == "circle")
    return buildCircle(ss, cx, cy);
  else if (ss.shapeType == "ellipse")
    return buildEllipse(ss, cx, cy);
  else if (ss.shapeType == "line")
    return buildLine(ss, cx, cy);
  else if (ss.shapeType == "arc")
    return buildArc(ss, cx, cy);
  else if (ss.shapeType == "polygon")
    return buildPolygon(ss, cx, cy);
  else if (ss.shapeType == "star")
    return buildStar(ss, cx, cy);
  return SkPath{};
}

void drawShape(SkCanvas *canvas, const ClipDesc &clip, int canvasW,
               int canvasH) {
  const ClipDesc::ShapeDesc &ss = clip.shape;
  const float opacity = clip.opacity;

  //  Apply clip-level transform
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

  // Shape origin = canvas center
  const float cx = (float)canvasW * 0.5f;
  const float cy = (float)canvasH * 0.5f;

  const SkPath path = buildPath(ss, cx, cy);

  //   Drop shadow
  if (ss.shadowEnabled) {
    float angleRad = ss.shadowAngle * (kPI / 180.f);
    float sdx = std::cos(angleRad) * ss.shadowDistance;
    float sdy = std::sin(angleRad) * ss.shadowDistance;

    SkPaint shadowPaint;
    shadowPaint.setStyle(SkPaint::kFill_Style);
    shadowPaint.setColor4f(
        {ss.shadowR, ss.shadowG, ss.shadowB, ss.shadowA * opacity});
    shadowPaint.setAntiAlias(true);
    shadowPaint.setMaskFilter(
        SkMaskFilter::MakeBlur(kNormal_SkBlurStyle, ss.shadowBlur * 0.5f));

    canvas->save();
    canvas->translate(sdx, sdy);
    canvas->drawPath(path, shadowPaint);
    canvas->restore();
  }

  //   Fill
  const bool isLine = (ss.shapeType == "line");
  if (!isLine && ss.fillOpacity > 0.f) {
    SkPaint fillPaint;
    fillPaint.setStyle(SkPaint::kFill_Style);
    fillPaint.setColor4f(
        {ss.fillR, ss.fillG, ss.fillB, ss.fillA * ss.fillOpacity * opacity});
    fillPaint.setAntiAlias(true);
    canvas->drawPath(path, fillPaint);
  }

  //   Stroke
  if (ss.strokeWidth > 0.f) {
    SkPaint strokePaint;
    strokePaint.setStyle(SkPaint::kStroke_Style);
    strokePaint.setStrokeWidth(ss.strokeWidth);
    strokePaint.setColor4f(
        {ss.strokeR, ss.strokeG, ss.strokeB, ss.strokeA * opacity});
    strokePaint.setAntiAlias(true);
    canvas->drawPath(path, strokePaint);
  }

  canvas->restore();
}

} // namespace fade::drawing
