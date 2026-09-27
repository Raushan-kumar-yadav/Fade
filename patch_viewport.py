import os
import re

path = 'src/workspaces/viewport/ViewportWidget.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Revert my bad patch if it applied
import re
content = re.sub(r'const arr = new Uint8Array\(buf\);.*?if \(buf\.byteLength < needed\) return;', 'if (buf.byteLength < needed) return;', content, flags=re.DOTALL)

patch = '''      const arr = new Uint8Array(buf);
      let firstNonZero = -1;
      for (let i = 0; i < arr.length; i++) {
          if (arr[i] !== 0) {
              firstNonZero = i;
              break;
          }
      }
      console.log([DIAGNOSTIC] ViewportWidget | isNativeRender: true | frame: {frameNum} | bufSize: {buf.byteLength} | expected: {needed} | firstNonZero: {firstNonZero});
      if (buf.byteLength < needed) return;'''

content = content.replace('if (buf.byteLength < needed) return;', patch)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched ViewportWidget.tsx")
