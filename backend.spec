# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import (
    collect_all, collect_data_files, collect_submodules, get_package_paths,
)

ROOT = Path(SPECPATH)


def _collect(*packages):
    """collect_all() for several packages; a package that is not installed is skipped."""
    datas, binaries, hidden = [], [], []
    for pkg in packages:
        try:
            d, b, h = collect_all(pkg)
        except Exception as exc:
            print(f'[backend.spec] WARNING: could not collect {pkg!r}: {exc}')
            continue
        print(f'[backend.spec] {pkg}: {len(d)} data, {len(b)} binaries, {len(h)} modules')
        datas += d
        binaries += b
        hidden += h
    return datas, binaries, hidden


# Packages that load native libraries or data files at runtime from their own
# folder. PyInstaller only follows `import` statements, so without this their
# Python code is bundled but the files they open are not, and the feature fails
# only in the packaged app:
#   kokoro_onnx      config.json (phoneme vocabulary)            -> TTS
#   espeakng_loader  espeak-ng.dll + espeak-ng-data/             -> TTS phonemizer
#   phonemizer       language data                               -> TTS phonemizer
#   mediapipe        native bindings + .tflite/.binarypb models  -> face detection
#   whisper          mel filters + tokenizer assets              -> transcription
#   faster_whisper   silero VAD model                            -> transcription
#   reportlab        fonts                                       -> PDF export
#   pdfplumber/pdfminer  used by the prompt-injection shield (loaded via sys.path)
NATIVE_AND_DATA_PACKAGES = [
    'chromadb', 'fastembed', 'av',
    'kokoro_onnx', 'espeakng_loader', 'phonemizer',
    'mediapipe',
    'whisper', 'faster_whisper',
    'reportlab', 'pdfplumber', 'pdfminer',
]
pkg_datas, pkg_binaries, pkg_hiddenimports = _collect(*NATIVE_AND_DATA_PACKAGES)


def _torchvision_binaries():
    """torchvision loads its C extensions (NMS, image codecs) by file name, not by
    import, so they have to be listed explicitly."""
    try:
        pkg_dir = Path(get_package_paths('torchvision')[1])
    except Exception as exc:
        print(f'[backend.spec] WARNING: torchvision not found: {exc}')
        return []
    files = sorted(list(pkg_dir.glob('*.pyd')) + list(pkg_dir.glob('*.dll')))
    print(f'[backend.spec] torchvision: {len(files)} native files')
    return [(str(f), 'torchvision') for f in files]


def _backend_modules():
    """Every module under backend/, discovered from disk so a new file can never be
    forgotten. Tests are left out."""
    mods = set()
    for py in (ROOT / 'backend').rglob('*.py'):
        parts = list(py.relative_to(ROOT).with_suffix('').parts)
        if 'tests' in parts or '__pycache__' in parts:
            continue
        if parts[-1] == '__init__':
            parts = parts[:-1]
        mods.add('.'.join(parts))
    return sorted(mods)


BACKEND_MODULES = _backend_modules()
print(f'[backend.spec] backend modules: {len(BACKEND_MODULES)}')

hiddenimports = (
    BACKEND_MODULES +
    pkg_hiddenimports +
    collect_submodules('uvicorn') + collect_submodules('fastapi') +
    collect_submodules('starlette') + collect_submodules('pydantic') +
    collect_submodules('langchain') + collect_submodules('langchain_core') +
    collect_submodules('langchain_community') + collect_submodules('langchain_openai') +
    collect_submodules('openai') + collect_submodules('anthropic') +
    collect_submodules('httpx') + collect_submodules('aiohttp') +
    collect_submodules('aiofiles') + collect_submodules('PIL') +
    collect_submodules('skia') + collect_submodules('cv2') +
    collect_submodules('numpy') + collect_submodules('imagehash') +
    collect_submodules('cryptography') + collect_submodules('multiprocessing') +
    [
        'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan', 'uvicorn.lifespan.on',
    ]
)

datas = (
    pkg_datas +
    collect_data_files('skia') +
    [
        # SKSL shaders
        (str(ROOT / 'backend' / 'timeline' / 'effects' / 'sksl'), 'backend/timeline/effects/sksl'),
        # AI skills
        (str(ROOT / 'backend' / 'ai' / 'skills'), 'backend/ai/skills'),
        # pii
        (str(ROOT / 'pii'), 'pii'),
        # templates
        (str(ROOT / 'templates'), 'templates'),
    ]
)

# Prompt-injection shield: backend/ai/prompt_shield.py adds
# <root>/cyberSecurityRepos/injection_shield to sys.path and imports src.shield.*
_shield_src = ROOT / 'cyberSecurityRepos' / 'injection_shield' / 'src'
if _shield_src.is_dir():
    datas.append((str(_shield_src), 'cyberSecurityRepos/injection_shield/src'))
else:
    print('[backend.spec] WARNING: injection_shield/src not found - prompt shield will be disabled')

binaries = pkg_binaries + _torchvision_binaries()

a = Analysis(
    [str(ROOT / 'backend' / 'main.py')],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # scipy and matplotlib must NOT be excluded: easyocr, scikit-learn and
    # scikit-image import scipy at module level, imagehash.phash needs
    # scipy.fftpack, and mediapipe's drawing utils import matplotlib.
    excludes=['tkinter', 'IPython'],
    # Ship our own backend package as plain .py files in _internal/backend instead
    # of inside the compiled archive. PyInstaller always prefers the archive, so
    # with the default mode the loose .py copies that build_full.ps1 overlays (and
    # that hotfix_deploy.ps1 updates) were never executed - a "hotfix" had no
    # effect. backend/main.py itself is the entry script and still needs a rebuild.
    module_collection_mode={'backend': 'py'},
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='backend', debug=False,
    bootloader_ignore_signals=False,
    strip=False, upx=False, console=True,
    disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None,
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, upx_exclude=[],
    name='backend',
)
