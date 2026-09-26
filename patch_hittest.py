import sys
with open('src/workspaces/viewport/TransformOverlay.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

search = """        let minX = -960, maxX = 960, minY = -540, maxY = 540;
        if (c.type === 'image' || c.type === 'video' || c.type === 'solid') {
            minX = 0; maxX = 1920;
            minY = 0; maxY = 1080;
        } else if (c.shape) {
            minX = -c.shape.width / 2;
            maxX = c.shape.width / 2;
            minY = -c.shape.height / 2;
            maxY = c.shape.height / 2;
        }"""

replacement = """        let minX = 0, maxX = 1920, minY = 0, maxY = 1080;
        if (c.type === 'image' || c.type === 'video') {
            const bw = c.baseWidth || 1920;
            const bh = c.baseHeight || 1080;
            const scale = Math.min(1920 / bw, 1080 / bh);
            const w = bw * scale;
            const h = bh * scale;
            minX = (1920 - w) / 2;
            maxX = minX + w;
            minY = (1080 - h) / 2;
            maxY = minY + h;
        } else if (c.type === 'solid') {
            minX = 0; maxX = 1920; minY = 0; maxY = 1080;
        } else if (c.baseWidth && c.baseHeight) {
            minX = -c.baseWidth / 2;
            maxX = c.baseWidth / 2;
            minY = -c.baseHeight / 2;
            maxY = c.baseHeight / 2;
        }"""

content = content.replace(search.replace('\r\n','\n'), replacement.replace('\r\n','\n'))

with open('src/workspaces/viewport/TransformOverlay.tsx', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print('Updated hit-test bounds!')
