import re

with open('renderer/src/HeadlessCompositor.cpp', 'r', encoding='utf-8') as f:
    content = f.read()

old_code = '''    const auto &t = clip.transform;
    float cx = t.anchorX * m_width;
    float cy = t.anchorY * m_height;
    canvas->translate(t.x + cx, t.y + cy);'''

new_code = '''    const auto &t = clip.transform;
    // CRITICAL FIX: Rotate around the center of the 1920x1080 composition by default!
    // FADE's t.anchorX/Y are absolute pixels. A value of 0 means "Center".
    float cx = m_width * 0.5f + t.anchorX;
    float cy = m_height * 0.5f + t.anchorY;
    canvas->translate(t.x + cx, t.y + cy);'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('renderer/src/HeadlessCompositor.cpp', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched HeadlessCompositor.cpp")
else:
    print("Could not find code block in HeadlessCompositor.cpp")
