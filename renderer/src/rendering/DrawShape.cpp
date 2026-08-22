#include "rendering/DrawShape.hpp"

#include <core/SkRRect.h>
#include <effects/SkMaskFilter.h>

#include <cmath>

namespace fade::drawing {

static constexpr float kPI = 3.14159265358979323846f;

//   Path builders

static SkPath buildRect(const ClipDesc::ShapeDesc &ss, float cx, float cy) {
  SkPath path;
  SkRect r = SkRect::MakeXYWH(cx - ss.width * 0.5f, cy - ss.height * 0.5f,
                              ss.width, ss.height);
  if (ss.cornerRadius > 0.f)
    path.addRoundRect(r, ss.cornerRadius, ss.cornerRadius);
  else
    path.addRect(r);
  return path;
}

static SkPath buildCircle(const ClipDesc::ShapeDesc &ss, float cx, float cy) {
  SkPath path;
  path.addCircle(cx, cy, ss.radiusX);
  return path;
}

static SkPath buildEllipse(const ClipDesc::ShapeDesc &ss, float cx, float cy) {
  SkPath path;
  path.addOval(SkRect::MakeXYWH(cx - ss.radiusX, cy - ss.radiusY,
                                ss.radiusX * 2.f, ss.radiusY * 2.f));
  return path;
}

static SkPath buildLine(const ClipDesc::ShapeDesc &ss, float cx, float cy) {
  SkPath path;
  path.moveTo(cx + ss.x1, cy + ss.y1);
  path.lineTo(cx + ss.x2, cy + ss.y2);
  return path;
}

static SkPath buildArc(const ClipDesc::ShapeDesc &ss, float cx, float cy) {
  SkPath path;
  SkRect oval = SkRect::MakeXYWH(cx - ss.arcRadius, cy - ss.arcRadius,
                                 ss.arcRadius * 2.f, ss.arcRadius * 2.f);
  path.addArc(oval, ss.arcStartAngle, ss.arcSweepAngle);
  return path;
}

// Regular N-sided polygon
static SkPath buildPolygon(const ClipDesc::ShapeDesc &ss, float cx, float cy) {
  SkPath path;
  const float step = 2.f * kPI / (float)ss.numSides;
  const float startAngle = -kPI * 0.5f;
  for (int i = 0; i < ss.numSides; ++i) {
    float a = startAngle + (float)i * step;
    float px = cx + ss.polygonRadius * std::cos(a);
    float py = cy + ss.polygonRadius * std::sin(a);
    if (i == 0)
      path.moveTo(px, py);
    else
      path.lineTo(px, py);
  }
  path.close();
  return path;
}

// N-pointed star
static SkPath buildStar(const ClipDesc::ShapeDesc &ss, float cx, float cy) {
  SkPath path;
  const int pts = ss.numPoints * 2;
  const float step = 2.f * kPI / (float)pts;
  const float startAngle = -kPI * 0.5f;
  for (int i = 0; i < pts; ++i) {
    float r = (i % 2 == 0) ? ss.outerRadius : ss.innerRadius;
    float a = startAngle + (float)i * step;
    float px = cx + r * std::cos(a);
    float py = cy + r * std::sin(a);
    if (i == 0)
      path.moveTo(px, py);
    else
      path.lineTo(px, py);
  }
  path.close();
  return path;
}

// Dispatch to the correct builder
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
  return SkPath{}; // unknown
}

// Public API

void drawShape(SkCanvas *canvas, const ClipDesc &clip, int canvasW,
               int canvasH) {
  const ClipDesc::ShapeDesc &ss = clip.shape;

  //   Apply clip transform
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

  // Shape origin defaults to canvas center
  const float cx = (float)canvasW * 0.5f;
  const float cy = (float)canvasH * 0.5f;

  //   Build path
  const SkPath path = buildPath(ss, cx, cy);

  //   Shadow pass
  if (ss.shadowEnabled) {
    const float rad = ss.shadowAngle * kPI / 180.f;
    const float dx = ss.shadowDistance * std::cos(rad);
    const float dy = ss.shadowDistance * std::sin(rad);

    SkPaint shadowPaint;
    shadowPaint.setColor4f(
        {ss.shadowR, ss.shadowG, ss.shadowB, ss.shadowA * clip.opacity});
    shadowPaint.setAntiAlias(true);
    shadowPaint.setStyle(SkPaint::kFill_Style);
    shadowPaint.setMaskFilter(
        SkMaskFilter::MakeBlur(kNormal_SkBlurStyle, ss.shadowBlur * 0.5f));

    canvas->save();
    canvas->translate(dx, dy);
    canvas->drawPath(path, shadowPaint);
    canvas->restore();
  }

  //   Fill pass

  const bool isLine = (ss.shapeType == "line");
  if (!isLine) {
    SkPaint fillPaint;
    fillPaint.setColor4f({ss.fillR, ss.fillG, ss.fillB,
                          ss.fillA * ss.fillOpacity * clip.opacity});
    fillPaint.setStyle(SkPaint::kFill_Style);
    fillPaint.setAntiAlias(true);
    canvas->drawPath(path, fillPaint);
  }

  //   Stroke pass
  if (ss.strokeWidth > 0.f) {
    SkPaint strokePaint;
    strokePaint.setColor4f(
        {ss.strokeR, ss.strokeG, ss.strokeB, ss.strokeA * clip.opacity});
    strokePaint.setStyle(SkPaint::kStroke_Style);
    strokePaint.setStrokeWidth(ss.strokeWidth);
    strokePaint.setStrokeCap(SkPaint::kRound_Cap);
    strokePaint.setStrokeJoin(SkPaint::kRound_Join);
    strokePaint.setAntiAlias(true);
    canvas->drawPath(path, strokePaint);
  }

  canvas->restore();
}

} // namespace fade::drawing
