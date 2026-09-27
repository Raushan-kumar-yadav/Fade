import os

path = 'electron/main.ts'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_init = '''    try {
      renderEngine.initialize(pw, ph, fps, effectsDir, pythonPort)
      renderEngine.setFrameReadyCallback(viewportFrameReadyCb)
      console.log('[RenderEngine] Initialized ?" effectsDir:', effectsDir, 'port:', pythonPort)
    } catch (e) {'''

new_init = '''    try {
      renderEngine.initialize(pw, ph, fps, effectsDir, pythonPort)
      renderEngine.setFrameReadyCallback(viewportFrameReadyCb)
      console.log('[DIAGNOSTIC] Initialized RenderEngine successfully.')
    } catch (e) {'''

content = content.replace(old_init, new_init)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched initRenderEngine")
