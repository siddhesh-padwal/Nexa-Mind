/* Optional end-to-end verification against the real running Flask server.
   Requires Playwright and installed Microsoft Edge. No AI responses are mocked.
   Camera success uses Chromium's synthetic camera device, not physical hardware. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const imagePath = process.argv[2];
  if (!imagePath) throw new Error('Usage: node scripts/browser_check.cjs PATH_TO_CAT_IMAGE [OUTPUT_DIRECTORY]');
  const out = path.resolve(process.argv[3] || 'browser-results'); fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] });
  const context = await browser.newContext({ baseURL: process.env.NEXA_URL || 'http://127.0.0.1:5000', viewport: { width: 1440, height: 1050 }, permissions: ['camera'], acceptDownloads: true });
  const page = await context.newPage(); const errors = []; const checks = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  try {
    await page.goto(process.env.NEXA_URL || 'http://127.0.0.1:5000');
    await page.locator('#status-pill[data-state="ready"]').waitFor({ timeout: 600000 });
    await page.screenshot({ path: path.join(out, 'desktop-empty.png'), fullPage: true });
    await page.locator('#file-input').setInputFiles(imagePath);
    await page.locator('#image-workspace').waitFor({ state: 'visible', timeout: 90000 });
    await page.locator('#upload-progress').waitFor({ state: 'hidden' });
    assert.match(await page.locator('#detection-list').innerText(), /cat/i); checks.push('real image upload and cat detection');
    const high = Number(await page.locator('#object-count').innerText());
    await page.locator('#confidence').evaluate(el => { el.value = '25'; }); await page.locator('#confidence').dispatchEvent('input');
    const low = Number(await page.locator('#object-count').innerText()); assert(low >= high); checks.push('confidence filter');
    await page.locator('#confidence').evaluate(el => { el.value = '50'; }); await page.locator('#confidence').dispatchEvent('input');
    const withBoxes = await page.locator('#image-canvas').evaluate(canvas => canvas.toDataURL());
    await page.locator('#show-boxes').uncheck();
    const withoutBoxes = await page.locator('#image-canvas').evaluate(canvas => canvas.toDataURL());
    assert.notEqual(withBoxes, withoutBoxes); await page.locator('#show-boxes').check(); checks.push('bounding-box toggle');
    await page.locator('#question').fill('How many cats are there?'); await page.locator('#ask-button').click();
    await page.locator('.answer-message').waitFor({ timeout: 90000 });
    const answer = await page.locator('.answer-message').innerText(); assert(answer.length > 0); checks.push('real visual answer: ' + answer.split('\n')[0]);
    await page.screenshot({ path: path.join(out, 'desktop-analysis.png'), fullPage: true });
    let downloading = page.waitForEvent('download'); await page.locator('#download-image').click();
    let download = await downloading; await download.saveAs(path.join(out, 'annotated.png')); assert(fs.statSync(path.join(out, 'annotated.png')).size > 1000); checks.push('annotated PNG download');
    downloading = page.waitForEvent('download'); await page.locator('#export-json').click();
    download = await downloading; await download.saveAs(path.join(out, 'analysis.json'));
    const exported = JSON.parse(fs.readFileSync(path.join(out, 'analysis.json'), 'utf8')); assert.equal(exported.questions.length, 1); checks.push('JSON export');
    const analysisId = exported.id;
    await page.reload(); await page.locator('.history-item').first().click();
    await page.locator('.answer-message').waitFor(); assert.match(await page.locator('.user-message').innerText(), /How many cats/); checks.push('persistent history after page reload');
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    await page.screenshot({ path: path.join(out, 'mobile-analysis.png'), fullPage: true }); checks.push('mobile layout without horizontal overflow');
    await page.setViewportSize({ width: 1440, height: 1050 });
    await page.locator('#delete-analysis').click(); await page.locator('#cancel-delete').click(); assert(await page.locator('#image-workspace').isVisible());
    await page.locator('#delete-analysis').click(); await page.locator('#confirm-delete').click();
    await page.locator('#drop-zone').waitFor({ state: 'visible' });
    assert.equal((await page.request.get(`/api/analyses/${analysisId}`)).status(), 404); checks.push('delete confirmation, cancellation, and complete deletion');
    await page.locator('#open-camera').click();
    await page.waitForFunction(() => !document.getElementById('capture-photo').disabled);
    await page.locator('#capture-photo').click();
    await page.locator('#image-workspace').waitFor({ state: 'visible', timeout: 90000 });
    await page.locator('#upload-progress').waitFor({ state: 'hidden' }); checks.push('camera snapshot through real upload/detection using synthetic browser camera');
    await page.locator('#delete-analysis').click(); await page.locator('#confirm-delete').click();
    await page.locator('#drop-zone').waitFor({ state: 'visible' });
    await page.evaluate(() => {
      navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Simulated denial for UI test', 'NotAllowedError'); };
    });
    await page.locator('#open-camera').click();
    await page.waitForFunction(() => document.getElementById('camera-error').textContent.includes('denied'));
    await page.locator('#close-camera').click(); checks.push('camera permission-denied message (simulated denial)');
    assert.deepEqual(errors, []);
    const report = { checks, browserErrors: errors, timestamp: new Date().toISOString() };
    fs.writeFileSync(path.join(out, 'browser-report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
