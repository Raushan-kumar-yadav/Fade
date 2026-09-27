path = 'renderer/src/rendering/DrawShape.cpp'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''  const auto &t = clip.transform;
  const float cx = static_cast<float>(canvasW) * 0.5f + t.anchorX;
  const float cy = static_cast<float>(canvasH) * 0.5f + t.anchorY;

  canvas->translate(t.x + cx, t.y + cy);
  canvas->rotate(t.rotation);
  canvas->scale(t.scaleX, t.scaleY);
  canvas->translate(-cx, -cy);

  float originX = static_cast<float>(canvasW) * 0.5f;
  float originY = static_cast<float>(canvasH) * 0.5f;'''

new_block = '''  const auto &t = clip.transform;
  fade::drawing::applyCanonicalTransform(canvas, t);

  float originX = 0.0f;
  float originY = 0.0f;'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched DrawShape.cpp")
else:
    print("Failed to patch DrawShape.cpp")
