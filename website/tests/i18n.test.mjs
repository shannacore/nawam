import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = p => readFileSync(resolve(root, p), 'utf8');
const pages = ['index.html', 'open-source.html', 'privacy.html', 'download-status.html', '404.html'];
const route = (page, lang) => `${lang === 'en' ? '/en/' : '/'}${page === 'index.html' ? '' : page}`;

test('five complete static English pages have paired navigation and search metadata', () => {
  for (const page of pages) {
    assert.ok(existsSync(resolve(root, 'public/en', page)), `English page missing: ${page}`);
    for (const lang of ['id', 'en']) {
      const html = read(`public/${lang === 'en' ? 'en/' : ''}${page}`);
      assert.match(html, new RegExp(`<html lang="${lang}"`));
      assert.ok(html.includes(`rel="canonical" href="https://nawam.shanna.id${route(page, lang)}"`));
      for (const alternate of ['id', 'en']) {
        assert.ok(html.includes(`hreflang="${alternate}" href="https://nawam.shanna.id${route(page, alternate)}"`));
        if (alternate !== lang) assert.ok(html.includes(`href="${route(page, alternate)}" lang="${alternate}" hreflang="${alternate}"`));
      }
      assert.ok(html.includes('hreflang="x-default"'));
      assert.ok(html.includes('class="language-switch"'));
      assert.ok(html.includes('data-language-link'));
      assert.ok(html.includes('/assets/i18n.css'));
      assert.ok(html.includes('/assets/site.js'));
      assert.ok(html.includes(`data-current-language="${lang}"`));
      for (const m of html.matchAll(/(?:src|href)="(\/[^"#?]*)"/g)) {
        const asset = m[1].endsWith('/') ? `${m[1]}index.html` : m[1];
        assert.ok(existsSync(resolve(root, `public${asset}`)), `Missing ${asset}`);
      }
    }
  }
});

test('English content includes every home section, warnings, legal and privacy disclosures', () => {
  const html = read('public/en/index.html');
  const id = read('public/index.html');
  for (const match of id.matchAll(/id="([^"]+)"/g)) assert.ok(html.includes(match[0]), match[1]);
  assert.equal([...html.matchAll(/<details>/g)].length, [...id.matchAll(/<details>/g)].length);
  for (const text of ['not digitally signed', 'physical USB', 'Windows 10 x64', 'not been tested', 'nawam.ini', 'Actual Nawam screenshot']) assert.ok(html.includes(text), text);
  assert.ok(!/\b(Unduh|Perangkat|Privasi|Kembali|Sistem berkas|belum|Anda|pengaturan)\b/.test(html));
  const legal = read('public/en/open-source.html');
  for (const text of ['Pete Batard', 'GNU General Public License', 'not an official Rufus release', 'Manrope', 'without warranty']) assert.ok(legal.includes(text), text);
  const privacy = read('public/en/privacy.html');
  for (const text of ['Firebase Hosting', 'GitHub Releases', 'clipboard', 'does not read', 'registry', 'analytics']) assert.ok(privacy.includes(text), text);
  const svg = read('public/assets/app-preview-en.svg');
  assert.match(svg, /not a screenshot/);
  assert.match(svg, /Drive Properties/);
  assert.ok(!/Ilustrasi|Perangkat|PILIH|SIAP/.test(svg));
  const sitemap = read('public/sitemap.xml');
  for (const p of pages.filter(p => p !== '404.html')) assert.ok(sitemap.includes(`https://nawam.shanna.id${route(p, 'en')}`));
  assert.ok(!sitemap.includes('/404.html'), 'Error pages should not enter sitemap');
});

const release = JSON.parse(read('public/release.json'));
async function runSite({lang = 'en', data = release, hash = '', clipboardFails = false, home = true, fetchFails = false} = {}) {
  const element = (attributes = {}) => ({
    attributes, disabled: true, textContent: 'static', listeners: {},
    getAttribute(name) { return this.attributes[name] ?? null; },
    setAttribute(name, value) { this.attributes[name] = value; },
    addEventListener(name, fn) { this.listeners[name] = fn; }
  });
  const ids = Object.fromEntries(['download-button', 'download-meta', 'release-hash', 'copy-hash', 'copy-status', 'faq'].map(id => [id, element()]));
  ids['download-button'].attributes.href = release.url;
  const links = [element({href: '/', lang: 'id'}), element({href: '/en/', lang: 'en'})];
  const events = {};
  let copied = null, fetches = 0;
  const location = {hash, pathname: lang === 'en' ? '/en/' : '/', origin: 'https://nawam.shanna.id'};
  const sandbox = {
    document: {
      documentElement: {lang},
      querySelector: selector => selector === '#download-button' && home ? ids['download-button'] : null,
      querySelectorAll: selector => selector === '[data-language-link]' ? links : [],
      getElementById: id => home ? ids[id] : null,
      addEventListener() {}
    },
    navigator: {clipboard: {async writeText(value) { if (clipboardFails) throw Error('denied'); copied = value; }}},
    window: {location, addEventListener: (name, fn) => { events[name] = fn; }}, location, URL,
    fetch: async () => { fetches++; if (fetchFails) throw Error('offline'); return {ok: true, json: async () => data}; }
  };
  runInNewContext(read('public/assets/site.js'), sandbox);
  await new Promise(resolve => setImmediate(resolve));
  return {ids, links, location, events, copied: () => copied, fetches: () => fetches};
}

test('download metadata and successful clipboard status follow html.lang', async () => {
  for (const [lang, download, version, status] of [
    ['en', 'Download Nawam for Windows', 'Version', 'Checksum copied.'],
    ['id', 'Unduh Nawam untuk Windows', 'Versi', 'Checksum berhasil disalin.']
  ]) {
    const state = await runSite({lang});
    assert.ok(state.ids['download-button'].textContent.startsWith(download));
    assert.ok(state.ids['download-meta'].textContent.startsWith(version));
    assert.equal(state.ids['release-hash'].textContent, release.sha256);
    assert.equal(state.ids['copy-hash'].disabled, false);
    await state.ids['copy-hash'].listeners.click();
    assert.equal(state.copied(), release.sha256);
    assert.equal(state.ids['copy-status'].textContent, status);
  }
});

test('clipboard permission failures have a localized manual-copy fallback', async () => {
  for (const [lang, expected] of [['en', /copy it manually/], ['id', /salin secara manual/]]) {
    const state = await runSite({lang, clipboardFails: true});
    await state.ids['copy-hash'].listeners.click();
    assert.match(state.ids['copy-status'].textContent, expected);
    assert.equal(state.copied(), null);
  }
});

test('release metadata fails closed for invalid fields and foreign or mismatched URLs', async () => {
  const cases = [null, [], {}, {...release, available: 'true'}, {...release, architecture: 'arm64'},
    ...[0, -1, 1.1, '5037056', null, Number.MAX_SAFE_INTEGER + 1].map(bytes => ({...release, bytes})),
    ...['', 'a'.repeat(63), 'G'.repeat(64), release.sha256 + '\n', null, [release.sha256]].map(sha256 => ({...release, sha256})),
    ...['9.9.9', '1.0.3\n', 101, null].map(version => ({...release, version})),
    ...[release.url.replace('github.com', 'github.com.evil.test'), release.url.replace('shannacore', 'other'),
      release.url.replace('/nawam/', '/another-repo/'), release.url.replace('https:', 'http:'),
      release.url.replace('/v1.0.3/', '/v9.9.9/'), release.url + '?redirect=evil', release.url + '#fragment',
      release.url.replace('github.com', 'user@github.com')].map(url => ({...release, url}))];
  for (const data of cases) {
    const state = await runSite({data});
    assert.equal(state.ids['copy-hash'].disabled, true, JSON.stringify(data));
    assert.equal(state.ids['download-meta'].textContent, 'static', JSON.stringify(data));
    assert.equal(state.ids['release-hash'].textContent, 'static');
  }
});

test('missing metadata keeps static links and non-download pages do not fetch it', async () => {
  const offline = await runSite({fetchFails: true});
  assert.equal(offline.ids['copy-hash'].disabled, true);
  assert.equal(offline.ids['download-button'].getAttribute('href'), release.url);
  assert.equal((await runSite({home: false})).fetches(), 0);
});

test('language links preserve existing simple fragments and update after hash changes', async () => {
  const state = await runSite({hash: '#faq'});
  assert.equal(state.links[1].getAttribute('href'), '/en/#faq');
  state.location.hash = '#unduh';
  state.ids.unduh = {};
  state.events.hashchange();
  assert.equal(state.links[0].getAttribute('href'), '/#unduh');
  state.location.hash = '#unknown';
  state.events.hashchange();
  assert.equal(state.links[1].getAttribute('href'), '/en/');
  state.location.hash = '#faq:~:text=private';
  state.events.hashchange();
  assert.equal(state.links[1].getAttribute('href'), '/en/');
});
