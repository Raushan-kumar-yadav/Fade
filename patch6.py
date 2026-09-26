import re

with open('src/workspaces/viewport/TransformGizmo.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the image/video size logic
old_logic = '''  } else if (clip.type === 'image' || clip.type === 'video') {
    const scale = Math.min(1920 / baseWidth, 1080 / baseHeight);
    imgW = baseWidth * scale;
    imgH = baseHeight * scale;
    localMinX = 0;
    localMinY = 0;
    localMaxX = localMinX + imgW;
    localMaxY = localMinY + imgH;
  }'''

new_logic = '''  } else if (clip.type === 'image' || clip.type === 'video') {
    // FADE's C++ renderer draws images at their exact native pixel resolution (1:1).
    // It does NOT apply any automatic object-fit scaling.
    imgW = baseWidth;
    imgH = baseHeight;
    localMinX = 0;
    localMinY = 0;
    localMaxX = imgW;
    localMaxY = imgH;
  }'''

if old_logic in content:
    content = content.replace(old_logic, new_logic)
else:
    print("Could not find the exact old logic block. Writing robust regex...")
    content = re.sub(
        r"\} else if \(clip\.type === 'image' \|\| clip\.type === 'video'\) \{.*?localMaxY = localMinY \+ imgH;\s*\}",
        new_logic,
        content,
        flags=re.DOTALL
    )

with open('src/workspaces/viewport/TransformGizmo.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print("Applied native pixel resolution patch.")
