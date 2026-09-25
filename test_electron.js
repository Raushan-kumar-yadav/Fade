const puppeteer = require('puppeteer');

(async () => {
  try {
    const browser = await puppeteer.connect({ browserURL: 'http://localhost:9222' });
    const pages = await browser.pages();
    let page = pages.find(p => p.url().includes('localhost:5173'));
    
    const res = await page.evaluate(async () => {
      let msg = [];
      const brushTool = document.querySelector('#tbx-tool-brush');
      if (brushTool) brushTool.click();
      
      const flexTabs = Array.from(document.querySelectorAll('.flexlayout__tab_button'));
      const toolsTab = flexTabs.find(t => t.textContent.includes('Tools'));
      if (toolsTab) toolsTab.click();
      
      await new Promise(r => setTimeout(r, 1000));
      
      const tpPanel = document.querySelector('.tp-panel');
      if (tpPanel) {
          msg.push('Found tp-panel after redesign!');
          msg.push('Text inside: ' + tpPanel.innerText.substring(0, 150).replace(/\n/g, ' '));
      } else {
          msg.push('tp-panel NOT FOUND.');
      }
      return msg;
    });
    console.log(res.join('\n'));
    await browser.disconnect();
  } catch (err) {
    console.error('Error:', err);
  }
})();
