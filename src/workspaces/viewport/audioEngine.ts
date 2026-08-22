/**
 * AudioEngine — manages HTMLAudioElement instances for all audio clips on the
 * timeline, keeping them in sync with the video playback frame clock.
 */

export interface AudioClipInfo {
  clipId:      string
  assetId:     string
  startFrame:  number
  duration:    number
  mediaOffset: number   // frames into the media where clip starts
  volume:      number
  streamUrl:   string
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

  /** Set playback speed (0.25, 0.5, 1.0, 2.0). Applied to all active audio elements. */
  setRate(rate: number) {
    this._rate = rate
    for (const { el } of this.nodes.values()) {
      el.playbackRate = rate
    }
  }

  /** Replace the full set of audio clips from the backend. */
  update(clips: AudioClipInfo[]) {
    const incoming = new Set(clips.map(c => c.clipId))

    // Remove stale nodes
    for (const [id, node] of this.nodes) {
      if (!incoming.has(id)) {
        node.el.pause()
        node.el.src = ''
        this.nodes.delete(id)
      }
    }

    // Add / update
    for (const clip of clips) {
      if (!this.nodes.has(clip.clipId)) {
        const el = new Audio()
        el.src           = `http://127.0.0.1:${this.port}${clip.streamUrl}`
        el.preload       = 'auto'
        el.volume        = Math.max(0, Math.min(1, clip.volume))
        el.crossOrigin   = 'anonymous'
        this.nodes.set(clip.clipId, { el, clip })
      } else {
        // Update volume if changed
        const node = this.nodes.get(clip.clipId)!
        node.clip  = clip
        node.el.volume = Math.max(0, Math.min(1, clip.volume))
      }
    }
  }

  /** Seek all audio elements to match the given timeline frame. */
  seek(frame: number) {
    for (const { el, clip } of this.nodes.values()) {
      const clipRelFrame = frame - clip.startFrame
      if (clipRelFrame < 0 || clipRelFrame >= clip.duration) {
        if (!el.paused) el.pause()
        continue  // was 'return' — must continue to seek remaining clips
      }
      const targetSec = (clipRelFrame + clip.mediaOffset) / this.fps
      if (Math.abs(el.currentTime - targetSec) > 0.1) {
        el.currentTime = targetSec
      }
    }
  }

  /** Start playback for clips that overlap the current frame. */
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
        el.play().catch(() => {})
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

  /** Called on every frame tick — start/stop clips that enter/exit range. */
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
          el.play().catch(() => {})
        }
      } else {
        if (!el.paused) el.pause()
      }
    }
  }

  destroy() {
    for (const { el } of this.nodes.values()) {
      el.pause()
      el.src = ''
    }
    this.nodes.clear()
  }
}
