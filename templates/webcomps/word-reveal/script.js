// Word Reveal — Fade WebComp Template
// Each word blurs/slides in with a staggered offset

const DUR = 210;

let p = Object.assign({
  line1:   'The Future',
  line2:   'Is Now',
  caption: 'A New Chapter',
  accent:  '#6c63ff',
  stagger: 8,
}, window.FADE_PARAMS || {});

// ── DOM refs ──────────────────────────────────────────────────────────────────
const line1El     = document.getElementById('line1');
const line2El     = document.getElementById('line2');
const captionEl   = document.getElementById('caption');
const accentBar   = document.getElementById('accentBar');
const orb1        = document.getElementById('orb1');
const orb2        = document.getElementById('orb2');
const orb3        = document.getElementById('orb3');

// ── Build word spans ───────────────────────────────────────────────────────────
/**
 * @param {HTMLElement} el
 * @param {string} text
 * @returns {HTMLElement[]}
 */
function buildWords(el, text) {
  el.innerHTML = '';
  return text.split(/\s+/).filter(Boolean).map(w => {
    const span = document.createElement('span');
    span.className = 'word';
    span.textContent = w;
    el.appendChild(span);
    return span;
  });
}

let words1 = [], words2 = [], wordsC = [];

function rebuild() {
  words1 = buildWords(line1El,   p.line1   || 'The Future');
  words2 = buildWords(line2El,   p.line2   || 'Is Now');
  wordsC = buildWords(captionEl, p.caption || 'A New Chapter');
  accentBar.style.background = p.accent || '#6c63ff';
  orb1.style.background = p.accent || '#6c63ff';
}
rebuild();

// ── Easing ─────────────────────────────────────────────────────────────────────
function easeOutExpo(t)  { return t >= 1 ? 1 : 1 - Math.pow(2, -10 * t); }
function easeOutBack(t)  {
  const c1 = 1.70158, c3 = c1 + 1;
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
}
function easeInExpo(t)   { return t <= 0 ? 0 : Math.pow(2, 10 * t - 10); }
function clamp(t, a, b)  { return Math.max(a, Math.min(b, t)); }
function clamp01(t)      { return clamp(t, 0, 1); }
function lerp(a, b, t)   { return a + (b - a) * t; }

// ── Animation timing ───────────────────────────────────────────────────────────
// Timeline:
// 0–10   : orbs fade in
// 10–80  : words line1 staggered in
// stagger: words line2 staggered after line1 ends
// ...    : caption in
// 155+   : orbs + words fade out

function animateWordIn(wordEls, frameStart, staggerF, frame, outStart) {
  wordEls.forEach((w, i) => {
    const t0 = frameStart + i * staggerF;
    const t1 = t0 + 22;
    const p  = clamp01((frame - t0) / (t1 - t0));
    const po = clamp01((frame - outStart - i * 4) / 18);

    const pIn  = easeOutBack(p);
    const pOut = easeInExpo(po);

    const ty   = lerp(60,  0, pIn) + pOut * -60;
    const blur = lerp(12,  0, easeOutExpo(p)) + pOut * 12;
    const op   = clamp01(easeOutExpo(p) - pOut);

    w.style.transform = `translateY(${ty}px)`;
    w.style.filter    = `blur(${blur}px)`;
    w.style.opacity   = op;
  });
}

window.addEventListener('fade:frame', (e) => {
  const f  = e.detail.frame ?? e.detail ?? 0;
  const sg = Math.max(2, Math.round(p.stagger ?? 8));

  // Orbs
  const orbIn  = clamp01(f / 20);
  const orbOut = clamp01((f - 165) / 20);
  const orbA   = easeOutExpo(orbIn) * (1 - easeInExpo(orbOut));
  orb1.style.opacity = orbA * 0.35;
  orb2.style.opacity = orbA * 0.25;
  orb3.style.opacity = orbA * 0.15;

  // Line 1 words (start f=10)
  const l1Start = 10;
  const l1End   = l1Start + words1.length * sg + 22;
  animateWordIn(words1, l1Start, sg, f, 158);

  // Line 2 words (start after line 1 halfway)
  const l2Start = l1Start + Math.ceil(words1.length * sg / 2);
  animateWordIn(words2, l2Start, sg, f, 162);

  // Accent bar grows after last line2 word
  const barStart = l2Start + (words2.length - 1) * sg + 18;
  const barP     = clamp01((f - barStart) / 20);
  const barOut   = clamp01((f - 162) / 14);
  const barW     = easeOutExpo(barP) * (1 - barOut) * 300;
  accentBar.style.width = `${barW}px`;
  accentBar.style.opacity = easeOutExpo(barP) * (1 - barOut);

  // Caption
  const capStart = barStart + 10;
  animateWordIn(wordsC, capStart, 5, f, 168);
});

window.addEventListener('fade:params', (e) => {
  Object.assign(p, e.detail);
  rebuild();
});
