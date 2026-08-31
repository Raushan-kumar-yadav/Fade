import { useState, useEffect, useCallback, useRef } from 'react'
import './HomeWorkspace.css'

const PORT = () => (window as any).__FADE_PORT__ ?? 8000
const api = (path: string, opts?: RequestInit) =>
  fetch(`http://127.0.0.1:${PORT()}${path}`, opts)

//   Types  

interface UserProfile {
  id: number; name: string; email: string; bio: string; avatar: string
}

interface Connection {
  platform: string; connected: number; access_token: string
  channel_id: string; channel_name: string
}

interface YTVideo {
  videoId: string; title: string; thumbUrl: string; publishedAt: string
  views: number; likes: number; comments: number; duration: string
  category: string; baselineViews: number; platform: string
}

interface AnalysisResult {
  scores: { quality: number; text: number; virality: number }
  analysis: string
}

//   ScoreRing  

function ScoreRing({ value, label, color }: { value: number; label: string; color: string }) {
  const r = 28; const circ = 2 * Math.PI * r
  return (
    <div className="score-ring">
      <svg width={72} height={72} viewBox="0 0 72 72">
        <circle cx={36} cy={36} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={5} />
        <circle cx={36} cy={36} r={r} fill="none" stroke={color} strokeWidth={5}
          strokeDasharray={`${(value / 100) * circ} ${circ}`}
          strokeDashoffset={circ * 0.25}
          strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 1s cubic-bezier(0.34,1.56,0.64,1)' }}
        />
        <text x={36} y={40} textAnchor="middle" fill={color} fontSize={14} fontWeight={700}>{value}</text>
      </svg>
      <span className="score-ring__label">{label}</span>
    </div>
  )
}

//   VideoCard  

function fmtNum(n: number) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

function parseDuration(iso: string) {
  const m = iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/)
  if (!m) return '—'
  const h = parseInt(m[1] ?? '0'), mn = parseInt(m[2] ?? '0'), s = parseInt(m[3] ?? '0')
  return h ? `${h}:${String(mn).padStart(2,'0')}:${String(s).padStart(2,'0')}` : `${mn}:${String(s).padStart(2,'0')}`
}

interface VideoCardProps {
  video: YTVideo
  result?: AnalysisResult
  loading?: boolean
  onAnalyze: (v: YTVideo) => void
}

function VideoCard({ video, result, loading, onAnalyze }: VideoCardProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={`hw-vcard${result ? ' hw-vcard--analyzed' : ''}`}>
      <div className="hw-vcard__thumb">
        <img src={video.thumbUrl || `https://picsum.photos/seed/${video.videoId}/320/180`} alt={video.title} />
        <span className="hw-vcard__dur">{parseDuration(video.duration)}</span>
        {result && (
          <div className="hw-vcard__score-overlay">
            <span className="hw-vcard__viral" style={{
              color: result.scores.virality >= 52 ? '#00d4aa' : result.scores.virality >= 48 ? '#ffd60a' : '#ff6584'
            }}>
              {result.scores.virality >= 52 ? '🚀 High' : result.scores.virality >= 48 ? '📊 Avg' : '📉 Low'}
            </span>
          </div>
        )}
      </div>
      <div className="hw-vcard__body">
        <h3 className="hw-vcard__title" title={video.title}>{video.title}</h3>
        <div className="hw-vcard__meta">
          <span>👁 {fmtNum(video.views)}</span>
          <span>♥ {fmtNum(video.likes)}</span>
          <span>💬 {fmtNum(video.comments)}</span>
        </div>

        {result && (
          <div className="hw-vcard__scores">
            <ScoreRing value={result.scores.quality}  label="Visual"  color="#6c63ff" />
            <ScoreRing value={result.scores.text}     label="Title"   color="#00d4aa" />
            <ScoreRing value={result.scores.virality} label="Viral"   color="#ffd60a" />
          </div>
        )}

        {result && (
          <div className="hw-vcard__analysis">
            <button className="hw-vcard__toggle" onClick={() => setExpanded(e => !e)}>
              {expanded ? '▲ Hide Analysis' : '▼ Show AI Analysis'}
            </button>
            {expanded && (
              <div className="hw-vcard__md">
                {result.analysis.split('\n').map((line, i) => (
                  <p key={i} className={
                    line.startsWith('##') ? 'hw-md-h2' :
                    line.startsWith('**') ? 'hw-md-bold' : 'hw-md-p'
                  }>
                    {line.replace(/\*\*/g, '')}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}

        <button
          className={`hw-vcard__btn${loading ? ' hw-vcard__btn--loading' : ''}`}
          onClick={() => onAnalyze(video)}
          disabled={loading}
        >
          {loading ? <span className="hw-spinner" /> : ''}
          {loading ? 'Analyzing…' : result ? 'Re-Analyze →' : 'Analyze →'}
        </button>
      </div>
    </div>
  )
}

//   Profile Modal  

interface ProfileModalProps { onClose: () => void }

function ProfileModal({ onClose }: ProfileModalProps) {
  const [tab, setTab] = useState<'info' | 'connections'>('info')
  const [profile, setProfile] = useState<UserProfile>({ id: 1, name: '', email: '', bio: '', avatar: '' })
  const [connections, setConnections] = useState<Record<string, Connection>>({})
  const [saving, setSaving] = useState(false)
  const [saveOk, setSaveOk] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const PORT = () => (window as any).__FADE_PORT__ ?? 8000

  useEffect(() => {
    api('/virality/profile').then(r => r.json()).then(d => setProfile(p => ({ ...p, ...d }))).catch(() => {})
    api('/virality/connections').then(r => r.json()).then(setConnections).catch(() => {})
  }, [])

  const handleSaveProfile = async () => {
    setSaving(true)
    try {
      await api('/virality/profile', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profile),
      })
      setSaveOk(true); setTimeout(() => setSaveOk(false), 2000)
    } finally { setSaving(false) }
  }

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return
    const reader = new FileReader()
    reader.onload = ev => setProfile(p => ({ ...p, avatar: ev.target?.result as string }))
    reader.readAsDataURL(file)
  }

  const [ytQuickMode, setYtQuickMode] = useState(false)
  const [ytApiKey, setYtApiKey]       = useState('')
  const [ytHandle, setYtHandle]       = useState('')
  const [ytConnecting, setYtConnecting] = useState(false)

  const connectYoutubeQuick = async () => {
    if (!ytApiKey.trim() || !ytHandle.trim()) {
      alert('Please enter both your YouTube API key and channel handle.')
      return
    }
    setYtConnecting(true)
    try {
      const res = await api('/virality/youtube/quick-connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: ytApiKey.trim(), channel_id: ytHandle.trim() }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail ?? 'Connection failed')
      const updated = await api('/virality/connections').then(r => r.json())
      setConnections(updated)
      setYtQuickMode(false)
    } catch (e: any) {
      alert(`Connect failed: ${e.message}`)
    } finally {
      setYtConnecting(false)
    }
  }

  const connectYoutube = async () => {
    try {
      const res = await api('/virality/youtube/auth-url').then(r => r.json())
      if (res.error || !res.url) {
        // No OAuth configured  
        setYtQuickMode(true)
        return
      }
      if ((window as any).electronAPI?.openExternal) {
        await (window as any).electronAPI.openExternal(res.url)
      } else {
        window.open(res.url, '_blank')
      }
    } catch {
      setYtQuickMode(true)
    }
  }

  const connectInstagram = () => {
    const igUrl = 'https://api.instagram.com/oauth/authorize?' + new URLSearchParams({
      client_id: (window as any).__IG_CLIENT_ID__ ?? 'YOUR_IG_APP_ID',
      redirect_uri: 'http://localhost:9999/ig-callback',
      scope: 'user_profile,user_media',
      response_type: 'code',
    }).toString()
    if ((window as any).electronAPI?.openExternal) {
      (window as any).electronAPI.openExternal(igUrl)
    } else {
      window.open(igUrl, '_blank')
    }
  }

  const disconnect = async (platform: string) => {
    await api(`/virality/connections/${platform}`, { method: 'DELETE' })
    const updated = await api('/virality/connections').then(r => r.json())
    setConnections(updated)
  }

  const yt = connections['youtube']
  const ig = connections['instagram']

  return (
    <div className="hw-modal-backdrop" onClick={onClose}>
      <div className="hw-modal" onClick={e => e.stopPropagation()}>
        <div className="hw-modal__header">
          <button
            className={`hw-modal__tab${tab === 'info' ? ' hw-modal__tab--active' : ''}`}
            onClick={() => setTab('info')}
          >👤 Profile</button>
          <button
            className={`hw-modal__tab${tab === 'connections' ? ' hw-modal__tab--active' : ''}`}
            onClick={() => setTab('connections')}
          >🔗 Connections</button>
          <button className="hw-modal__close" onClick={onClose}>✕</button>
        </div>

        {tab === 'info' && (
          <div className="hw-modal__body">
            {/* Avatar */}
            <div className="hw-profile__avatar-area" onClick={() => fileRef.current?.click()}>
              {profile.avatar
                ? <img src={profile.avatar} alt="avatar" className="hw-profile__avatar-img" />
                : <div className="hw-profile__avatar-placeholder">
                    {profile.name ? profile.name[0].toUpperCase() : '?'}
                  </div>
              }
              <span className="hw-profile__avatar-hint">Click to change</span>
            </div>
            <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleAvatarChange} />

            <div className="hw-form-group">
              <label>Display Name</label>
              <input
                className="hw-input"
                placeholder="Your name…"
                value={profile.name}
                onChange={e => setProfile(p => ({ ...p, name: e.target.value }))}
              />
            </div>
            <div className="hw-form-group">
              <label>Email</label>
              <input
                className="hw-input"
                placeholder="your@email.com"
                value={profile.email}
                onChange={e => setProfile(p => ({ ...p, email: e.target.value }))}
              />
            </div>
            <div className="hw-form-group">
              <label>Bio</label>
              <textarea
                className="hw-input hw-textarea"
                placeholder="A short bio about your channel…"
                rows={3}
                value={profile.bio}
                onChange={e => setProfile(p => ({ ...p, bio: e.target.value }))}
              />
            </div>
            <button
              className={`hw-btn-primary${saveOk ? ' hw-btn-primary--ok' : ''}`}
              onClick={handleSaveProfile}
              disabled={saving}
            >
              {saveOk ? '✓ Saved!' : saving ? 'Saving…' : 'Save Profile'}
            </button>
          </div>
        )}

        {tab === 'connections' && (
          <div className="hw-modal__body hw-connections">
            {/* YouTube */}
            <div className={`hw-conn-card hw-conn-card--yt${yt?.connected ? ' hw-conn-card--connected' : ''}`}
              style={{ flexDirection: 'column', alignItems: 'stretch', gap: 12 }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <div className="hw-conn-card__icon">
                  <svg viewBox="0 0 24 24" width={28} height={28} fill="currentColor">
                    <path d="M23.5 6.2s-.3-2-1.2-2.8c-1.1-1.2-2.4-1.2-3-1.3C16.8 2 12 2 12 2s-4.8 0-7.3.2c-.6.1-1.9.1-3 1.3C.8 4.2.5 6.2.5 6.2S.2 8.6.2 11v2.2c0 2.4.3 4.8.3 4.8s.3 2 1.2 2.8c1.1 1.2 2.6 1.2 3.3 1.2C7.2 22 12 22 12 22s4.8 0 7.3-.2c.6-.1 1.9-.1 3-1.3.9-.8 1.2-2.8 1.2-2.8s.3-2.4.3-4.8V11c0-2.4-.3-4.8-.3-4.8zM9.7 15.5V8.4l8.1 3.6-8.1 3.5z"/>
                  </svg>
                </div>
                <div className="hw-conn-card__info">
                  <div className="hw-conn-card__name">YouTube</div>
                  {yt?.connected
                    ? <div className="hw-conn-card__status hw-conn-card__status--ok">
                        ✓ Connected as <strong>{yt.channel_name || yt.channel_id}</strong>
                      </div>
                    : <div className="hw-conn-card__status">Not connected</div>
                  }
                </div>
                {yt?.connected
                  ? <button className="hw-conn-btn hw-conn-btn--disconnect" onClick={() => disconnect('youtube')}>Disconnect</button>
                  : !ytQuickMode
                    ? <button className="hw-conn-btn hw-conn-btn--connect" onClick={connectYoutube}>Connect →</button>
                    : null
                }
              </div>
              {/* Quick Connect inline form */}
              {!yt?.connected && ytQuickMode && (
                <div className="hw-quick-connect">
                  <p className="hw-quick-connect__label">
                    🔑 <strong>Quick Connect</strong> — paste your YouTube Data API key and channel handle
                  </p>
                  <input
                    className="hw-input"
                    placeholder="YouTube API Key (AIza…)"
                    type="password"
                    value={ytApiKey}
                    onChange={e => setYtApiKey(e.target.value)}
                  />
                  <input
                    className="hw-input"
                    placeholder="Channel Handle (@yourhandle or UCxxxxxxxx)"
                    value={ytHandle}
                    onChange={e => setYtHandle(e.target.value)}
                  />
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      className="hw-conn-btn hw-conn-btn--connect"
                      style={{ flex: 1 }}
                      onClick={connectYoutubeQuick}
                      disabled={ytConnecting}
                    >
                      {ytConnecting ? <span className="hw-spinner" style={{ width: 12, height: 12 }} /> : null}
                      {ytConnecting ? ' Connecting…' : '✓ Connect'}
                    </button>
                    <button className="hw-conn-btn hw-conn-btn--disconnect" onClick={() => setYtQuickMode(false)}>
                      Cancel
                    </button>
                  </div>
                  <p className="hw-conn-note" style={{ marginTop: 0 }}>
                    Get a free API key at <a href="#" style={{ color: '#a89bff' }}
                      onClick={e => { e.preventDefault(); (window as any).electronAPI?.openExternal?.('https://console.cloud.google.com/apis/library/youtube.googleapis.com') || window.open('https://console.cloud.google.com/apis/library/youtube.googleapis.com', '_blank') }}
                    >console.cloud.google.com</a> → YouTube Data API v3 → Create Credentials.
                  </p>
                </div>
              )}
            </div>

            {/* Instagram */}
            <div className={`hw-conn-card hw-conn-card--ig${ig?.connected ? ' hw-conn-card--connected' : ''}`}>
              <div className="hw-conn-card__icon hw-conn-card__icon--ig">
                <svg viewBox="0 0 24 24" width={28} height={28} fill="currentColor">
                  <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/>
                </svg>
              </div>
              <div className="hw-conn-card__info">
                <div className="hw-conn-card__name">Instagram</div>
                {ig?.connected
                  ? <div className="hw-conn-card__status hw-conn-card__status--ok">
                      ✓ Connected as <strong>{ig.channel_name || ig.channel_id}</strong>
                    </div>
                  : <div className="hw-conn-card__status">Not connected · coming soon</div>
                }
              </div>
              {ig?.connected
                ? <button className="hw-conn-btn hw-conn-btn--disconnect" onClick={() => disconnect('instagram')}>Disconnect</button>
                : <button className="hw-conn-btn" style={{ opacity: 0.4, cursor: 'not-allowed' }} disabled>Soon</button>
              }
            </div>

            <p className="hw-conn-note">
              ℹ️ For YouTube: get a Data API key from <strong>Google Cloud Console</strong> with <code>YouTube Data API v3</code> enabled.
              For full OAuth, set <code>YOUTUBE_CLIENT_ID</code> + <code>YOUTUBE_CLIENT_SECRET</code> env vars.
            </p>
          </div>
        )}

      </div>
    </div>
  )
}

// ── Analysis Modal ────────────────────────────────────────────────────────────

function AnalysisModal({ result, video, onClose }: {
  result: AnalysisResult; video: YTVideo; onClose: () => void
}) {
  return (
    <div className="hw-modal-backdrop" onClick={onClose}>
      <div className="hw-modal hw-modal--analysis" onClick={e => e.stopPropagation()}>
        <div className="hw-modal__header">
          <span className="hw-modal__title">🤖 AI Virality Analysis</span>
          <button className="hw-modal__close" onClick={onClose}>✕</button>
        </div>
        <div className="hw-modal__body">
          <div className="hw-analysis__video-info">
            <img src={video.thumbUrl} alt="" className="hw-analysis__thumb" />
            <div>
              <div className="hw-analysis__vtitle">{video.title}</div>
              <div className="hw-analysis__vmeta">
                {video.category} · {fmtNum(video.views)} views · {parseDuration(video.duration)}
              </div>
            </div>
          </div>
          <div className="hw-analysis__scores">
            <ScoreRing value={result.scores.quality}  label="Visual Quality"  color="#6c63ff" />
            <ScoreRing value={result.scores.text}     label="Title Strength"  color="#00d4aa" />
            <ScoreRing value={result.scores.virality} label="Viral Potential" color="#ffd60a" />
          </div>
          <div className="hw-analysis__content">
            {result.analysis.split('\n').filter(Boolean).map((line, i) => {
              if (line.startsWith('### ')) return <h3 key={i} className="hw-md-h3">{line.slice(4)}</h3>
              if (line.startsWith('## '))  return <h2 key={i} className="hw-md-h2">{line.slice(3)}</h2>
              if (line.startsWith('# '))   return <h1 key={i} className="hw-md-h1">{line.slice(2)}</h1>
              if (line.startsWith('**') && line.endsWith('**')) return <p key={i} className="hw-md-bold">{line.replace(/\*\*/g, '')}</p>
              if (line.startsWith('- ') || line.startsWith('* ')) return <li key={i} className="hw-md-li">{line.slice(2).replace(/\*\*/g, '')}</li>
              return <p key={i} className="hw-md-p">{line.replace(/\*\*/g, '')}</p>
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

//   HomeWorkspace  

interface HomeWorkspaceProps { onProjectCreated?: () => void }

export default function HomeWorkspace({ onProjectCreated: _ }: HomeWorkspaceProps) {
  const [showProfile, setShowProfile] = useState(false)
  const [profile, setProfile] = useState<UserProfile>({ id: 1, name: '', email: '', bio: '', avatar: '' })
  const [connections, setConnections] = useState<Record<string, Connection>>({})
  const [videos, setVideos] = useState<YTVideo[]>([])
  const [videosLoading, setVideosLoading] = useState(false)
  const [videosError, setVideosError] = useState('')
  const [analysisResults, setAnalysisResults] = useState<Record<string, AnalysisResult>>({})
  const [analyzingId, setAnalyzingId] = useState<string | null>(null)
  const [selectedAnalysis, setSelectedAnalysis] = useState<{ result: AnalysisResult; video: YTVideo } | null>(null)

  const loadProfile = useCallback(async () => {
    try {
      const p = await api('/virality/profile').then(r => r.json())
      setProfile(p)
    } catch {}
  }, [])

  const loadConnections = useCallback(async () => {
    try {
      const c = await api('/virality/connections').then(r => r.json())
      setConnections(c)
    } catch {}
  }, [])

  useEffect(() => {
    loadProfile(); loadConnections()
  }, [loadProfile, loadConnections])

  const loadVideos = useCallback(async () => {
    setVideosLoading(true); setVideosError('')
    try {
      const res = await api('/virality/youtube/videos')
      if (!res.ok) {
        const e = await res.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(e.detail ?? 'Failed to fetch videos')
      }
      const data = await res.json()
      setVideos(data.videos ?? [])
    } catch (e: any) {
      setVideosError(e.message ?? 'Failed to load videos')
    } finally {
      setVideosLoading(false)
    }
  }, [])

  const ytConnected = connections['youtube']?.connected

  useEffect(() => {
    if (ytConnected) loadVideos()
  }, [ytConnected, loadVideos])

  const handleAnalyze = useCallback(async (video: YTVideo) => {
    setAnalyzingId(video.videoId)
    try {
      const res = await api('/virality/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          videoId: video.videoId,
          title: video.title,
          thumbUrl: video.thumbUrl,
          platform: video.platform,
          category: video.category,
          baselineViews: video.baselineViews,
        }),
      })
      if (!res.ok) {
        const e = await res.json().catch(() => ({ detail: 'Model error' }))
        alert(`Analysis failed: ${e.detail}`)
        return
      }
      const result: AnalysisResult = await res.json()
      setAnalysisResults(prev => ({ ...prev, [video.videoId]: result }))
      setSelectedAnalysis({ result, video })
    } catch (e: any) {
      alert(`Analysis error: ${e.message}`)
    } finally {
      setAnalyzingId(null)
    }
  }, [])

  const ytConn = connections['youtube']
  const avgViral = Object.values(analysisResults).length
    ? Math.round(Object.values(analysisResults).reduce((s, r) => s + r.scores.virality, 0) / Object.values(analysisResults).length)
    : null

  const displayName = profile.name || 'Creator'
  const avatarLetter = displayName[0]?.toUpperCase() ?? '?'

  return (
    <div className="home-ws">
      {/* Header */}
      <div className="home-ws__header">
        <div>
          <h1 className="home-ws__title">
            Content Intelligence
            <span className="home-ws__title-badge">AI</span>
          </h1>
          <p className="home-ws__subtitle">Virality prediction · Channel analytics · AI insights</p>
        </div>
        <div className="home-ws__header-right">
          {ytConnected
            ? <button className="hw-refresh-btn" onClick={loadVideos} disabled={videosLoading} title="Refresh videos">
                {videosLoading ? <span className="hw-spinner" /> : '↻'}
              </button>
            : null
          }
          <div
            className="hw-avatar"
            title="Profile & Connections"
            onClick={() => { setShowProfile(true); loadConnections() }}
          >
            {profile.avatar
              ? <img src={profile.avatar} alt="avatar" />
              : <span>{avatarLetter}</span>
            }
            {ytConnected
              ? <span className="hw-avatar__badge hw-avatar__badge--yt" title="YouTube connected" />
              : null
            }
          </div>
        </div>
      </div>

      {/* Stats bar */}
      <div className="home-ws__stats">
        <div className="hw-stat">
          <span className="hw-stat__val" style={{ color: '#6c63ff' }}>{videos.length || '—'}</span>
          <span className="hw-stat__lbl">Videos</span>
        </div>
        <div className="hw-stat">
          <span className="hw-stat__val" style={{ color: '#00d4aa' }}>
            {avgViral !== null ? avgViral : '—'}
            <small>{avgViral !== null ? '/100' : ''}</small>
          </span>
          <span className="hw-stat__lbl">Avg Virality</span>
        </div>
        <div className="hw-stat">
          <span className="hw-stat__val" style={{ color: '#ffd60a' }}>{Object.keys(analysisResults).length || '—'}</span>
          <span className="hw-stat__lbl">Analyzed</span>
        </div>
        <div className="hw-stat">
          <span className="hw-stat__val" style={{ color: '#ff6584' }}>
            {ytConnected ? '🟢' : '⚫'}
          </span>
          <span className="hw-stat__lbl">YouTube</span>
        </div>
      </div>

      {/* Main content */}
      {!ytConnected ? (
        <div className="hw-connect-cta">
          <div className="hw-connect-cta__glow" />
          <div className="hw-connect-cta__icon">🎬</div>
          <h2>Connect Your Channel</h2>
          <p>Link your YouTube account to fetch your latest videos and run AI virality analysis on each one.</p>
          <button
            className="hw-btn-primary hw-btn-primary--large"
            onClick={() => setShowProfile(true)}
          >
            Connect YouTube →
          </button>
        </div>
      ) : videosLoading ? (
        <div className="hw-loading">
          <div className="hw-loading__spinner" />
          <span>Fetching your latest videos…</span>
        </div>
      ) : videosError ? (
        <div className="hw-error">
          <span>⚠️ {videosError}</span>
          <button className="hw-btn-ghost" onClick={loadVideos}>Retry</button>
        </div>
      ) : videos.length === 0 ? (
        <div className="hw-empty">No videos found on your channel.</div>
      ) : (
        <div className="home-ws__grid">
          {videos.map(v => (
            <VideoCard
              key={v.videoId}
              video={v}
              result={analysisResults[v.videoId]}
              loading={analyzingId === v.videoId}
              onAnalyze={handleAnalyze}
            />
          ))}
        </div>
      )}

      {/* Profile Modal */}
      {showProfile && (
        <ProfileModal onClose={() => { setShowProfile(false); loadProfile(); loadConnections() }} />
      )}

      {/* Analysis Detail Modal */}
      {selectedAnalysis && (
        <AnalysisModal
          result={selectedAnalysis.result}
          video={selectedAnalysis.video}
          onClose={() => setSelectedAnalysis(null)}
        />
      )}
    </div>
  )
}
