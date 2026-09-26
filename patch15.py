import re

with open('renderer/src/HeadlessCompositor.cpp', 'r', encoding='utf-8') as f:
    content = f.read()

# We need to find the transform block.
# Let's use regex to replace it exactly.
pattern = r"const auto &t = clip\.transform;[\s\S]*?(?=// videoClip\.py)"

new_code = '''const auto &t = clip.transform;
    float cx = m_width * 0.5f + t.anchorX;
    float cy = m_height * 0.5f + t.anchorY;
    
    // 1. Position
    canvas->translate(t.x, t.y);
    
    // 2. Pivot
    canvas->translate(cx, cy);
    
    // 3. Rotate & Scale
    canvas->rotate(t.rotation);
    canvas->scale(t.scaleX, t.scaleY);
    
    // 4. Un-pivot
    canvas->translate(-cx, -cy);
  
    // 5. Letterbox (pad & scale to fit 1920x1080).
    // Because this happens AFTER un-pivoting, the padding is applied in the unrotated object space.
    // This perfectly aligns the center of the letterboxed image to (960, 540).
    if (imgW != m_width || imgH != m_height) {
      float scale =
          std::min(static_cast<float>(m_width) / static_cast<float>(imgW),
                   static_cast<float>(m_height) / static_cast<float>(imgH));
      float padX = (static_cast<float>(m_width) - imgW * scale) * 0.5f;
      float padY = (static_cast<float>(m_height) - imgH * scale) * 0.5f;
      canvas->translate(padX, padY);
      canvas->scale(scale, scale);
    }
  
    '''

content = re.sub(pattern, new_code, content)

with open('renderer/src/HeadlessCompositor.cpp', 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched HeadlessCompositor.cpp order of operations")
