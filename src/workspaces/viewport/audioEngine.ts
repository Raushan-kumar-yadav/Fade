
export interface AudioClipInfo {
  clipId: string
  assetId: string
  startFrame:  number
  duration: number
  mediaOffset: number  
  volume: number
  streamUrl: string
}

interface AudioNode {
  clip: AudioClipInfo
  buffer:  AudioBuffer | null  
  gainNode: GainNode
  source: AudioBufferSourceNode | null  
  loading: boolean
  dead: boolean
}

export class AudioEngine {
  private ctx: AudioContext | null = null
  private nodes:   Map<string, AudioNode> = new Map()
  private fps = 30
  private port = 8000
  private _playing = false
  private _rate    = 1.0
   
  private _playStartCtxTime = 0
  private _playStartFrame   = 0

  constructor(fps: number, port: number) {
    this.fps  = fps
    this.port = port
  }

  private _getCtx(): AudioContext {
    if (!this.ctx || this.ctx.state === 'closed') {
      this.ctx = new AudioContext()
    }
    return this.ctx
  }

  setFps(fps: number) { this.fps = fps }

  updatePort(port: number) {
    if (this.port === port) return
    this.port = port
 
    for (const [, node] of this.nodes) {
      if (!node.dead) this._fetchBuffer(node)
    }
  }

  setRate(rate: number) {
    this._rate = rate
    for (const [, node] of this.nodes) {
      if (node.source) node.source.playbackRate.value = rate
    }
  }

  // Fetch & decode  

  private async _fetchBuffer(node: AudioNode, attempt = 0) {
    if (node.loading || node.dead || !this.port) return
    node.loading = true
    const url = `http://127.0.0.1:${this.port}${node.clip.streamUrl}`
    try {
      const resp = await fetch(url)
      if (!resp.ok) throw new Error(`HTTP ${resp.status} (${resp.statusText})`)
      const arrayBuf = await resp.arrayBuffer()
      const ctx = this._getCtx()
      node.buffer = await ctx.decodeAudioData(arrayBuf)
      console.log('[AudioEngine] decoded', node.clip.clipId.slice(-6),
        `${node.buffer.duration.toFixed(1)}s`)
      if (this._playing) {
        this._startSource(node, this._currentFrame())
      }
    } catch (e) {
      const maxRetries = 3
      if (attempt < maxRetries && !node.dead) {
        const delay = Math.pow(2, attempt) * 2000  // 2s → 4s → 8s
        console.warn(`[AudioEngine] fetch failed (attempt ${attempt + 1}/${maxRetries}), retrying in ${delay}ms`, node.clip.clipId)
        node.loading = false
        setTimeout(() => this._fetchBuffer(node, attempt + 1), delay)
        return
      }
      console.warn('[AudioEngine] fetch/decode failed (giving up)', node.clip.clipId, e)
    } finally {
      node.loading = false
    }
  }

  // Update clip list  

  update(clips: AudioClipInfo[]) {
    const incoming = new Set(clips.map(c => c.clipId))

    // Remove stale
    for (const [id, node] of this.nodes) {
      if (!incoming.has(id)) {
        node.dead = true
        this._stopSource(node)
        this.nodes.delete(id)
      }
    }

    // Add / update
    for (const clip of clips) {
      if (!this.port) continue
      if (!this.nodes.has(clip.clipId)) {
        const ctx  = this._getCtx()
        const gain = ctx.createGain()
        gain.gain.value = Math.max(0, Math.min(1, clip.volume))
        gain.connect(ctx.destination)
        const node: AudioNode = {
          clip, buffer: null, gainNode: gain,
          source: null, loading: false, dead: false,
        }
        this.nodes.set(clip.clipId, node)
        this._fetchBuffer(node)
      } else {
        const node = this.nodes.get(clip.clipId)!
        const prevUrl = `http://127.0.0.1:${this.port}${node.clip.streamUrl}`
        const newUrl  = `http://127.0.0.1:${this.port}${clip.streamUrl}`
        node.clip = clip
        node.gainNode.gain.value = Math.max(0, Math.min(1, clip.volume))
        if (prevUrl !== newUrl) {
          node.buffer = null
          this._stopSource(node)
          this._fetchBuffer(node)
        }
      }
    }
  }

  // Playback control  

  seek(frame: number) {
    const ctx = this._getCtx()
    
    this._playStartCtxTime = ctx.currentTime
    this._playStartFrame   = frame
    if (this._playing) {
       
      for (const [, node] of this.nodes) {
        this._stopSource(node)
        this._startSource(node, frame)
      }
    }
  }

  play(frame: number) {
    this._playing = true
    const ctx = this._getCtx()
    if (ctx.state === 'suspended') ctx.resume()
    this._playStartCtxTime = ctx.currentTime
    this._playStartFrame   = frame
    for (const [, node] of this.nodes) {
      this._stopSource(node)
      this._startSource(node, frame)
    }
  }

  pause() {
    this._playing = false
    for (const [, node] of this.nodes) {
      this._stopSource(node)
    }
  }

  // tick() is called every frame  
  tick(_frame: number) {
    if (!this._playing) return
    for (const [, node] of this.nodes) {
       
      if (node.buffer && !node.source && !node.dead) {
        this._startSource(node, this._currentFrame())
      }
    }
  }

 
  syncToFrame(authoritative: number) {
    if (!this._playing) return
    const drift = Math.abs(this._currentFrame() - authoritative)
    if (drift > 1) {
      const ctx = this._getCtx()
      this._playStartCtxTime = ctx.currentTime
      this._playStartFrame   = authoritative
       
      for (const [, node] of this.nodes) {
        this._stopSource(node)
        this._startSource(node, authoritative)
      }
    }
  }

  // Internal  

  private _currentFrame(): number {
    if (!this._playing) return this._playStartFrame
    const ctx = this._getCtx()
    const elapsed = ctx.currentTime - this._playStartCtxTime
    return this._playStartFrame + elapsed * this.fps * this._rate
  }

  private _startSource(node: AudioNode, frame: number) {
    if (!node.buffer || node.dead) return
    const ctx = this._getCtx()
    const clip = node.clip
    const clipRelFrame = frame - clip.startFrame

 
    if (clipRelFrame >= clip.duration) return

    const offsetSec = Math.max(0,
      ((clipRelFrame < 0 ? 0 : clipRelFrame) + clip.mediaOffset) / this.fps
    )
 
    if (offsetSec >= node.buffer.duration) return

    
    let delayCtxTime = 0
    if (clipRelFrame < 0) {
      delayCtxTime = (-clipRelFrame) / (this.fps * this._rate)
    }

    const src = ctx.createBufferSource()
    src.buffer             = node.buffer
    src.playbackRate.value = this._rate
    src.connect(node.gainNode)

 
    const clipDurSec  = (clip.duration - Math.max(0, clipRelFrame)) / this.fps
    const bufRemainSec = node.buffer.duration - offsetSec
    const playDurSec  = Math.max(0, Math.min(clipDurSec, bufRemainSec))
    if (playDurSec <= 0) return

    src.start(ctx.currentTime + delayCtxTime, offsetSec, playDurSec)
    src.onended = () => { if (node.source === src) node.source = null }
    node.source = src
  }

  private _stopSource(node: AudioNode) {
    if (node.source) {
      try { node.source.stop() } catch {   }
      node.source = null
    }
  }

  destroy() {
    for (const [, node] of this.nodes) {
      node.dead = true
      this._stopSource(node)
      node.gainNode.disconnect()
    }
    this.nodes.clear()
    this.ctx?.close()
    this.ctx = null
  }
}
