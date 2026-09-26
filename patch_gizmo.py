import re

with open("src/workspaces/viewport/TransformGizmo.tsx", "r", encoding="utf-8") as f:
    content = f.read()

# I will write the new SVG rendering part manually.
# First, let's locate the return statement.
idx = content.find("  return (\n    <svg")
if idx == -1:
    print("Could not find SVG return")

# We need to add hover state hooks and svgScale hook.
hooks = """
  const [svgScale, setSvgScale] = useState(1);
  const [hoveredHandle, setHoveredHandle] = useState<string | null>(null);

  useEffect(() => {
    if (!svgRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (let entry of entries) {
        setSvgScale(1920 / entry.contentRect.width);
      }
    });
    observer.observe(svgRef.current);
    return () => observer.disconnect();
  }, []);
"""

content = content.replace("  const [mode, setMode] = useState<'normal' | 'crop'>('normal');", "  const [mode, setMode] = useState<'normal' | 'crop'>('normal');\n" + hooks)

# Edge handles in visual corners calculation:
edgeCalc = """
  const edgeMidpoints = [
    { x: (vCorners[0].x + vCorners[1].x) / 2, y: (vCorners[0].y + vCorners[1].y) / 2 },
    { x: (vCorners[1].x + vCorners[2].x) / 2, y: (vCorners[1].y + vCorners[2].y) / 2 },
    { x: (vCorners[2].x + vCorners[3].x) / 2, y: (vCorners[2].y + vCorners[3].y) / 2 },
    { x: (vCorners[3].x + vCorners[0].x) / 2, y: (vCorners[3].y + vCorners[0].y) / 2 },
  ];
  
  const cropPath = `M0,0 L1920,0 L1920,1080 L0,1080 Z M${vCorners[0].x},${vCorners[0].y} L${vCorners[3].x},${vCorners[3].y} L${vCorners[2].x},${vCorners[2].y} L${vCorners[1].x},${vCorners[1].y} Z`;
"""

# add edgeCalc before rotHandle
content = content.replace("  const rotHandle = ", edgeCalc + "\n  const rotHandle = ")

# Fix resize math to handle edges
resizeMath = """
    else if (dragType?.startsWith('resize_')) {
       const isEdge = dragType.includes('edge');
       const index = parseInt(dragType.split('_').pop()!, 10);
       const oppIndex = (index + 2) % 4;
       
       const startLocalCorners = [
         { x: init.localMinX + init.cropL * init.imgW, y: init.localMinY + init.cropT * init.imgH },
         { x: init.localMaxX - init.cropR * init.imgW, y: init.localMinY + init.cropT * init.imgH },
         { x: init.localMaxX - init.cropR * init.imgW, y: init.localMaxY - init.cropB * init.imgH },
         { x: init.localMinX + init.cropL * init.imgW, y: init.localMaxY - init.cropB * init.imgH }
       ];
       
       let dragLocal = startLocalCorners[index];
       let oppLocal = startLocalCorners[oppIndex];
       
       if (isEdge) {
           dragLocal = { x: (startLocalCorners[index].x + startLocalCorners[(index+1)%4].x)/2, y: (startLocalCorners[index].y + startLocalCorners[(index+1)%4].y)/2 };
           oppLocal = { x: (startLocalCorners[oppIndex].x + startLocalCorners[(oppIndex+1)%4].x)/2, y: (startLocalCorners[oppIndex].y + startLocalCorners[(oppIndex+1)%4].y)/2 };
       }
       
       const curLocal = inverseApplyMatrix(pt);
       const dxDrag = dragLocal.x - oppLocal.x;
       const dyDrag = dragLocal.y - oppLocal.y;
       const dxCur = curLocal.x - oppLocal.x;
       const dyCur = curLocal.y - oppLocal.y;
       
       if (isEdge) {
           if (index === 0 || index === 2) { // Top or Bottom -> scale Y
               if (Math.abs(dyDrag) > 0.01) next.sy = init.sy * (dyCur / dyDrag);
           } else { // Left or Right -> scale X
               if (Math.abs(dxDrag) > 0.01) next.sx = init.sx * (dxCur / dxDrag);
           }
       } else {
           let scaleFactor = 1;
           if (Math.abs(dxDrag) > Math.abs(dyDrag) && Math.abs(dxDrag) > 0.01) scaleFactor = dxCur / dxDrag;
           else if (Math.abs(dyDrag) > 0.01) scaleFactor = dyCur / dyDrag;
           next.sx = init.sx * scaleFactor;
           next.sy = init.sy * scaleFactor;
       }
       
       const calcWorld = (lPt: {x: number, y: number}, state: any) => {
          let nx = lPt.x - state.ax; let ny = lPt.y - state.ay;
          nx *= state.sx; ny *= state.sy;
          const r = state.rot * Math.PI / 180;
          const cx = Math.cos(r); const sx = Math.sin(r);
          return {
             x: nx * cx - ny * sx + state.ax + state.px,
             y: nx * sx + ny * cx + state.ay + state.py
          };
       };
       
       const oldW = calcWorld(oppLocal, init);
       const newW = calcWorld(oppLocal, next);
       next.px += (oldW.x - newW.x);
       next.py += (oldW.y - newW.y);
    }
"""
content = re.sub(r"else if \(dragType\?\.startsWith\('resize_'\)\) \{.*?const oldW = calcWorld\(oppLocal, init\);\s*const newW = calcWorld\(oppLocal, next\);\s*next\.px \+= \(oldW\.x - newW\.x\);\s*next\.py \+= \(oldW\.y - newW\.y\);\s*\}", resizeMath.strip(), content, flags=re.DOTALL)

with open("patch_gizmo.py", "w", encoding="utf-8") as f:
    f.write(repr(content))

print("Step 1 done")
