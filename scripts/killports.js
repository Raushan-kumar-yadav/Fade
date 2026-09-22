 
const { execSync, spawnSync } = require('child_process')
const path = require('path')
const fs   = require('fs')

 
const toolsDir  = path.join(__dirname, '..', 'tools', 'ffmpeg')
const ffmpegExe = path.join(toolsDir, 'ffmpeg.exe')

if (!fs.existsSync(ffmpegExe)) {
  console.log('[predev] ffmpeg not found in tools/ — downloading...')
  try {
 
    const wingetCheck = spawnSync('winget', ['--version'], { encoding: 'utf8', shell: true })
    if (wingetCheck.status === 0) {
      // winget available 
      const r = spawnSync('winget', ['install', '--id', 'Gyan.FFmpeg', '-e', '--silent', '--accept-package-agreements', '--accept-source-agreements'], {
        encoding: 'utf8', shell: true, stdio: 'inherit'
      })
      if (r.status === 0) {
         
        try {
          const loc = execSync('where ffmpeg', { encoding: 'utf8' }).trim().split('\n')[0].trim()
          fs.mkdirSync(toolsDir, { recursive: true })
          fs.copyFileSync(loc, ffmpegExe)
          // Also copy ffprobe if present
          const probeExe = path.join(path.dirname(loc), 'ffprobe.exe')
          if (fs.existsSync(probeExe)) fs.copyFileSync(probeExe, path.join(toolsDir, 'ffprobe.exe'))
          console.log('[predev] ffmpeg installed and copied to tools/ffmpeg/')
        } catch { }
      }
    } else {
       
      const zipUrl = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
      const zipPath = path.join(__dirname, '..', 'tools', 'ffmpeg_dl.zip')
      fs.mkdirSync(path.join(__dirname, '..', 'tools'), { recursive: true })
      console.log('[predev] Downloading ffmpeg (this may take a minute)...')
      execSync(`powershell -Command "Invoke-WebRequest -Uri '${zipUrl}' -OutFile '${zipPath}'"`, { stdio: 'inherit' })
      execSync(`powershell -Command "Expand-Archive -Path '${zipPath}' -DestinationPath '${path.join(__dirname, '..', 'tools', 'ffmpeg_tmp')}' -Force"`, { stdio: 'inherit' })
      // Find the bin subfolder
      const tmpBin = fs.readdirSync(path.join(__dirname, '..', 'tools', 'ffmpeg_tmp'))
        .map(d => path.join(__dirname, '..', 'tools', 'ffmpeg_tmp', d, 'bin'))
        .find(d => fs.existsSync(d))
      if (tmpBin) {
        fs.mkdirSync(toolsDir, { recursive: true })
        for (const f of fs.readdirSync(tmpBin)) {
          fs.copyFileSync(path.join(tmpBin, f), path.join(toolsDir, f))
        }
        fs.rmSync(path.join(__dirname, '..', 'tools', 'ffmpeg_tmp'), { recursive: true, force: true })
        fs.rmSync(zipPath, { force: true })
        console.log('[predev] ffmpeg downloaded and extracted to tools/ffmpeg/')
      }
    }
  } catch (e) {
    console.warn('[predev] Could not auto-install ffmpeg:', e.message)
    console.warn('[predev] Please install ffmpeg manually: https://ffmpeg.org/download.html')
  }
} else {
  // Already present 
  process.env.PATH = toolsDir + path.delimiter + (process.env.PATH || '')
}
 

function freePort(port) {
  try {
    const out = execSync('netstat -ano', { encoding: 'utf8' })
    // Match exact port in LISTENING state
    const re  = new RegExp(`:${port}\\s+\\S+\\s+LISTENING\\s+(\\d+)`)
    const m = out.match(re)
    if (m) {
      execSync(`taskkill /F /PID ${m[1]}`, { stdio: 'ignore' })
      console.log(`[predev] killed PID ${m[1]} on :${port}`)
    }
  } catch { /* port already free */ }
}

// Free Vite port
freePort(5173)

// Free backend port  
for (let p = 8000; p <= 8005; p++) {
  freePort(p)
}

// Kill any lingering Python processes (stale backend)
try {
  execSync('taskkill /F /IM python.exe', { stdio: 'ignore' })
  console.log('[predev] killed python.exe')
} catch { /* none running */ }

 
try {
  execSync('ping 127.0.0.1 -n 3 > nul', { stdio: 'ignore' })  
} catch { /* ignore */ }

// Kill ports one more time in case python.exe was still dying
for (let p = 8000; p <= 8005; p++) {
  freePort(p)
}

// Ensure AI Python deps are installed  
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
