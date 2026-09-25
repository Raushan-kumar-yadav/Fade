import os

with open('src/workspaces/tools/ToolboxWidget.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

target = '''const CREATE_TOOLS: ToolDef[] = [
  { id: 'text',       icon: 'T',  label: 'Text',        shortcut: 'T', group: 'create' },
  { id: 'solid',      icon: '■',  label: 'Solid Color', shortcut: 'O', group: 'create' },
  { id: 'adjustment', icon: '⧔', label: 'Adjustment',  shortcut: 'A', group: 'create' },
];'''

# We will just split and insert since unicode characters can be tricky with replace
lines = text.split('\n')
for i, line in enumerate(lines):
    if "{ id: 'solid'," in line and "{ id: 'brush'" not in text:
        lines.insert(i+1, "  { id: 'brush',      icon: '🖌',  label: 'Brush',       shortcut: 'B', group: 'create' },")
        lines.insert(i+2, "  { id: 'eraser',     icon: '▤',  label: 'Eraser',      shortcut: 'E', group: 'create' },")
        break

text = '\n'.join(lines)

# Also update the shortcut handler
for i, line in enumerate(lines):
    if "t: 'text',    o: 'solid', a: 'adjustment'," in line and "b: 'brush'" not in text:
        lines[i] = "      t: 'text',    o: 'solid', a: 'adjustment', b: 'brush', e: 'eraser',"
        break

text = '\n'.join(lines)

with open('src/workspaces/tools/ToolboxWidget.tsx', 'w', encoding='utf-8') as f:
    f.write(text)
