/**
 * killports.js — run before `npm run dev` to free Vite + backend ports.
 * Kills PIDs holding :5173 and :8000-8005 (backend may have drifted).
 * Also kills any lingering python.exe (stale backend process).
 */
const { execSync } = require('child_process')

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
