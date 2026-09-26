import re

with open('renderer/src/HeadlessCompositor.cpp', 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(
    r"float cx = t\.anchorX \* m_width;\s*float cy = t\.anchorY \* m_height;",
    "float cx = m_width * 0.5f + t.anchorX;\n    float cy = m_height * 0.5f + t.anchorY;",
    content
)

with open('renderer/src/HeadlessCompositor.cpp', 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched HeadlessCompositor.cpp")
