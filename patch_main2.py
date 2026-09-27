import os

path = 'electron/main.ts'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

import re

# 1. Electron native loader
def repl_load(m):
    return '''  function loadRenderEngine(): void {
    const resRoot     = getResourcesRoot()
    const addonPath   = path.join(resRoot, 'renderer', 'build', 'Release', 'render_engine.node')
    const releaseBinDir = path.join(resRoot, 'renderer', 'build', 'Release')
  
    console.log('[DIAGNOSTIC] Resolving addonPath:', addonPath);
    if (fs.existsSync(addonPath)) {
        console.log('[DIAGNOSTIC] File size:', fs.statSync(addonPath).size, 'bytes');
    }

    if (!fs.existsSync(addonPath)) {'''

content = re.sub(r'  function loadRenderEngine\(\): void \{\s*const resRoot     = getResourcesRoot\(\)\s*const addonPath   = path\.join\(resRoot, \'renderer\', \'build\', \'Release\', \'render_engine\.node\'\)\s*const releaseBinDir = path\.join\(resRoot, \'renderer\', \'build\', \'Release\'\)\s*if \(!fs\.existsSync\(addonPath\)\) \{', repl_load, content)


def repl_try(m):
    return '''  try {
      
    renderEngine = require(addonPath) as RenderEngine
    console.log('[DIAGNOSTIC] Native addon loaded successfully')
  } catch (e) {
    console.error('[DIAGNOSTIC] Failed to load native addon:', e)
    renderEngine = null
  }'''

content = re.sub(r'  try \{\s*renderEngine = require\(addonPath\) as RenderEngine\s*console\.log\(\'\[RenderEngine\] Native addon loaded successfully\'\)\s*\} catch \(e\) \{\s*console\.error\(\'\[RenderEngine\] Failed to load native addon:\', e\)\s*renderEngine = null\s*\}', repl_try, content)

def repl_init(m):
    return '''    try {
      renderEngine.initialize(pw, ph, fps, effectsDir, pythonPort)
      renderEngine.setFrameReadyCallback(viewportFrameReadyCb)
      console.log('[DIAGNOSTIC] Initialized RenderEngine successfully.')
    } catch (e) {'''

content = re.sub(r'    try \{\s*renderEngine\.initialize\(pw, ph, fps, effectsDir, pythonPort\)\s*renderEngine\.setFrameReadyCallback\(viewportFrameReadyCb\)\s*console\.log\(\'\[RenderEngine\] Initialized .*?\'\)\s*\} catch \(e\) \{', repl_init, content)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched main.ts")
