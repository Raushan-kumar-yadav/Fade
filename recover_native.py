import os
import subprocess

files = [
    'renderer/build/Release/avcodec-61.dll',
    'renderer/build/Release/avdevice-61.dll',
    'renderer/build/Release/avfilter-10.dll',
    'renderer/build/Release/avformat-61.dll',
    'renderer/build/Release/avutil-59.dll',
    'renderer/build/Release/render_engine.node',
    'renderer/build/Release/swresample-5.dll',
    'renderer/build/Release/swscale-8.dll'
]

os.makedirs('renderer/build/Release', exist_ok=True)

for file in files:
    try:
        result = subprocess.run(['git', 'show', f'HEAD:{file}'], capture_output=True, check=True)
        with open(file, 'wb') as f:
            f.write(result.stdout)
        print(f"Recovered {file}")
    except Exception as e:
        print(f"Failed to recover {file}: {e}")
