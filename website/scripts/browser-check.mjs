import { chromium } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import assert from 'node:assert/strict';
const base = process.env.QA_URL || 'http://127.0.0.1:5081';
mkdirSync('artifacts', {recursive: true});
const browser = await chromium.launch({channel: 'chrome', headless: true});
const report = [];
try {
  for (const width of [1440, 768, 390, 320]) {
    const context = await browser.newContext({viewport: {width, height: 1000}, reducedMotion: 'reduce'});
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    await page.goto(base, {waitUntil: 'networkidle'});
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.locator('h1').count(), 1);
    assert.ok(await page.evaluate(() => document.fonts.check('16px Manrope')));
    assert.ok(await page.evaluate(() => [...document.images].every(i => i.complete && i.naturalWidth > 0)));
    const size = await page.evaluate(() => ({width: innerWidth, content: document.documentElement.scrollWidth}));
    assert.ok(size.content <= size.width, `Horizontal overflow at ${width}`);
    if (width < 781) {
      await page.getByRole('button', {name: /Menu/}).click();
      await page.locator('#navigation').getByRole('link', {name: 'Fitur', exact: true}).click();
      assert.equal(await page.locator('.menu-toggle').getAttribute('aria-expanded'), 'false');
    }
    const linux = page.getByRole('tab', {name: 'Linux', exact: true});
    await linux.click();
    assert.equal(await linux.getAttribute('aria-selected'), 'true');
    assert.equal(await page.locator('#panel-linux').isVisible(), true);
    await linux.press('ArrowRight');
    assert.equal(await page.locator('#tab-format').getAttribute('aria-selected'), 'true');
    await page.locator('#tab-windows').click();
    await page.getByText('Apakah file dalam USB akan terhapus?', {exact: true}).click();
    assert.equal(await page.locator('details[open]').count(), 1);
    await page.getByText('Apakah file dalam USB akan terhapus?', {exact: true}).click();
    const accessibility = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
    await page.screenshot({path: `artifacts/home-${width}.png`, fullPage: true});
    report.push({width, overflow: size.content > size.width, errors,
      violations: accessibility.violations.map(v => ({id:v.id, impact:v.impact, description:v.description,
        nodes: v.nodes.map(n => ({target:n.target, summary:n.failureSummary}))}))});
    await context.close();
  }
  const page = await browser.newPage();
  for (const path of ['/open-source.html', '/privacy.html', '/download-status.html']) {
    const response = await page.goto(base + path, {waitUntil: 'networkidle'});
    assert.equal(response.status(), 200);
  }
  const missing = await page.goto(base + '/definitely-missing-file');
  assert.equal(missing.status(), 404);
  writeFileSync('artifacts/browser-report.json', JSON.stringify(report, null, 2));
  for (const item of report) {
    assert.deepEqual(item.errors, [], `Browser errors at ${item.width}`);
    assert.deepEqual(item.violations, [], `Accessibility violations at ${item.width}`);
  }
  console.log(JSON.stringify(report));
} finally { await browser.close(); }
