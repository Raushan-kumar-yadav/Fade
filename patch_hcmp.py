with open('renderer/src/HeadlessCompositor.cpp', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('#include "rendering/DrawText.hpp"', '#include "rendering/DrawText.hpp"\n#include "rendering/TransformHelper.hpp"')

old_block = '''  const auto &t = clip.transform;
  float cx = t.anchorX * m_width;
  float cy = t.anchorY * m_height;
  canvas->translate(t.x + cx, t.y + cy);
  canvas->rotate(t.rotation);
  canvas->scale(t.scaleX, t.scaleY);
  canvas->translate(-cx, -cy);

  // Scale decoded image to fit canvas
  if (imgW != m_width || imgH != m_height) {
    float scale =
        std::min(static_cast<float>(m_width) / static_cast<float>(imgW),
                 static_cast<float>(m_height) / static_cast<float>(imgH));
    float padX = (static_cast<float>(m_width) - imgW * scale) * 0.5f;
    float padY = (static_cast<float>(m_height) - imgH * scale) * 0.5f;
    canvas->translate(padX, padY);
    canvas->scale(scale, scale);
  }'''

new_block = '''  const auto &t = clip.transform;
  fade::drawing::applyCanonicalTransform(canvas, t);

  // Scale decoded image to fit canvas bounds
  // FADE CANONICAL MODEL: Draw centered around (0,0) in local space
  float scale = 1.0f;
  if (imgW > 0 && imgH > 0) {
    scale = std::min(static_cast<float>(m_width) / static_cast<float>(imgW),
                     static_cast<float>(m_height) / static_cast<float>(imgH));
  }
  float drawW = static_cast<float>(imgW) * scale;
  float drawH = static_cast<float>(imgH) * scale;
  
  float padX = -drawW * 0.5f;
  float padY = -drawH * 0.5f;
  
  canvas->translate(padX, padY);
  canvas->scale(scale, scale);'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open('renderer/src/HeadlessCompositor.cpp', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched HeadlessCompositor.cpp")
else:
    print("Could not find old block in HeadlessCompositor.cpp")
