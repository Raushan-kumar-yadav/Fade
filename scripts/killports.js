/**
 * killports.js — run before `npm run dev` to free Vite + backend ports.
 * Kills PIDs holding :5173 and :8000-8005 (backend may have drifted).
 * Also kills any lingering python.exe (stale backend process).
 * Also ensures AI Python deps (langgraph etc.) are installed in the venv.
 */
const { execSync, spawnSync } = require('child_process')
const path = require('path')
const fs   = require('fs')

function freePort(port) {
  try {
    const out = execSync('netstat -ano', { encoding: 'utf8' })
    // Match exact port in LISTENING state
    const re  = new RegExp(`:${port}\\s+\\S+\\s+LISTENING\\s+(\\d+)`)
    const m   = out.match(re)
    if (m) {
      execSync(`taskkill /F /PID ${m[1]}`, { stdio: 'ignore' })
      console.log(`[predev] killed PID ${m[1]} on :${port}`)
    }
  } catch { /* port already free */ }
}

// Free Vite port
freePort(5173)

// Free backend port + any drift ports from crashed restarts
for (let p = 8000; p <= 8005; p++) {
  freePort(p)
}

// Kill any lingering Python processes (stale backend)
try {
  execSync('taskkill /F /IM python.exe', { stdio: 'ignore' })
  console.log('[predev] killed python.exe')
} catch { /* none running */ }

// Wait for OS to release ports before new backend starts
try {
  execSync('ping 127.0.0.1 -n 3 > nul', { stdio: 'ignore' }) // ~1.5s cross-platform sleep
} catch { /* ignore */ }

// Kill ports one more time in case python.exe was still dying
for (let p = 8000; p <= 8005; p++) {
  freePort(p)
}

// ── Ensure AI Python deps are installed ───────────────────────────────────────
const venvPip = path.join(__dirname, '..', '.venv', 'Scripts', 'pip.exe')
const reqFile = path.join(__dirname, '..', 'requirements.txt')

if (fs.existsSync(venvPip) && fs.existsSync(reqFile)) {
  try {
    // Quick check: if langgraph importable, skip install
    const venvPy = path.join(__dirname, '..', '.venv', 'Scripts', 'python.exe')
    const check = spawnSync(venvPy, ['-c', 'import langgraph'], { encoding: 'utf8' })
    if (check.status !== 0) {
      console.log('[predev] langgraph missing — installing AI deps from requirements.txt...')
      const res = spawnSync(venvPip, ['install', '-r', reqFile, '-q'], {
        encoding: 'utf8', stdio: 'inherit'
      })
      if (res.status === 0) {
        console.log('[predev] AI deps installed OK')
      } else {
        console.warn('[predev] AI deps install failed — AI features may not work')
      }
    } else {
      console.log('[predev] AI deps OK')
    }
  } catch (e) {
    console.warn('[predev] Could not check AI deps:', e.message)
  }
}
