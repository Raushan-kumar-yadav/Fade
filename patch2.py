with open('src/workspaces/viewport/TransformGizmo.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("http://127.0.0.1:/clips", "`http://127.0.0.1:${(window as any).__FADE_PORT__ || 8000}/clips")

with open('src/workspaces/viewport/TransformGizmo.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed fetch")
