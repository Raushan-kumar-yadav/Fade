import re

with open('src/workspaces/viewport/TransformGizmo.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    'body: JSON.stringify({ clipId: selected.clipId, initialParams: init, finalParams: finalParams })',
    'body: JSON.stringify({ clip_id: selected.clipId, before: init, after: finalParams })'
)

content = content.replace(
    'initialParams: { rotation: rot },',
    'before: { rotation: rot },'
)

content = content.replace(
    'finalParams: { rotation: rot + 90 }',
    'after: { rotation: rot + 90 }'
)

content = content.replace(
    'clipId: selected.clipId,',
    'clip_id: selected.clipId,'
)

with open('src/workspaces/viewport/TransformGizmo.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched TransformGizmo.tsx body keys")
