import os

path = 'electron/main.ts'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''  function loadRenderEngine(): void {
    const resRoot     = getResourcesRoot()
    const addonPath   = path.join(resRoot, 'renderer', 'build', 'Release', 'render_engine.node')
    const releaseBinDir = path.join(resRoot, 'renderer', 'build', 'Release')
  
    if (!fs.existsSync(addonPath)) {
      console.log('[RenderEngine] Native addon not found at', addonPath, '?" using Python compositor fallback')
      return
    }'''

new_block = '''  function loadRenderEngine(): void {
    const resRoot     = getResourcesRoot()
    const addonPath   = path.join(resRoot, 'renderer', 'build', 'Release', 'render_engine.node')
    const releaseBinDir = path.join(resRoot, 'renderer', 'build', 'Release')
    
    console.log('[DIAGNOSTIC] Resolving addonPath:', addonPath);
    if (fs.existsSync(addonPath)) {
        console.log('[DIAGNOSTIC] File size:', fs.statSync(addonPath).size, 'bytes');
    }

    if (!fs.existsSync(addonPath)) {
      console.log('[RenderEngine] Native addon not found at', addonPath, '?" using Python compositor fallback')
      return
    }'''

old_try = '''  try {
      
    renderEngine = require(addonPath) as RenderEngine
    console.log('[RenderEngine] Native addon loaded successfully')
  } catch (e) {
    console.error('[RenderEngine] Failed to load native addon:', e)
    renderEngine = null
  }'''

new_try = '''  try {
    renderEngine = require(addonPath) as RenderEngine
    console.log('[DIAGNOSTIC] Native addon loaded successfully')
  } catch (e) {
    console.error('[DIAGNOSTIC] Failed to load native addon:', e)
    renderEngine = null
  }'''

content = content.replace(old_block, new_block).replace(old_try, new_try)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched electron/main.ts")
