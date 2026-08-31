 

export interface AudioClipInfo {
  clipId: string
  assetId: string
  startFrame:  number
  duration: number
  mediaOffset: number   // frames into the media where clip starts
  volume: number
  streamUrl: string
}

interface AudioNode {
  el:   HTMLAudioElement
  clip: AudioClipInfo
}

export class AudioEngine {
  private nodes: Map<string, AudioNode> = new Map()
  private fps   = 30
  private port  = 8000
  private _playing = false
  private _rate   = 1.0

  constructor(fps: number, port: number) {
    this.fps  = fps
    this.port = port
  }

  setFps(fps: number) { this.fps = fps }

  /** Update the backend port   */
  updatePort(port: number) {
    if (this.port === port) return
    this.port = port
    for (const [, node] of this.nodes) {
      node.el.src = `http://127.0.0.1:${port}${node.clip.streamUrl}`
    }
  }

  /** Set playback speed   */
  setRate(rate: number) {
    this._rate = rate
    for (const { el } of this.nodes.values()) {
      el.playbackRate = rate
    }
  }

 
  update(clips: AudioClipInfo[]) {
    const incoming = new Set(clips.map(c => c.clipId))

    // Remove stale nodes  
    for (const [id, node] of this.nodes) {
      if (!incoming.has(id)) {
        ;(node.el as any)._fade_dead = true
        node.el.pause()
        node.el.src = ''
        this.nodes.delete(id)
      }
    }

    // Add / update
    for (const clip of clips) {
       
      if (!this.port) continue

      const expectedSrc = `http://127.0.0.1:${this.port}${clip.streamUrl}`
      if (!this.nodes.has(clip.clipId)) {
        const el = new Audio()
        el.src     = expectedSrc
        el.preload = 'auto'
        el.volume  = Math.max(0, Math.min(1, clip.volume))
         
        el.addEventListener('error', () => {
           
          if ((el as any)._fade_dead) return
          console.error('[AudioEngine] load error', clip.clipId, clip.streamUrl, el.error)
        })
        el.addEventListener('canplaythrough', () => {
          console.log('[AudioEngine] ready', clip.clipId, clip.streamUrl)
        })
        this.nodes.set(clip.clipId, { el, clip })
        console.log('[AudioEngine] added clip', clip.clipId, 'src=', el.src)
      } else {
      
        const node = this.nodes.get(clip.clipId)!
        node.clip  = clip
        node.el.volume = Math.max(0, Math.min(1, clip.volume))
        if (node.el.src !== expectedSrc) {
          node.el.src = expectedSrc
          console.log('[AudioEngine] updated src for', clip.clipId, '->', expectedSrc)
        }
      }
    }
  }

 
  seek(frame: number) {
    for (const { el, clip } of this.nodes.values()) {
      const clipRelFrame = frame - clip.startFrame
      if (clipRelFrame < 0 || clipRelFrame >= clip.duration) {
        if (!el.paused) el.pause()
        continue   
      }
      const targetSec = (clipRelFrame + clip.mediaOffset) / this.fps
      if (Math.abs(el.currentTime - targetSec) > 0.1) {
        el.currentTime = targetSec
      }
    }
  }

 
  play(frame: number) {
    this._playing = true
    for (const { el, clip } of this.nodes.values()) {
      const clipRelFrame = frame - clip.startFrame
      if (clipRelFrame >= 0 && clipRelFrame < clip.duration) {
        const targetSec = (clipRelFrame + clip.mediaOffset) / this.fps
        if (Math.abs(el.currentTime - targetSec) > 0.15) {
          el.currentTime = targetSec
        }
        el.playbackRate = this._rate
        el.play().catch(e => console.warn('[AudioEngine] play rejected', clip.clipId, e.message))
      }
    }
  }

  /** Pause all audio. */
  pause() {
    this._playing = false
    for (const { el } of this.nodes.values()) {
      if (!el.paused) el.pause()
    }
  }

 
  tick(frame: number) {
    if (!this._playing) return
    for (const { el, clip } of this.nodes.values()) {
      const clipRelFrame = frame - clip.startFrame
      const inRange = clipRelFrame >= 0 && clipRelFrame < clip.duration

      if (inRange) {
        const targetSec = (clipRelFrame + clip.mediaOffset) / this.fps
        // Drift correction threshold scales with playback rate
        const driftThreshold = 0.2 / Math.max(0.1, this._rate)
        if (Math.abs(el.currentTime - targetSec) > driftThreshold) {
          el.currentTime = targetSec
        }
        if (el.playbackRate !== this._rate) el.playbackRate = this._rate
        if (el.paused) {
          el.play().catch(e => console.warn('[AudioEngine] tick play rejected', clip.clipId, e.message))
        }
      } else {
        if (!el.paused) el.pause()
      }
    }
  }

  destroy() {
    for (const { el } of this.nodes.values()) {
      ;(el as any)._fade_dead = true
      el.pause()
      el.src = ''
    }
    this.nodes.clear()
  }
}
