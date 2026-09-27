const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  
  try {
    await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle0', timeout: 30000 });
    
    // Evaluate in page to avoid powershell mangling
    const res = await page.evaluate(async () => {
      let msg = [];
      const btn = document.querySelector('.hp-btn--primary');
      if (btn) {
        btn.click();
        await new Promise(r => setTimeout(r, 2000));
      }
      
      const brushTool = document.querySelector('#tbx-tool-brush');
      if (brushTool) {
        brushTool.click();
        msg.push('Clicked brush tool.');
      }
      
      const tabs = Array.from(document.querySelectorAll('.flexlayout__tab_button'));
      const toolsTab = tabs.find(t => t.textContent.includes('Tools'));
      if (toolsTab) {
        toolsTab.click();
        msg.push('Clicked Tools tab.');
      }
      
      await new Promise(r => setTimeout(r, 1000));
      
      const tpPanel = document.querySelector('.tp-panel');
      if (tpPanel) {
        msg.push('FOUND tp-panel!');
        msg.push(tpPanel.outerHTML.substring(0, 500));
      } else {
        msg.push('tp-panel NOT FOUND.');
        const props = document.querySelector('.vp--props');
        if (props) {
            msg.push('Found vp--props instead: ' + props.outerHTML);
        }
      }
      return msg;
    });
    console.log(res.join('\n'));
  } catch (err) {
    console.error('Error:', err);
  }
  
  await browser.close();
})();
