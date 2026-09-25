import os

with open('src/context/toolContext.ts', 'r', encoding='utf-8') as f:
    text = f.read()

target = '''    // Creation tools
    | 'text'          // T  - add text clip
    | 'solid'         // O  - add solid/color clip'''

if "| 'solid'" in text and "| 'brush'" not in text:
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if "| 'solid'" in line:
            lines.insert(i+1, "    | 'brush'         // B  - brush tool")
            lines.insert(i+2, "    | 'eraser'        // E  - eraser tool")
            break
    text = '\n'.join(lines)

with open('src/context/toolContext.ts', 'w', encoding='utf-8') as f:
    f.write(text)
