import os

path = 'backend/routers/render.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# I messed up the indentation. Let's fix it manually.
# In python:
content = content.replace('''      print(f"[FRAME] << frame={frame} | clips={len(result['clips'])} | dt={1000*(time.perf_counter()-_t0):.1f}ms", flush=True)
      img_clips = [c for c in result.get("clips", []) if c.get("type") == "image"]
      if img_clips:
          c = img_clips[0]
          t = c.get("transform", {})
          print(f"[DIAGNOSTIC] Python serialized ImageClip: file={c.get('file')} type={c.get('type')} x={t.get('x')} y={t.get('y')} scaleX={t.get('scaleX')} scaleY={t.get('scaleY')} rotation={t.get('rotation')} anchorX={t.get('anchorX')} anchorY={t.get('anchorY')}")''',
'''    print(f"[FRAME] << frame={frame} | clips={len(result['clips'])} | dt={1000*(time.perf_counter()-_t0):.1f}ms", flush=True)
    img_clips = [c for c in result.get("clips", []) if c.get("type") == "image"]
    if img_clips:
        c = img_clips[0]
        t = c.get("transform", {})
        print(f"[DIAGNOSTIC] Python serialized ImageClip: file={c.get('file')} type={c.get('type')} x={t.get('x')} y={t.get('y')} scaleX={t.get('scaleX')} scaleY={t.get('scaleY')} rotation={t.get('rotation')} anchorX={t.get('anchorX')} anchorY={t.get('anchorY')}")''')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed indentation")
