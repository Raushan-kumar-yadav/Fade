// Cinematic Split — Fade WebComp Template
// Cormorant Garamond splits from center with a light-leak flash

let p = Object.assign({
  topWord:    'CINEMATIC',
  bottomWord: 'UNIVERSE',
  eyebrow:    '2024 · OFFICIAL TRAILER',
  flashColor: '#ffffff',
  textColor:  '#e8dcc8',
}, window.Fade_PARAMS || {});

const scene     = document.getElementById('scene');
const flash     = document.getElementById('flash');
const barTop    = document.getElementById('barTop');
const barBot    = document.getElementById('barBottom');
const divider   = document.getElementById('divider');
const wordTop   = document.getElementById('wordTop');
const wordBot   = document.getElementById('wordBottom');
const eyebrow   = document.getElementById('eyebrow');
const brackets  = [1,2,3,4].map(i => document.getElementById('br'+i));

function applyParams() {
  wordTop.textContent = p.topWord    || 'CINEMATIC';
  wordBot.textContent = p.bottomWord || 'UNIVERSE';
  eyebrow.textContent = p.eyebrow    || '2024 · OFFICIAL TRAILER';
  const tc = p.textColor || '#e8dcc8';
  wordTop.style.color  = tc;
  wordBot.style.color  = tc;
  eyebrow.style.color  = tc;
  brackets.forEach(b => { b.style.color = tc; });
  flash.style.background = `radial-gradient(ellipse 60% 50% at 50% 50%, ${p.flashColor||'#fff'}, transparent)`;
}
applyParams();

// ── Easing ─────────────────────────────────────────────────────────────────────
function easeOutExpo(t)  { return t>=1?1:1-Math.pow(2,-10*t); }
function easeOutCubic(t) { return 1-Math.pow(1-t,3); }
function easeInCubic(t)  { return t*t*t; }
function easeOutBack(t)  {
  const c = 1.70158;
  return 1+(c+1)*Math.pow(t-1,3)+c*Math.pow(t-1,2);
}
function clamp01(t)      { return Math.max(0,Math.min(1,t)); }
function lerp(a,b,t)     { return a+(b-a)*t; }
function prog(f,t0,t1)   { return clamp01((f-t0)/(t1-t0)); }

// Letterbox height animation (bars shrink to 0 on reveal, grow back on exit)
const LETTERBOX_H = 120;

window.addEventListener('fade:frame', (e) => {
  const f = e.detail.frame ?? e.detail ?? 0;

  // ── Light-leak flash (frame 0–10) ──────────────────────────────────────────
  const fp = prog(f, 0, 10);
  flash.style.opacity = Math.sin(fp * Math.PI) * 0.65;

  // ── Letterbox bars ─────────────────────────────────────────────────────────
  // Start tall, shrink to reveal, grow back at end
  const barReveal  = easeOutExpo(prog(f, 5, 30));
  const barHide    = easeInCubic(prog(f, 165, 185));
  const barH       = lerp(LETTERBOX_H, 0, barReveal) + barHide * LETTERBOX_H;
  barTop.style.height = barH + 'px';
  barBot.style.height = barH + 'px';

  // ── Divider ────────────────────────────────────────────────────────────────
  const dp  = easeOutExpo(prog(f, 12, 28));
  const dpo = 1 - easeInCubic(prog(f, 162, 178));
  divider.style.transform = `scaleX(${dp * dpo})`;
  divider.style.opacity   = dp * dpo;

  // ── Words split apart from center ─────────────────────────────────────────
  // Top word slides UP from center
  const wp  = easeOutBack(clamp01(prog(f, 10, 35)));
  const wpo = easeInCubic(prog(f, 158, 178));
  wordTop.style.transform = `translateY(${lerp(-100, 0, wp) - wpo * 100}%)`;
  wordTop.style.opacity   = easeOutCubic(prog(f, 10, 26)) * (1 - wpo);

  // Bottom word slides DOWN from center
  wordBot.style.transform = `translateY(${lerp(100, 0, wp) + wpo * 100}%)`;
  wordBot.style.opacity   = wordTop.style.opacity;

  // ── Eyebrow ────────────────────────────────────────────────────────────────
  const ep  = easeOutCubic(prog(f, 38, 56));
  const epo = 1 - easeInCubic(prog(f, 162, 178));
  eyebrow.style.opacity   = ep * epo;
  eyebrow.style.transform = `translateY(${lerp(10, 0, ep)}px)`;

  // ── Corner brackets ────────────────────────────────────────────────────────
  const bp  = easeOutExpo(prog(f, 18, 36));
  const bpo = 1 - easeInCubic(prog(f, 160, 178));
  brackets.forEach(b => { b.style.opacity = bp * bpo; });
});

window.addEventListener('Fade:params', (e) => {
  Object.assign(p, e.detail);
  applyParams();
});
