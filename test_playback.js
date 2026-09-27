const puppeteer = require('puppeteer');
(async () => {
  let browser;
  try {
    browser = await puppeteer.connect({ browserURL: 'http://localhost:9222' });
    const pages = await browser.pages();
    let page = pages.find(p => p.url().includes('localhost:5173'));
    
    // We will simulate creating a new project, fetching /editor/state to add an image to media pool,
    // then adding it to the timeline.
    const res = await page.evaluate(async () => {
      let log = [];
      const btn = document.querySelector('.hp-btn--primary');
      if (btn) btn.click(); // New Project
      await new Promise(r => setTimeout(r, 2000));
      
      // Upload an image via HTTP POST directly to backend API or use the UI
      // FADE adds assets by sending the path to /editor/import?
      // Actually we can just create an image file and simulate dropping it!
      return log;
    });
    console.log(res);
  } catch (err) {
    console.error(err);
  } finally {
    if (browser) await browser.disconnect();
  }
})();
