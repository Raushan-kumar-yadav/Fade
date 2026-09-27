#pragma once
#include <core/SkCanvas.h>
#include <core/SkM44.h>
#include "../napi/FrameDescriptor.hpp"

namespace fade {
namespace drawing {

inline void applyCanonicalTransform(SkCanvas* canvas, const ClipTransform& t) {
    canvas->translate(t.x, t.y);
    canvas->translate(t.anchorX, t.anchorY);
    canvas->rotate(t.rotation);
    canvas->scale(t.scaleX, t.scaleY);
    canvas->translate(-t.anchorX, -t.anchorY);
}

inline SkM44 getCanonicalMatrix(const ClipTransform& t) {
    SkM44 model = SkM44::Translate(t.x, t.y, 0.f);
    model.preConcat(SkM44::Translate(t.anchorX, t.anchorY, 0.f));
    model.preConcat(SkM44::Rotate({0, 0, 1}, t.rotation * (3.14159265358979323846f / 180.f)));
    model.preConcat(SkM44::Scale(t.scaleX, t.scaleY, 1.f));
    model.preConcat(SkM44::Translate(-t.anchorX, -t.anchorY, 0.f));
    return model;
}

} // namespace drawing
} // namespace fade
