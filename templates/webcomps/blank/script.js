 

window.addEventListener('fade:frame', (e) => {
  const { frame, time } = e.detail;
  // Animate here based on frame/time
});

window.addEventListener('Fade:params', (e) => {
  const params = e.detail;
  // React to param changes here
});
