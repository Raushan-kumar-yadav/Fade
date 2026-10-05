/**
 * fadeServerApi.ts
 * Client for the remote Fade Verification Server (Render backend).
 * Config is persisted to localStorage so it survives app restarts.
 */

const STORAGE_KEY = 'fade_server_config'

export interface FadeServerConfig {
  baseUrl: string
  apiKey: string
}

const DEFAULTS: FadeServerConfig = {
  baseUrl: 'https://fade-web-backend.onrender.com',
  apiKey: 'sih2026-fade-secret-key',
}

export function getFadeServerConfig(): FadeServerConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) }
  } catch {}
  return { ...DEFAULTS }
}

export function saveFadeServerConfig(cfg: FadeServerConfig) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg))
}

export interface RegisterPayload {
  artifact_id: string
  sha256: string
  phash?: string | null
  wm_id?: string | null
  merkle_proof?: any[] | null
  merkle_root?: string | null
  ledger_tx?: string | null
  filename?: string | null
  content_type?: string | null
  size_bytes?: number | null
}

export interface RegisterResult {
  ok: boolean
  artifact_id: string
  registered_at: number
}

export interface BlockchainStatus {
  enabled: boolean
  chain_id?: number
  wallet_address?: string
  last_anchor_tx?: string | null
  pending_count?: number
  total_anchored?: number
  error?: string
}

export interface ArtifactRecord {
  id: string
  filename: string | null
  content_type: string
  sha256: string
  registered_at: number
  registered_by: string | null
  ledger_tx: string | null
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  cfg?: FadeServerConfig
): Promise<T> {
  const config = cfg ?? getFadeServerConfig()
  const url = `${config.baseUrl}${path}`
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  const resp = await fetch(url, { ...options, headers })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new Error(body.detail ?? `Server error ${resp.status}`)
  }
  return resp.json()
}

/** POST /registerContent  — register a proof bundle on the server */
export async function registerOnServer(
  payload: RegisterPayload,
  cfg?: FadeServerConfig
): Promise<RegisterResult> {
  const config = cfg ?? getFadeServerConfig()
  return request<RegisterResult>(
    '/registerContent',
    {
      method: 'POST',
      headers: { 'X-API-Key': config.apiKey },
      body: JSON.stringify(payload),
    },
    config
  )
}

/** GET /blockchain/status */
export async function getBlockchainStatus(cfg?: FadeServerConfig): Promise<BlockchainStatus> {
  return request<BlockchainStatus>('/blockchain/status', {}, cfg)
}

/** GET /artifacts */
export async function listArtifacts(cfg?: FadeServerConfig): Promise<{ artifacts: ArtifactRecord[] }> {
  const config = cfg ?? getFadeServerConfig()
  return request<{ artifacts: ArtifactRecord[] }>(
    `/artifacts?x_api_key=${encodeURIComponent(config.apiKey)}`,
    {},
    config
  )
}

/** GET /verifyLog */
export async function getVerifyLog(limit = 20, cfg?: FadeServerConfig): Promise<{ log: any[] }> {
  return request<{ log: any[] }>(`/verifyLog?limit=${limit}`, {}, cfg)
}

/** GET /health */
export async function pingServer(cfg?: FadeServerConfig): Promise<{ status: string }> {
  return request<{ status: string }>('/health', {}, cfg)
}

/** GET /blockchain/verify-proof/:artifactId */
export async function verifyProof(
  artifactId: string,
  cfg?: FadeServerConfig
): Promise<any> {
  return request<any>(`/blockchain/verify-proof/${artifactId}`, {}, cfg)
}
