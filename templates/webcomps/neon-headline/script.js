// Neon Headline — Fade WebComp Template
// Orbitron font with electric neon glow flicker reveal

let p = Object.assign({
  topLabel:  'STUDIO PRESENTS',
  mainText:  'ILLUMINATE',
  tagline:   'Beyond the visible',
  neonColor: '#00ffe7',
  bgColor:   '#05050f',
}, window.Fade_PARAMS || {});

const scene     = document.getElementById('scene');
const scanlines = document.getElementById('scanlines');
const glowField = document.getElementById('glowField');
const ruleTop   = document.getElementById('ruleTop');
const ruleBot   = document.getElementById('ruleBottom');
const topLabel  = document.getElementById('topLabel');
const mainText  = document.getElementById('mainText');
const tagline   = document.getElementById('tagline');

function hexToRgb(hex) {
  const r = parseInt(hex.slice(1,3),16);
  const g = parseInt(hex.slice(3,5),16);
  const b = parseInt(hex.slice(5,7),16);
  return `${r},${g},${b}`;
}

function applyParams() {
  scene.style.background = p.bgColor || '#05050f';
  const nc  = p.neonColor || '#00ffe7';
  const rgb = hexToRgb(nc);

  mainText.style.webkitTextStrokeColor = nc;
  mainText.dataset.text = p.mainText || 'ILLUMINATE';
  mainText.textContent  = p.mainText || 'ILLUMINATE';
  topLabel.textContent  = p.topLabel || 'STUDIO PRESENTS';
  tagline.textContent   = p.tagline  || 'Beyond the visible';

  topLabel.style.color = nc + '99';
  ruleTop.style.background  = `linear-gradient(90deg,transparent,${nc},transparent)`;
  ruleBot.style.background  = `linear-gradient(90deg,transparent,${nc},transparent)`;
  glowField.style.background = `radial-gradient(ellipse, rgba(${rgb},0.14) 0%, transparent 70%)`;
  scanlines.style.backgroundImage = `repeating-linear-gradient(
    0deg, transparent, transparent 3px,
    rgba(${rgb},0.015) 3px, rgba(${rgb},0.015) 4px
  )`;
}
applyParams();

//   Easing  
function easeOutExpo(t)  { return t>=1?1:1-Math.pow(2,-10*t); }
function easeOutCubic(t) { return 1-Math.pow(1-t,3); }
function easeInCubic(t)  { return t*t*t; }
function clamp01(t) { return Math.max(0,Math.min(1,t)); }
function lerp(a,b,t) { return a+(b-a)*t; }

function prog(f, t0, t1) { return clamp01((f-t0)/(t1-t0)); }

// Neon flicker table  
const flickerTable = [1,1,0.3,1,1,0.6,1,1,1,0.2,1,1,1,0.8,1,0.4,1,1];
function flicker(f) {
  return flickerTable[f % flickerTable.length];
}

window.addEventListener('fade:frame', (e) => {
  const f = e.detail.frame ?? e.detail ?? 0;
  const DUR = 180;

  // Scanlines fade in
  scanlines.style.opacity = easeOutCubic(prog(f,0,15)) * (1-prog(f,160,180));

  // Glow field
  glowField.style.opacity = easeOutCubic(prog(f,5,30)) * (1-easeInCubic(prog(f,155,178)));

  // Rules slide in from center
  const rp = easeOutExpo(prog(f,8,24));
  const ro = 1-easeInCubic(prog(f,158,175));
  ruleTop.style.opacity = rp * ro;
  ruleBot.style.opacity = rp * ro;
  ruleTop.style.transform = `scaleX(${rp * ro})`;
  ruleBot.style.transform = `scaleX(${rp * ro})`;

  // Top label slide down
  const lp = easeOutCubic(prog(f,12,28));
  const lo = 1-easeInCubic(prog(f,155,170));
  topLabel.style.opacity   = lp * lo;
  topLabel.style.transform = `translateY(${lerp(-20,0,lp)}px)`;

  // Main text 
  const mp = prog(f,20,45);
  const mo = 1-easeInCubic(prog(f,148,168));
  const mEase = easeOutExpo(mp);

  // Flicker during reveal 
  const flickMult = mp < 0.9 ? flicker(f) : 1;

  mainText.style.opacity   = mEase * flickMult * mo;
  mainText.style.transform = `scale(${lerp(0.86,1,mEase)})`;

  
  const glowIntensity = mEase * flickMult * mo;
  mainText.style.setProperty('--glow', glowIntensity);
  // Use filter on parent to simulate glow brightening
  const blurPx = lerp(20, 0, mEase);
  mainText.style.filter = `drop-shadow(0 0 ${12*glowIntensity}px ${p.neonColor||'#00ffe7'}) drop-shadow(0 0 ${40*glowIntensity}px ${p.neonColor||'#00ffe7'})`;

  // Tagline
  const tp = easeOutCubic(prog(f,42,62));
  const to = 1-easeInCubic(prog(f,158,175));
  tagline.style.opacity   = tp * to;
  tagline.style.transform = `translateY(${lerp(16,0,tp)}px)`;
});

window.addEventListener('Fade:params', (e) => {
  Object.assign(p, e.detail);
  applyParams();
});
