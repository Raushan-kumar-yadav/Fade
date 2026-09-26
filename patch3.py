import re

with open('src/workspaces/viewport/TransformGizmo.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

old_set_params = '''    setParams(prev => prev.map(p => {
      if (p.id === 'pos_x') return { ...p, value: next.px };
      if (p.id === 'pos_y') return { ...p, value: next.py };
      if (p.id === 'scale_x') return { ...p, value: next.sx };
      if (p.id === 'scale_y') return { ...p, value: next.sy };
      if (p.id === 'rotation') return { ...p, value: next.rot };
      if (p.id === 'cropLeft') return { ...p, value: next.cropL };
      if (p.id === 'cropRight') return { ...p, value: next.cropR };
      if (p.id === 'cropTop') return { ...p, value: next.cropT };
      if (p.id === 'cropBottom') return { ...p, value: next.cropB };
      return p;
    }));'''

new_set_params = '''    setParams(prev => {
      const nextParams = [...prev];
      const updateOrAdd = (id: string, value: number) => {
         const idx = nextParams.findIndex(p => p.id === id);
         if (idx >= 0) nextParams[idx] = { ...nextParams[idx], value };
         else nextParams.push({ id, value, type: 'number' } as any);
      };
      updateOrAdd('pos_x', next.px);
      updateOrAdd('pos_y', next.py);
      updateOrAdd('scale_x', next.sx);
      updateOrAdd('scale_y', next.sy);
      updateOrAdd('rotation', next.rot);
      updateOrAdd('cropLeft', next.cropL);
      updateOrAdd('cropRight', next.cropR);
      updateOrAdd('cropTop', next.cropT);
      updateOrAdd('cropBottom', next.cropB);
      return nextParams;
    });'''

content = content.replace(old_set_params, new_set_params)

with open('src/workspaces/viewport/TransformGizmo.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed setParams")
