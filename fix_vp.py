import os
import re

path = 'src/workspaces/viewport/ViewportWidget.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

bad_line = "console.log([DIAGNOSTIC] ViewportWidget | isNativeRender: true | frame:  | bufSize:  | expected:  | firstNonZero: );"
good_line = "console.log([DIAGNOSTIC] ViewportWidget | isNativeRender: true | frame:  | bufSize:  | expected:  | firstNonZero: );"

content = content.replace(bad_line, good_line)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed ViewportWidget")
