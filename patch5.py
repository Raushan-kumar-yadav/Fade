import re

with open('src/workspaces/viewport/TransformGizmo.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Revert getParam inversion
old_getParam = '''  const getParam = (id: string, defaultVal: number) => {
    const row = params.find(r => r.id === id);
    if (row !== undefined) {
      // FADE's C++ renderer has an inverted X axis for position.
      // We flip it here so all internal Gizmo math remains standard (+X = Right).
      if (id === 'pos_x') return -row.value;
      return row.value;
    }
    return defaultVal;
  };'''

new_getParam = '''  const getParam = (id: string, defaultVal: number) => {
    const row = params.find(r => r.id === id);
    return row !== undefined ? row.value : defaultVal;
  };'''
content = content.replace(old_getParam, new_getParam)

# 2. Fix anchor_x/y (remove * 1920 and * 1080)
old_anchor = '''  const ax = getParam('anchor_x', 0.5) * 1920;
  const ay = getParam('anchor_y', 0.5) * 1080;'''
new_anchor = '''  const ax = getParam('anchor_x', 0);
  const ay = getParam('anchor_y', 0);'''
content = content.replace(old_anchor, new_anchor)

# 3. Fix localMinX/Y to 0
old_local = '''  } else if (clip.type === 'image' || clip.type === 'video') {
    const scale = Math.min(1920 / baseWidth, 1080 / baseHeight);
    imgW = baseWidth * scale;
    imgH = baseHeight * scale;
    localMinX = (1920 - imgW) / 2;
    localMinY = (1080 - imgH) / 2;'''
new_local = '''  } else if (clip.type === 'image' || clip.type === 'video') {
    const scale = Math.min(1920 / baseWidth, 1080 / baseHeight);
    imgW = baseWidth * scale;
    imgH = baseHeight * scale;
    localMinX = 0;
    localMinY = 0;'''
content = content.replace(old_local, new_local)

# 4. Revert setParam inversion
content = content.replace("updateOrAdd('pos_x', -next.px);", "updateOrAdd('pos_x', next.px);")
content = content.replace("inspectorApi.setParam(selected.clipId, 'pos_x', -next.px);", "inspectorApi.setParam(selected.clipId, 'pos_x', next.px);")
content = content.replace("pos_x: -getParam('pos_x', init.px),", "pos_x: getParam('pos_x', init.px),")

with open('src/workspaces/viewport/TransformGizmo.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print("Reverted inversion and fixed static geometry")
