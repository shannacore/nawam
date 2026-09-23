import { chromium, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
const base = (process.env.QA_URL || 'http://127.0.0.1:5081').replace(/\/$/, '');
const output = process.env.QA_I18N_OUTPUT || 'artifacts/i18n';
const pages = ['', 'open-source.html', 'privacy.html', 'download-status.html', '404.html'];
const widths = [1440, 768, 390, 320];
const report = {base, browser: 'Chrome', pages: [], behaviors: []};
mkdirSync(output, {recursive: true});
const save = () => writeFileSync(`${output}/report.json`, JSON.stringify(report, null, 2));
const release = JSON.parse(readFileSync(new URL('../public/release.json', import.meta.url), 'utf8'));
const browser = await chromium.launch({channel: 'chrome', headless: true});
try {
  report.browserVersion = browser.version();
  for (const lang of ['id', 'en']) {
    for (const width of widths) {
      const context = await browser.newContext({viewport: {width, height: 1000}, reducedMotion: 'reduce'});
      const page = await context.newPage();
      for (const name of pages) {
        const path = `${lang === 'en' ? '/en/' : '/'}${name}`;
        const errors = [];
        const pageError = e => errors.push(e.message);
        const consoleError = m => {
          const expected404 = m.location().url === base + '/404.html' && /404/.test(m.text());
          if (m.type() === 'error' && !expected404) errors.push(m.text());
        };
        page.on('pageerror', pageError);
        page.on('console', consoleError);
        const response = await page.goto(base + path, {waitUntil: 'networkidle'});
        await page.evaluate(() => document.fonts.ready);
        assert.equal(response.status(), path === '/404.html' ? 404 : 200, path);
        assert.equal(await page.locator('html').getAttribute('lang'), lang);
        assert.equal(await page.locator('h1').count(), 1);
        assert.equal(await page.locator('.language-switch a').count(), 1);
        assert.ok(await page.evaluate(() => [...document.images].every(i => i.complete && i.naturalWidth > 0)));
        const size = await page.evaluate(() => ({width: innerWidth, content: document.documentElement.scrollWidth}));
        const switchTarget = `${lang === 'en' ? '/' : '/en/'}${name}`;
        const alternate = page.locator(`.language-switch a[lang="${lang === 'en' ? 'id' : 'en'}"]`);
        assert.equal(await alternate.getAttribute('href'), switchTarget);
        if (!name) {
          await expect(page.locator('#release-hash')).toHaveText(release.sha256);
          await expect(page.locator('#download-button')).toHaveText(lang === 'en' ? 'Download Nawam for Windows ↓' : 'Unduh Nawam untuk Windows ↓');
          if (await page.locator('.menu-toggle').isVisible()) {
            await page.locator('.menu-toggle').click();
            await page.keyboard.press('Escape');
            await expect(page.locator('.menu-toggle')).toHaveAttribute('aria-expanded', 'false');
            await page.locator('.menu-toggle').click();
            await page.locator('#navigation a[href="#fitur"]').click();
            await expect(page.locator('.menu-toggle')).toHaveAttribute('aria-expanded', 'false');
          }
          await page.locator('#tab-linux').click();
          await expect(page.locator('#panel-linux')).toBeVisible();
          await page.locator('#tab-linux').press('ArrowRight');
          await expect(page.locator('#panel-format')).toBeVisible();
          await page.locator('#tab-format').press('Home');
          await expect(page.locator('#panel-windows')).toBeVisible();
          await page.locator('details summary').nth(1).click();
          await expect(page.locator('details[open]')).toHaveCount(1);
          await page.locator('details summary').nth(1).click();
          await page.evaluate(() => { location.hash = '#faq'; });
          await expect(alternate).toHaveAttribute('href', `${switchTarget}#faq`);
          await alternate.focus();
          await page.keyboard.press('Enter');
          await expect(page).toHaveURL(base + switchTarget + '#faq');
          const back = page.locator(`.language-switch a[lang="${lang}"]`);
          await expect(back).toHaveAttribute('href', path + '#faq');
          await back.click();
          await expect(page).toHaveURL(base + path + '#faq');
          await page.evaluate(() => { location.hash = ''; scrollTo(0, 0); });
          await page.screenshot({path: `${output}/${lang}-home-${width}.png`, fullPage: true});
        } else {
          await alternate.click();
          await expect(page).toHaveURL(base + switchTarget);
          await page.locator(`.language-switch a[lang="${lang}"]`).click();
          await expect(page).toHaveURL(base + path);
        }
        const accessibility = await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
        report.pages.push({lang, width, path, status: response.status(), overflow: size.content > size.width, errors,
          violations: accessibility.violations.map(v => ({id: v.id, impact: v.impact,
            nodes: v.nodes.map(n => ({target: n.target, summary: n.failureSummary}))}))});
        save();
        page.off('pageerror', pageError);
        page.off('console', consoleError);
      }
      await context.close();
    }
  }
  for (const lang of ['id', 'en']) {
    const path = lang === 'en' ? '/en/' : '/';
    const context = await browser.newContext({permissions: ['clipboard-read', 'clipboard-write']});
    const page = await context.newPage();
    await page.goto(base + path);
    await expect(page.locator('#copy-hash')).toBeEnabled();
    await page.locator('#copy-hash').click();
    await expect(page.locator('#copy-status')).toHaveText(lang === 'en' ? 'Checksum copied.' : 'Checksum berhasil disalin.');
    assert.equal(await page.evaluate(() => navigator.clipboard.readText()), release.sha256);
    await page.evaluate(() => { navigator.clipboard.writeText = async () => { throw new DOMException('denied', 'NotAllowedError'); }; });
    await page.locator('#copy-hash').click();
    await expect(page.locator('#copy-status')).toContainText(lang === 'en' ? 'copy it manually' : 'salin secara manual');
    report.behaviors.push({lang, clipboard: 'real API success; controlled denied-permission fallback'});
    for (const bad of [{...release, url: release.url.replace('shannacore', 'other')},
      {...release, version: '99.0.0'}, {...release, bytes: 0}, {...release, sha256: 'invalid'}]) {
      await page.route('**/release.json', route => route.fulfill({json: bad}));
      await page.goto(base + path, {waitUntil: 'networkidle'});
      await expect(page.locator('#copy-hash')).toBeDisabled();
      await expect(page.locator('#download-button')).toHaveAttribute('href', release.url);
      await page.unroute('**/release.json');
    }
    await page.route('**/release.json', route => route.fulfill({status: 503, body: 'Unavailable'}));
    await page.goto(base + path, {waitUntil: 'networkidle'});
    await expect(page.locator('#copy-hash')).toBeDisabled();
    report.behaviors.push({lang, malformedMetadata: 'rejected', unavailableMetadata: 'static link retained'});
    await context.close();
    const noJS = await browser.newContext({javaScriptEnabled: false});
    const staticPage = await noJS.newPage();
    await staticPage.goto(base + path);
    const other = lang === 'en' ? 'id' : 'en';
    await staticPage.locator(`.language-switch a[lang="${other}"]`).click();
    await expect(staticPage.locator('html')).toHaveAttribute('lang', other);
    report.behaviors.push({lang, noJavaScriptSwitch: 'passed'});
    await noJS.close();
  }
  assert.equal(report.pages.length, pages.length * widths.length * 2);
  for (const entry of report.pages) {
    assert.equal(entry.overflow, false, `Overflow: ${entry.path} ${entry.width}`);
    assert.deepEqual(entry.errors, [], `Browser errors: ${entry.path} ${entry.width}`);
    assert.deepEqual(entry.violations, [], `Accessibility: ${entry.path} ${entry.width}`);
  }
  console.log(JSON.stringify({checks: report.pages.length, behaviors: report.behaviors.length, report: `${output}/report.json`, passed: true}));
} catch (error) {
  report.failure = error.stack;
  throw error;
} finally {
  save();
  await browser.close();
}
