// Lower Third — Fade WebComp Template
// Animated slide-in/out with easing

const lt = document.getElementById('lt');
const bar = document.getElementById('bar');
const nameEl = document.getElementById('nameText');
const titleEl = document.getElementById('titleText');

// Animation timing (in frames)
const ANIM_IN_START = 10;
const ANIM_IN_END = 30;
const ANIM_OUT_START = 120;
const ANIM_OUT_END = 140;

function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3);
}

function easeInCubic(t) {
  return t * t * t;
}

window.addEventListener('fade:frame', (e) => {
  const { frame } = e.detail;

  let progress;
  if (frame < ANIM_IN_START) {
    progress = 0;
  } else if (frame <= ANIM_IN_END) {
    progress = easeOutCubic((frame - ANIM_IN_START) / (ANIM_IN_END - ANIM_IN_START));
  } else if (frame < ANIM_OUT_START) {
    progress = 1;
  } else if (frame <= ANIM_OUT_END) {
    progress = 1 - easeInCubic((frame - ANIM_OUT_START) / (ANIM_OUT_END - ANIM_OUT_START));
  } else {
    progress = 0;
  }

  const translateX = -120 * (1 - progress);
  lt.style.transform = `translateX(${translateX}%)`;
  lt.style.opacity = progress;
});

window.addEventListener('fade:params', (e) => {
  const p = e.detail;
  if (p.name) nameEl.textContent = p.name;
  if (p.title) titleEl.textContent = p.title;
  if (p.accentColor) {
    bar.style.background = `linear-gradient(180deg, ${p.accentColor}, ${p.accentColor}88)`;
  }
});
