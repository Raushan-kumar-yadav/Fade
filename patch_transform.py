import sys
with open('src/workspaces/viewport/TransformOverlay.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

search = """  const [assetWidth, setAssetWidth] = useState(1920);
  const [assetHeight, setAssetHeight] = useState(1080);"""

replacement = """  const [baseWidth, setBaseWidth] = useState(1920);
  const [baseHeight, setBaseHeight] = useState(1080);"""

content = content.replace(search, replacement)

search2 = """  useEffect(() => {
    if (!selected || selected.type !== 'clip') return;
    const clip = state.tracks.flatMap(t => t.clips).find(c => c.id === selected.clipId);
    if (!clip || clip.type !== 'image') return;
    
    if (clip.assetId) {
      fetch(`http://127.0.0.1:${(window as any).__FADE_PORT__ || 8000}/library/assets/rich`)
        .then(r => r.json())
        .then(assets => {
           const a = assets.find((x: any) => x.assetId === clip.assetId);
           if (a && a.width && a.height) {
             setAssetWidth(a.width);
             setAssetHeight(a.height);
           }
        })
        .catch(console.error);
    }
  }, [selected, state.tracks]);"""

replacement2 = """  useEffect(() => {
    if (!selected || selected.type !== 'clip' || activeTool !== 'pointer') return;
    // Fetch real base dimensions from render engine
    fetch(`http://127.0.0.1:${(window as any).__FADE_PORT__ || 8000}/render/frame/${currentFrame}`)
      .then(r => r.json())
      .then(data => {
         const c = data.clips.find((x: any) => x.clipId === selected.clipId);
         if (c && c.baseWidth && c.baseHeight) {
            setBaseWidth(c.baseWidth);
            setBaseHeight(c.baseHeight);
         }
      })
      .catch(console.error);
  }, [selected, currentFrame, activeTool]);"""

content = content.replace(search2.replace('\r\n','\n'), replacement2.replace('\r\n','\n'))

search3 = """  let boxW = 1920;
  let boxH = 1080;
  let localX = 0;
  let localY = 0;

  if (clip.type === 'shape') {
    boxW = getParam('shape_w', 200);
    boxH = getParam('shape_h', 120);
    localX = -boxW / 2;
    localY = -boxH / 2;
  } else if (clip.type === 'image') {
    // Letterbox calculation
    const scale = Math.min(1920 / assetWidth, 1080 / assetHeight);
    boxW = assetWidth * scale;
    boxH = assetHeight * scale;
    localX = (1920 - boxW) / 2;
    localY = (1080 - boxH) / 2;
  }"""

replacement3 = """  let boxW = 1920;
  let boxH = 1080;
  let localX = 0;
  let localY = 0;

  if (clip.type === 'shape') {
    boxW = getParam('shape_w', baseWidth);
    boxH = getParam('shape_h', baseHeight);
    localX = -boxW / 2;
    localY = -boxH / 2;
  } else if (clip.type === 'image' || clip.type === 'video') {
    // Letterbox calculation inside 1920x1080
    const scale = Math.min(1920 / baseWidth, 1080 / baseHeight);
    boxW = baseWidth * scale;
    boxH = baseHeight * scale;
    localX = (1920 - boxW) / 2;
    localY = (1080 - boxH) / 2;
  } else if (clip.type === 'solid') {
    boxW = 1920;
    boxH = 1080;
    localX = 0;
    localY = 0;
  }"""

content = content.replace(search3.replace('\r\n','\n'), replacement3.replace('\r\n','\n'))

with open('src/workspaces/viewport/TransformOverlay.tsx', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print('Updated TransformOverlay.tsx!')
