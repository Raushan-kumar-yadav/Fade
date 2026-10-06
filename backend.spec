# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = Path(SPECPATH)

chroma_datas,  chroma_binaries,  chroma_hiddenimports  = collect_all('chromadb')
fastembed_datas, fastembed_binaries, fastembed_hiddenimports = collect_all('fastembed')
av_datas, av_binaries, av_hiddenimports = collect_all('av')

# ALL backend modules listed explicitly so PyInstaller never misses one
BACKEND_MODULES = [
    'backend', 'backend.__init__', 'backend._root', 'backend.events',
    'backend.serializers', 'backend.state', 'backend.main', 'backend.fix_comps',
    'backend.ai', 'backend.ai.__init__', 'backend.ai.VideoSemantic',
    'backend.ai.VideoSemantic.__init__', 'backend.ai.VideoSemantic.descriptions',
    'backend.ai.VideoSemantic.frameExtractor', 'backend.ai.VideoSemantic.indexer',
    'backend.ai.VideoSemantic.merger', 'backend.ai.agent', 'backend.ai.agent_jobs',
    'backend.ai.agent_registry', 'backend.ai.bg_remove_tools', 'backend.ai.director',
    'backend.ai.intent_classifier', 'backend.ai.mcp_client', 'backend.ai.mcp_server',
    'backend.ai.plan_tools', 'backend.ai.planner', 'backend.ai.platform_presets',
    'backend.ai.prompt_shield', 'backend.ai.publish_tools', 'backend.ai.router',
    'backend.ai.skill_executor', 'backend.ai.skill_loader', 'backend.ai.skill_tools',
    'backend.ai.task_queue', 'backend.ai.task_router', 'backend.ai.task_store',
    'backend.ai.tool_sets', 'backend.ai.tools', 'backend.ai.tracking_tools',
    'backend.ai.video_pipeline', 'backend.ai.video_pipeline.__init__',
    'backend.ai.video_pipeline.asset_gatherer', 'backend.ai.video_pipeline.news_search',
    'backend.ai.video_pipeline.pipeline', 'backend.ai.video_pipeline.scene_planner',
    'backend.ai.video_pipeline.schema', 'backend.ai.video_pipeline.timeline_builder',
    'backend.ai.whisper_tool',
    'backend.animation', 'backend.animation.__init__', 'backend.animation.animPath',
    'backend.animation.anim_debug', 'backend.animation.animatableProperty',
    'backend.animation.curve_presets', 'backend.animation.expression_context',
    'backend.animation.keyframe', 'backend.animation.scalarTrack',
    'backend.animation.transform',
    'backend.api', 'backend.api.__init__', 'backend.api.api',
    'backend.audio', 'backend.audio.__init__', 'backend.audio.mixer',
    'backend.bg_remove', 'backend.bg_remove.__init__', 'backend.bg_remove.service',
    'backend.compositor', 'backend.compositor.__init__', 'backend.compositor.compositor',
    'backend.compositor.renderPipeline',
    'backend.config.global_config',
    'backend.decoder', 'backend.decoder.__init__', 'backend.decoder.decoder',
    'backend.editor_tools.commands', 'backend.editor_tools.state',
    'backend.editor_tools.transform_utils',
    'backend.encoder', 'backend.encoder.__init__', 'backend.encoder.encoder',
    'backend.engine', 'backend.engine.__init__', 'backend.engine.engine',
    'backend.history', 'backend.history.__init__', 'backend.history.commandStack',
    'backend.integrity', 'backend.integrity.__init__', 'backend.integrity.echo_integrity',
    'backend.integrity.perceptual', 'backend.integrity.router',
    'backend.integrity.service', 'backend.integrity.watermark',
    'backend.media', 'backend.media.__init__', 'backend.media.asset',
    'backend.media.asset.__init__', 'backend.media.asset.baseAsset',
    'backend.media.asset.mediaAsset', 'backend.media.asset.webCompAsset',
    'backend.media.cache', 'backend.media.cache.__init__', 'backend.media.cache.frameCache',
    'backend.media.decoder', 'backend.media.decoder.__init__',
    'backend.media.decoder.baseDecoder', 'backend.media.decoder.decodedFrame',
    'backend.media.decoder.decoderPool', 'backend.media.decoder.ffmpegDecoder',
    'backend.media.decoder.imageDecoder', 'backend.media.decoder.videoDecoder',
    'backend.media.decoderavDecoder', 'backend.media.scheduler',
    'backend.media.scheduler.__init__', 'backend.media.scheduler.decodeScheduler',
    'backend.pii', 'backend.pii.__init__', 'backend.pii.detector',
    'backend.pii.sanitizer', 'backend.pii.security',
    'backend.project', 'backend.project.__init__', 'backend.project.project',
    'backend.renderer', 'backend.renderer.__init__', 'backend.renderer.skiaRenderer',
    'backend.rendering', 'backend.rendering.__init__', 'backend.rendering.graph',
    'backend.rendering.graph.__init__', 'backend.rendering.graph.baseNode',
    'backend.rendering.graph.clipNode', 'backend.rendering.graph.effectNode',
    'backend.rendering.graph.graphBuilder', 'backend.rendering.graph.mergeNode',
    'backend.rendering.graph.outputNode', 'backend.rendering.graph.renderGraph',
    'backend.rendering.nodes', 'backend.rendering.nodes.__init__',
    'backend.rendering.nodes.effectNode', 'backend.rendering.nodes.maskNode',
    'backend.rendering.nodes.penNode', 'backend.rendering.nodes.shapeNode',
    'backend.rendering.nodes.textNode', 'backend.rendering.renderContext',
    'backend.routers', 'backend.routers.__init__', 'backend.routers.animation',
    'backend.routers.audio', 'backend.routers.audio_tools', 'backend.routers.bg_remove_',
    'backend.routers.clips', 'backend.routers.comps', 'backend.routers.context',
    'backend.routers.debug', 'backend.routers.effects', 'backend.routers.export_',
    'backend.routers.image_tools', 'backend.routers.integrations', 'backend.routers.jobs',
    'backend.routers.library', 'backend.routers.mcp_remote_router',
    'backend.routers.pdf_export', 'backend.routers.pii', 'backend.routers.playback',
    'backend.routers.project', 'backend.routers.render', 'backend.routers.scene_tools',
    'backend.routers.search', 'backend.routers.timeline', 'backend.routers.transitions',
    'backend.routers.virality',
    'backend.serializers', 'backend.state',
    'backend.timeline', 'backend.timeline.__init__', 'backend.timeline.clips',
    'backend.timeline.clips.__init__', 'backend.timeline.clips.animEngine',
    'backend.timeline.clips.audioClip', 'backend.timeline.clips.baseClip',
    'backend.timeline.clips.compClip', 'backend.timeline.clips.imageClip',
    'backend.timeline.clips.penClip', 'backend.timeline.clips.shapeClip',
    'backend.timeline.clips.svgClip', 'backend.timeline.clips.textClip',
    'backend.timeline.clips.videoClip', 'backend.timeline.clips.webComp',
    'backend.timeline.effects', 'backend.timeline.effects.__init__',
    'backend.timeline.effects.baseEffect', 'backend.timeline.effects.effects',
    'backend.timeline.effects.skslEffect', 'backend.timeline.timeline',
    'backend.timeline.tracks', 'backend.timeline.tracks.__init__',
    'backend.timeline.tracks.audioTrack', 'backend.timeline.tracks.baseTrack',
    'backend.timeline.tracks.imageLayer', 'backend.timeline.tracks.videoTrack',
    'backend.timeline.transitions', 'backend.timeline.transitions.__init__',
    'backend.timeline.transitions.transition',
    'backend.tools', 'backend.tools.__init__', 'backend.tools.downloader',
    'backend.tools.downloader.__init__', 'backend.tools.downloader.image_downloader',
    'backend.tools.downloader.ytdlp_downloader', 'backend.tools.generators',
    'backend.tools.generators.__init__', 'backend.tools.generators.comfyui_generator',
    'backend.tools.generators.image_generator', 'backend.tools.generators.stability_generator',
    'backend.tools.generators.tts_generator', 'backend.tools.generators.video_generator',
    'backend.tracking', 'backend.tracking.__init__', 'backend.tracking.detector',
    'backend.tracking.jobs', 'backend.tracking.router', 'backend.tracking.service',
    'backend.tracking.tracker',
    'backend.worker', 'backend.worker.__init__', 'backend.worker.index_cache',
    'backend.worker.sandbox_worker', 'backend.worker.transcript_status',
    'backend.worker.waveform_cache', 'backend.worker.worker_bus',
]

hiddenimports = (
    BACKEND_MODULES +
    chroma_hiddenimports + fastembed_hiddenimports + av_hiddenimports +
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
    chroma_datas + fastembed_datas + av_datas +
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

binaries = chroma_binaries + av_binaries

a = Analysis(
    [str(ROOT / 'backend' / 'main.py')],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'IPython'],
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
