import os
import re

with open('src/context/toolContext.ts', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace(
    "| 'solid'         // O  - add solid/color clip",
    "| 'solid'         // O  - add solid/color clip\n    | 'brush'         // B  - brush tool\n    | 'eraser'        // E  - eraser tool"
)

text = text.replace(
    "export function isCreationTool(tool: ActiveTool): boolean {\n  return !isEditTool(tool);\n}",
    "export function isCreationTool(tool: ActiveTool): boolean {\n  return !isEditTool(tool);\n}\n\nexport function isImageTool(tool: ActiveTool): boolean {\n  return ['brush', 'eraser'].includes(tool);\n}"
)

text = text.replace(
    "ripple:         'col-resize',",
    "ripple:         'col-resize',\n    brush:          'crosshair',\n    eraser:         'crosshair',"
)

with open('src/context/toolContext.ts', 'w', encoding='utf-8') as f:
    f.write(text)
