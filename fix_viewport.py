import os

path = 'src/workspaces/viewport/ViewportWidget.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the broken console.log line with a working one
old_line = "console.log([DIAGNOSTIC] ViewportWidget | isNativeRender: true | frame: {frameNum} | bufSize: {buf.byteLength} | expected: {needed} | firstNonZero: {firstNonZero});"
new_line = "console.log([DIAGNOSTIC] ViewportWidget | isNativeRender: true | frame:  | bufSize:  | expected:  | firstNonZero: );"

content = content.replace(old_line, new_line)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed ViewportWidget syntax")
