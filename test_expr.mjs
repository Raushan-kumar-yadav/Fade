const clipId = '0f2601c0-5c3a-492b-b31e-b12b280c0f8a';
const trackId = '7c1901f6-934';
const base = 'http://localhost:8000';

const exprX = `track("${trackId}", frame, "cx")`;
const exprY = `track("${trackId}", frame, "cy")`;

async function test() {
  const rx = await fetch(`${base}/clips/${clipId}/expression/pos_x`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({expression: exprX})
  });
  console.log('pos_x:', await rx.text());

  const ry = await fetch(`${base}/clips/${clipId}/expression/pos_y`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({expression: exprY})
  });
  console.log('pos_y:', await ry.text());
}
test().catch(console.error);
