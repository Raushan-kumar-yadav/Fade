path = 'renderer/src/rendering/DrawText.cpp'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_block_1 = '''  const auto &t = clip.transform;
  const float cx = static_cast<float>(canvasW) * 0.5f + t.anchorX;
  const float cy = static_cast<float>(canvasH) * 0.5f + t.anchorY;

  SkM44 model = SkM44::Translate(t.x + cx, t.y + cy, 0.f);
  model.preConcat(SkM44::Rotate({0, 0, 1}, t.rotation * (SK_ScalarPI / 180.f)));
  model.preConcat(SkM44::Scale(t.scaleX, t.scaleY, 1.f));
  model.preConcat(SkM44::Translate(-cx, -cy, 0.f));'''

new_block_1 = '''  const auto &t = clip.transform;
  SkM44 model = fade::drawing::getCanonicalMatrix(t);'''

old_block_2 = '''  const float originX = static_cast<float>(canvasW) * 0.5f;
  const float originY =
      static_cast<float>(canvasH) * 0.5f - totalH * 0.5f + ts.fontSize;'''

new_block_2 = '''  // Local object origin is (0,0) center
  const float originX = 0.0f;
  const float originY = 0.0f - totalH * 0.5f + ts.fontSize;'''

if old_block_1 in content:
    content = content.replace(old_block_1, new_block_1)
    content = content.replace(old_block_2, new_block_2)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched DrawText.cpp")
else:
    print("Failed to patch DrawText.cpp")
