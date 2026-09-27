import os
for file in ['DrawShape.cpp', 'DrawPen.cpp', 'DrawSvg.cpp', 'DrawText.cpp']:
    path = f'renderer/src/rendering/{file}'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    if 'TransformHelper.hpp' not in content:
        content = '#include "TransformHelper.hpp"\n' + content
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Added TransformHelper to {file}")
