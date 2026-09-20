 
const scene = document.getElementById('scene');
const bg = document.getElementById('bg');
const grid = document.getElementById('grid');
const scan = document.getElementById('scan');
const barTop   = document.getElementById('barTop');
const barBot   = document.getElementById('barBottom');
const highlight= document.getElementById('highlight');
const headline = document.getElementById('headline');
const subline  = document.getElementById('subline');
const frameNum = document.getElementById('frameNum');

// Defaults from Fade_PARAMS (set before first frame event)
let p = Object.assign({
  headline:   'BREAKING NEWS',
  subline:    'Live Coverage',
  color1:     '#ff6b35',
  color2:     '#f7c59f',
  dark:       true,
}, window.Fade_PARAMS || {});

function applyParams() {
  headline.textContent = p.headline || 'BREAKING NEWS';
  subline.textContent  = p.subline  || 'Live Coverage';
  barTop.style.background    = `linear-gradient(90deg, transparent, ${p.color1}, ${p.color2}, transparent)`;
  barBot.style.background    = `linear-gradient(90deg, transparent, ${p.color1}, ${p.color2}, transparent)`;
  highlight.style.background = `linear-gradient(90deg, transparent 0%, ${p.color1}22 50%, transparent 100%)`;
  bg.style.background = p.dark ? '#0a0a0f' : '#f5f5f0';
  headline.style.color = p.dark ? '#ffffff' : '#0a0a0f';
  subline.style.color  = p.dark ? 'rgba(255,255,255,0.55)' : 'rgba(10,10,15,0.55)';
}
applyParams();

//   Easing  
function easeOutExpo(t) { return t === 1 ? 1 : 1 - Math.pow(2, -10 * t); }
function easeOutCubic(t){ return 1 - Math.pow(1 - t, 3); }
function easeInExpo(t) { return t === 0 ? 0 : Math.pow(2, 10 * t - 10); }
function clamp01(t) { return Math.max(0, Math.min(1, t)); }

function lerp(a, b, t)  { return a + (b - a) * t; }

// Animation timeline (frames)
const DUR = 180;
const T = {
  bgIn: [0,  8],
  scanSlide: [5,  18],
  barsIn: [8,  20],
  headIn: [14, 32],
  subIn: [22, 40],
  hlIn: [16, 28],
  idle: [40, 140],
  hlOut: [130,145],
  headOut: [140,158],
  subOut: [148,162],
  barsOut: [152,165],
  bgOut: [160,180],
};

function prog(frame, t0, t1) {
  return clamp01((frame - t0) / (t1 - t0));
}

window.addEventListener('fade:frame', (e) => {
  const f = e.detail.frame ?? e.detail ?? 0;
  frameNum.textContent = 'F' + String(f).padStart('000'.length, '0');

  // Background
  bg.style.opacity   = easeOutCubic(prog(f, ...T.bgIn)) * (1 - easeInExpo(prog(f, ...T.bgOut)));
  grid.style.opacity = easeOutCubic(prog(f, ...T.bgIn)) * 0.4 * (1 - prog(f, ...T.bgOut));

  // Scan line burst
  const sp = prog(f, ...T.scanSlide);
  scan.style.transform = `scaleX(${easeOutExpo(sp)})`;
  scan.style.opacity   = sp < 0.5 ? sp * 2 : (1 - sp) * 2;

  // Accent bars
  const bp = easeOutExpo(prog(f, ...T.barsIn));
  const bpOut = prog(f, ...T.barsOut);
  const bScale = bp * (1 - easeInExpo(bpOut));
  barTop.style.transform = `scaleX(${bScale})`;
  barBot.style.transform = `scaleX(${bScale})`;

  // Highlight
  const hlP = easeOutCubic(prog(f, ...T.hlIn));
  const hlO = prog(f, ...T.hlOut);
  highlight.style.transform = `scaleX(${hlP * (1 - hlO)})`;
  highlight.style.opacity   = hlP * (1 - hlO);

  // Headline reveal (slide up from clip)
  const hp = easeOutExpo(prog(f, ...T.headIn));
  const hOut= easeInExpo(prog(f, ...T.headOut));
  headline.style.transform = `translateY(${lerp(110, 0, hp) + hOut * -110}%)`;

  // Subline reveal
  const sp2 = easeOutCubic(prog(f, ...T.subIn));
  const sOut = easeInExpo(prog(f, ...T.subOut));
  subline.style.transform = `translateY(${lerp(110, 0, sp2) + sOut * -110}%)`;
});

window.addEventListener('Fade:params', (e) => {
  Object.assign(p, e.detail);
  applyParams();
});
