import { useState, useEffect, useCallback } from 'react'
import {
  getFadeServerConfig,
  saveFadeServerConfig,
  pingServer,
  getBlockchainStatus,
  listArtifacts,
  getVerifyLog,
  verifyProof,
  type FadeServerConfig,
  type BlockchainStatus,
  type ArtifactRecord,
} from '../api/fadeServerApi'
import './FadeServerWorkspace.css'

export default function FadeServerWorkspace() {
  const [cfg, setCfg] = useState<FadeServerConfig>(getFadeServerConfig())
  const [draftUrl, setDraftUrl] = useState(cfg.baseUrl)
  const [draftKey, setDraftKey] = useState(cfg.apiKey)
  const [pingState, setPingState] = useState<'idle' | 'pinging' | 'ok' | 'error'>('idle')
  const [pingMsg, setPingMsg] = useState('')

  const [status, setStatus] = useState<BlockchainStatus | null>(null)
  const [statusErr, setStatusErr] = useState('')

  const [artifacts, setArtifacts] = useState<ArtifactRecord[]>([])
  const [artifactsErr, setArtifactsErr] = useState('')
  const [artifactsLoading, setArtifactsLoading] = useState(false)

  const [log, setLog] = useState<any[]>([])
  const [logLoading, setLogLoading] = useState(false)

  const [proofResult, setProofResult] = useState<any | null>(null)
  const [proofId, setProofId] = useState('')

  const [tab, setTab] = useState<'config' | 'artifacts' | 'log' | 'blockchain'>('config')

  const saveConfig = () => {
    const next = { baseUrl: draftUrl.replace(/\/$/, ''), apiKey: draftKey }
    setCfg(next)
    saveFadeServerConfig(next)
  }

  const ping = useCallback(async () => {
    const live = { baseUrl: draftUrl.replace(/\/$/, ''), apiKey: draftKey }
    setPingState('pinging')
    setPingMsg('')
    try {
      const r = await pingServer(live)
      setPingState('ok')
      setPingMsg(r.status ?? 'OK')
    } catch (e: any) {
      setPingState('error')
      setPingMsg(e.message)
    }
  }, [draftUrl, draftKey])

  const loadStatus = useCallback(async () => {
    setStatusErr('')
    try {
      const s = await getBlockchainStatus(cfg)
      setStatus(s)
    } catch (e: any) {
      setStatusErr(e.message)
    }
  }, [cfg])

  const loadArtifacts = useCallback(async () => {
    setArtifactsLoading(true)
    setArtifactsErr('')
    try {
      const { artifacts: list } = await listArtifacts(cfg)
      setArtifacts(list)
    } catch (e: any) {
      setArtifactsErr(e.message)
    } finally {
      setArtifactsLoading(false)
    }
  }, [cfg])

  const loadLog = useCallback(async () => {
    setLogLoading(true)
    try {
      const { log: rows } = await getVerifyLog(30, cfg)
      setLog(rows)
    } catch {}
    setLogLoading(false)
  }, [cfg])

  const loadProof = useCallback(async () => {
    if (!proofId.trim()) return
    setProofResult(null)
    try {
      const r = await verifyProof(proofId.trim(), cfg)
      setProofResult(r)
    } catch (e: any) {
      setProofResult({ error: e.message })
    }
  }, [proofId, cfg])

  useEffect(() => {
    if (tab === 'blockchain') loadStatus()
    if (tab === 'artifacts') loadArtifacts()
    if (tab === 'log') loadLog()
  }, [tab, loadStatus, loadArtifacts, loadLog])

  const ts = (unix: number) => new Date(unix * 1000).toLocaleString()

  return (
    <div className="fsw">
      <div className="fsw__header">
        <div className="fsw__logo">
          <span className="fsw__logo-icon">🛡️</span>
          <div>
            <div className="fsw__logo-title">Fade Server</div>
            <div className="fsw__logo-sub">Blockchain Verification Network</div>
          </div>
        </div>
        <div className="fsw__tabs">
          {(['config', 'blockchain', 'artifacts', 'log'] as const).map(t => (
            <button
              key={t}
              className={`fsw__tab${tab === t ? ' fsw__tab--active' : ''}`}
              onClick={() => setTab(t)}
            >
              {{ config: '⚙️ Config', blockchain: '⛓️ Blockchain', artifacts: '📦 Artifacts', log: '📋 Verify Log' }[t]}
            </button>
          ))}
        </div>
      </div>

      <div className="fsw__body">

        {/* CONFIG TAB */}
        {tab === 'config' && (
          <div className="fsw__section">
            <div className="fsw__card">
              <div className="fsw__card-title">🌐 Server Connection</div>
              <div className="fsw__field">
                <label>Backend URL</label>
                <input
                  className="fsw__input"
                  value={draftUrl}
                  onChange={e => setDraftUrl(e.target.value)}
                  placeholder="https://fade-web-backend.onrender.com"
                />
              </div>
              <div className="fsw__field">
                <label>API Key</label>
                <input
                  className="fsw__input"
                  type="password"
                  value={draftKey}
                  onChange={e => setDraftKey(e.target.value)}
                  placeholder="sih2026-fade-secret-key"
                />
              </div>
              <div className="fsw__btn-row">
                <button className="fsw__btn fsw__btn--primary" onClick={saveConfig}>
                  💾 Save Config
                </button>
                <button className="fsw__btn fsw__btn--ghost" onClick={ping} disabled={pingState === 'pinging'}>
                  {pingState === 'pinging' ? '⏳ Pinging…' : '🔌 Test Connection'}
                </button>
              </div>
              {pingState === 'ok' && (
                <div className="fsw__ping fsw__ping--ok">✅ Server reachable — {pingMsg}</div>
              )}
              {pingState === 'error' && (
                <div className="fsw__ping fsw__ping--err">❌ {pingMsg}</div>
              )}
            </div>

            <div className="fsw__card fsw__card--info">
              <div className="fsw__card-title">📡 Registered Endpoints</div>
              <table className="fsw__endpoint-table">
                <thead><tr><th>Method</th><th>Endpoint</th><th>Description</th></tr></thead>
                <tbody>
                  {[
                    ['POST', '/registerContent', 'Register artifact proof bundle'],
                    ['GET', '/getVerificationContent/:url', 'Verify content by public URL'],
                    ['GET', '/artifacts', 'List all registered artifacts'],
                    ['GET', '/verifyLog', 'Recent verification attempts'],
                    ['GET', '/blockchain/status', 'Blockchain anchor status'],
                    ['GET', '/blockchain/verify-proof/:id', 'Verify Merkle proof'],
                    ['POST', '/blockchain/trigger-anchor', 'Manual anchor cycle (admin)'],
                    ['GET', '/health', 'Health check'],
                  ].map(([m, p, d]) => (
                    <tr key={p}>
                      <td><span className={`fsw__method fsw__method--${m.toLowerCase()}`}>{m}</span></td>
                      <td><code>{p}</code></td>
                      <td>{d}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Blockchain Proof Verifier */}
            <div className="fsw__card">
              <div className="fsw__card-title">🔍 Verify Artifact Proof</div>
              <div className="fsw__field">
                <label>Artifact ID</label>
                <div className="fsw__input-row">
                  <input
                    className="fsw__input"
                    value={proofId}
                    onChange={e => setProofId(e.target.value)}
                    placeholder="Enter artifact ID…"
                  />
                  <button className="fsw__btn fsw__btn--primary" onClick={loadProof}>Verify</button>
                </div>
              </div>
              {proofResult && (
                <pre className={`fsw__proof-result${proofResult.error ? ' fsw__proof-result--err' : proofResult.valid ? ' fsw__proof-result--ok' : ''}`}>
                  {JSON.stringify(proofResult, null, 2)}
                </pre>
              )}
            </div>
          </div>
        )}

        {/* BLOCKCHAIN TAB */}
        {tab === 'blockchain' && (
          <div className="fsw__section">
            <div className="fsw__refresh-row">
              <button className="fsw__btn fsw__btn--ghost" onClick={loadStatus}>↻ Refresh</button>
            </div>
            {statusErr && <div className="fsw__ping fsw__ping--err">❌ {statusErr}</div>}
            {status && (
              <div className="fsw__grid-2">
                <div className="fsw__stat-card">
                  <div className="fsw__stat-label">Network</div>
                  <div className="fsw__stat-value">{status.chain_id === 80002 ? '🟣 Polygon Amoy' : `Chain ${status.chain_id}`}</div>
                </div>
                <div className="fsw__stat-card">
                  <div className="fsw__stat-label">Blockchain</div>
                  <div className={`fsw__stat-value ${status.enabled ? 'fsw__stat-value--ok' : 'fsw__stat-value--warn'}`}>
                    {status.enabled ? '✅ Active' : '⚠️ Disabled'}
                  </div>
                </div>
                <div className="fsw__stat-card">
                  <div className="fsw__stat-label">Pending Anchors</div>
                  <div className="fsw__stat-value">{status.pending_count ?? 0}</div>
                </div>
                <div className="fsw__stat-card">
                  <div className="fsw__stat-label">Total Anchored</div>
                  <div className="fsw__stat-value">{status.total_anchored ?? 0}</div>
                </div>
                <div className="fsw__stat-card fsw__stat-card--wide">
                  <div className="fsw__stat-label">Wallet Address</div>
                  <div className="fsw__stat-value fsw__stat-value--mono">{status.wallet_address ?? '—'}</div>
                </div>
                {status.last_anchor_tx && (
                  <div className="fsw__stat-card fsw__stat-card--wide">
                    <div className="fsw__stat-label">Last Anchor TX</div>
                    <a
                      className="fsw__tx-link"
                      href={`https://amoy.polygonscan.com/tx/${status.last_anchor_tx}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {status.last_anchor_tx.slice(0, 20)}… ↗
                    </a>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ARTIFACTS TAB */}
        {tab === 'artifacts' && (
          <div className="fsw__section">
            <div className="fsw__refresh-row">
              <span className="fsw__count">{artifacts.length} artifact{artifacts.length !== 1 ? 's' : ''}</span>
              <button className="fsw__btn fsw__btn--ghost" onClick={loadArtifacts}>↻ Refresh</button>
            </div>
            {artifactsErr && <div className="fsw__ping fsw__ping--err">❌ {artifactsErr}</div>}
            {artifactsLoading && <div className="fsw__loading">Loading…</div>}
            {!artifactsLoading && artifacts.length === 0 && !artifactsErr && (
              <div className="fsw__empty">No artifacts registered yet. Export a composition with integrity enabled.</div>
            )}
            <div className="fsw__artifact-list">
              {artifacts.map(a => (
                <div key={a.id} className="fsw__artifact-row">
                  <div className="fsw__artifact-icon">
                    {a.content_type === 'video' ? '🎬' : a.content_type === 'image' ? '🖼️' : '📄'}
                  </div>
                  <div className="fsw__artifact-info">
                    <div className="fsw__artifact-name">{a.filename ?? a.id}</div>
                    <div className="fsw__artifact-meta">
                      <code className="fsw__hash">{a.sha256.slice(0, 16)}…</code>
                      <span>·</span>
                      <span>{ts(a.registered_at)}</span>
                      {a.ledger_tx && (
                        <>
                          <span>·</span>
                          <a
                            className="fsw__tx-link"
                            href={`https://amoy.polygonscan.com/tx/${a.ledger_tx}`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            ⛓️ On-chain
                          </a>
                        </>
                      )}
                    </div>
                  </div>
                  <button
                    className="fsw__btn fsw__btn--sm"
                    onClick={() => { setProofId(a.id); setTab('config') }}
                  >
                    Verify Proof
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* VERIFY LOG TAB */}
        {tab === 'log' && (
          <div className="fsw__section">
            <div className="fsw__refresh-row">
              <span className="fsw__count">{log.length} recent verifications</span>
              <button className="fsw__btn fsw__btn--ghost" onClick={loadLog}>↻ Refresh</button>
            </div>
            {logLoading && <div className="fsw__loading">Loading…</div>}
            {!logLoading && log.length === 0 && (
              <div className="fsw__empty">No verification attempts yet.</div>
            )}
            <div className="fsw__log-list">
              {log.map((row, i) => (
                <div key={i} className={`fsw__log-row ${row.verdict === 'UNVERIFIED' ? 'fsw__log-row--fail' : 'fsw__log-row--ok'}`}>
                  <div className="fsw__log-verdict">
                    {row.verdict === 'UNVERIFIED' ? '❌' : '✅'} {row.verdict}
                  </div>
                  <div className="fsw__log-url" title={row.content_url}>{row.content_url}</div>
                  <div className="fsw__log-meta">
                    <span>{row.method ?? 'none'}</span>
                    <span>·</span>
                    <span>{row.content_type}</span>
                    <span>·</span>
                    <span>{ts(row.verified_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
