import os
import glob
import re

files = glob.glob('renderer/src/rendering/*.cpp')
for fpath in files:
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Look for:
    # const float cx = t.anchorX * static_cast<float>(canvasW);
    # or
    # const float cx = t.anchorX * (float)canvasW;
    
    # We will replace them with:
    # const float cx = static_cast<float>(canvasW) * 0.5f + t.anchorX;
    
    old_code_1 = r"const float cx = t\.anchorX \* static_cast<float>\(canvasW\);\s*const float cy = t\.anchorY \* static_cast<float>\(canvasH\);"
    new_code_1 = "const float cx = static_cast<float>(canvasW) * 0.5f + t.anchorX;\n  const float cy = static_cast<float>(canvasH) * 0.5f + t.anchorY;"
    
    old_code_2 = r"const float cx = t\.anchorX \* \(float\)canvasW;\s*const float cy = t\.anchorY \* \(float\)canvasH;"
    new_code_2 = "const float cx = (float)canvasW * 0.5f + t.anchorX;\n  const float cy = (float)canvasH * 0.5f + t.anchorY;"

    content = re.sub(old_code_1, new_code_1, content)
    content = re.sub(old_code_2, new_code_2, content)

    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Patched {fpath}")
