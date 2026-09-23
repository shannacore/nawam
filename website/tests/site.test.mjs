import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = p => readFileSync(resolve(root, p), 'utf8');
test('landing page is complete and honest about availability', () => {
  assert.ok(existsSync(resolve(root, 'public/index.html')), 'Landing page must exist');
  const html = read('public/index.html');
  for (const id of ['fitur','cara-pakai','kompatibilitas','unduh','rilis','faq']) {
    assert.ok(html.includes(`id="${id}"`), id);
  }
  assert.match(html, /lang="id"/);
  assert.match(html, /nawam\.web\.app/);
  assert.match(html, /SHANNA Digital Systems/);
  assert.match(html, /data.*USB.*(terhapus|dihapus)/i);
  assert.match(html, /belum.*(digital|code.signing)/i);
  assert.ok(!html.includes('href="#"'), 'No dead placeholder links');
  for (const m of html.matchAll(/(?:src|href)="(\/[^"#?]*)"/g)) {
    const file = m[1].endsWith('/') ? `${m[1]}index.html` : m[1];
    assert.ok(existsSync(resolve(root, `public${file}`)), `Missing local asset ${file}`);
  }
});
test('only the public directory is deployed with safe headers', () => {
  const config = JSON.parse(read('firebase.json'));
  assert.equal(config.hosting.public, 'public');
  assert.equal(config.hosting.site, 'nawam');
  const h = config.hosting.headers.flatMap(x => x.headers);
  assert.ok(h.some(x => x.key === 'Content-Security-Policy' && x.value.includes("object-src 'none'")));
  assert.ok(h.some(x => x.key === 'X-Content-Type-Options' && x.value === 'nosniff'));
  assert.equal(config.hosting.rewrites, undefined, 'Missing assets must return real 404');
});
