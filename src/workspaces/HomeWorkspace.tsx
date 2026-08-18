import './HomeWorkspace.css'

interface Video {
  id: number
  title: string
  views: string
  likes: string
  duration: string
  score: number
  thumb: string
}

const MOCK_VIDEOS: Video[] = [
  { id: 1, title: 'Morning Routine That Changed My Life', views: '2.4M', likes: '142K', duration: '8:32',  score: 87, thumb: 'https://picsum.photos/seed/v1/320/180' },
  { id: 2, title: 'I Tested Every AI Tool in 2025', views: '1.1M', likes: '98K',  duration: '12:04', score: 74, thumb: 'https://picsum.photos/seed/v2/320/180' },
  { id: 3, title: 'Why This Short Went Viral Overnight', views: '8.7M', likes: '610K', duration: '0:58',  score: 95, thumb: 'https://picsum.photos/seed/v3/320/180' },
  { id: 4, title: 'Productivity System for Creators 2025', views: '540K', likes: '41K',  duration: '15:20', score: 61, thumb: 'https://picsum.photos/seed/v4/320/180' },
  { id: 5, title: 'The Perfect YouTube Thumbnail Formula', views: '920K', likes: '77K',  duration: '6:45',  score: 82, thumb: 'https://picsum.photos/seed/v5/320/180' },
  { id: 6, title: 'I Posted Every Day for 30 Days', views: '3.2M', likes: '228K', duration: '10:11', score: 90, thumb: 'https://picsum.photos/seed/v6/320/180' },
]

interface ScoreBadgeProps { score: number }

function ScoreBadge({ score }: ScoreBadgeProps) {
  const color = score >= 85 ? '#00d4aa' : score >= 65 ? '#FFD60A' : '#ff6584'
  return (
    <div className="score-badge">
      <svg width="36" height="36" viewBox="0 0 36 36">
        <circle cx="18" cy="18" r="15" fill="none" stroke="#2a2a2e" strokeWidth="3" />
        <circle cx="18" cy="18" r="15" fill="none" stroke={color} strokeWidth="3"
          strokeDasharray={`${score * 0.942} 94.2`}
          strokeDashoffset="23.55" strokeLinecap="round"
          style={{ transform: 'rotate(-90deg)', transformOrigin: '50% 50%' }}
        />
      </svg>
      <span style={{ color }}>{score}</span>
    </div>
  )
}

interface VideoCardProps { video: Video }

function VideoCard({ video }: VideoCardProps) {
  return (
    <div className="video-card">
      <div className="video-card__thumb">
        <img src={video.thumb} alt={video.title} />
        <span className="video-card__duration">{video.duration}</span>
        <ScoreBadge score={video.score} />
      </div>
      <div className="video-card__body">
        <h3 className="video-card__title">{video.title}</h3>
        <div className="video-card__meta">
          <span>👁 {video.views}</span>
          <span>♥ {video.likes}</span>
        </div>
        <div className="video-card__summary">
          AI: Strong hook in first 3s. Retention drop at 40%. Add pattern interrupt.
        </div>
        <button className="video-card__btn">Analyze →</button>
      </div>
    </div>
  )
}

interface Stat { label: string; value: string; unit: string; color: string }

const STATS: Stat[] = [
  { label: 'Avg Virality', value: '82', unit: '/100', color: '#00d4aa' },
  { label: 'Total Views', value: '16.9M', unit: '', color: '#6c63ff' },
  { label: 'Videos Indexed', value: '6', unit: '', color: '#ff6584' },
  { label: 'Trending Niche', value: 'AI', unit: '', color: '#FFD60A' },
]

export default function HomeWorkspace() {
  return (
    <div className="home-ws">
      <div className="home-ws__header">
        <div>
          <h1>Recent Videos</h1>
          <p>AI-powered analytics for your content</p>
        </div>
        <div className="home-ws__header-right">
          <button className="icon-btn" title="Settings">⚙</button>
          <div className="avatar" title="Profile">R</div>
        </div>
      </div>

      <div className="home-ws__stats">
        {STATS.map(({ label, value, unit, color }) => (
          <div className="stat-chip" key={label}>
            <span style={{ color, fontSize: 22, fontWeight: 700 }}>{value}<small>{unit}</small></span>
            <span>{label}</span>
          </div>
        ))}
      </div>

      <div className="home-ws__grid">
        {MOCK_VIDEOS.map(v => <VideoCard key={v.id} video={v} />)}
      </div>
    </div>
  )
}
