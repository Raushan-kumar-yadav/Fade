import re

with open('src/workspaces/viewport/TransformGizmo.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update getParam to flip pos_x
old_getParam = '''  const getParam = (id: string, defaultVal: number) => {
    const row = params.find(r => r.id === id);
    return row !== undefined ? row.value : defaultVal;
  };'''

new_getParam = '''  const getParam = (id: string, defaultVal: number) => {
    const row = params.find(r => r.id === id);
    if (row !== undefined) {
      // FADE's C++ renderer has an inverted X axis for position.
      // We flip it here so all internal Gizmo math remains standard (+X = Right).
      if (id === 'pos_x') return -row.value;
      return row.value;
    }
    return defaultVal;
  };'''

content = content.replace(old_getParam, new_getParam)

# 2. Update updateOrAdd to flip pos_x back when saving to state
old_updateOrAdd = '''        updateOrAdd('pos_x', next.px);'''
new_updateOrAdd = '''        updateOrAdd('pos_x', -next.px);'''
content = content.replace(old_updateOrAdd, new_updateOrAdd)

# 3. Update inspectorApi.setParam to flip pos_x
old_setParam = '''    inspectorApi.setParam(selected.clipId, 'pos_x', next.px);'''
new_setParam = '''    inspectorApi.setParam(selected.clipId, 'pos_x', -next.px);'''
content = content.replace(old_setParam, new_setParam)

# 4. Update finalParams in handlePointerUp to flip pos_x
old_finalParams = '''    const finalParams = {
      pos_x: getParam('pos_x', init.px), pos_y: getParam('pos_y', init.py),'''
new_finalParams = '''    const finalParams = {
      pos_x: -getParam('pos_x', init.px), pos_y: getParam('pos_y', init.py),'''
content = content.replace(old_finalParams, new_finalParams)

with open('src/workspaces/viewport/TransformGizmo.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print("Applied inverted X-axis patch")
