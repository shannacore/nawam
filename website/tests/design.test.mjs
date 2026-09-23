import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../public');
test('hero uses unmodified real screenshot in both languages',()=>{
  const image=readFileSync(resolve(root,'assets/nawam-original.png'));
  assert.equal(createHash('sha256').update(image).digest('hex'),
    'e95e4efcfd7adf3c9b28c7ec1afb069aba7f1949bc2b633e5f3c1c2e9e768b4e');
  for(const file of ['index.html','en/index.html']){
    const html=readFileSync(resolve(root,file),'utf8');
    assert.ok(html.includes('src="/assets/nawam-original.png"'));
    assert.ok(!html.includes('app-preview'));
    assert.ok(!html.includes('Vector preview'));
    assert.ok(html.includes('width="415" height="536"'));
  }
});
test('header is not sticky and language controls are flag-only',()=>{
  const css=readFileSync(resolve(root,'assets/i18n.css'),'utf8');
  assert.ok(css.includes('.header{position:relative;'));
  for(const locale of ['', 'en/']) for(const file of ['index.html','privacy.html','open-source.html','download-status.html','404.html']) {
    const html=readFileSync(resolve(root,locale+file),'utf8');
    const footer=html.split('<footer')[1];
    assert.ok(!footer.includes('Developed by'));
    assert.ok(!footer.includes('Bootable USB Creator'));
    assert.equal([...html.matchAll(/data-language-link/g)].length,1);
    assert.ok(html.includes(`/assets/flag-${locale ? 'en' : 'id'}.svg`));
    assert.ok(!html.includes('>Indonesia</a>'));
    assert.ok(!html.includes('>English</a>'));
    assert.ok(html.includes('data-current-language='));
  }
});
test('new light design uses requested palette and shared pages',()=>{
  assert.ok(existsSync(resolve(root,'assets/design.css')),'Light design must exist');
  const css=readFileSync(resolve(root,'assets/design.css'),'utf8').toLowerCase();
  for(const color of ['#ffffff','#2563eb','#f8fafc','#06b6d4','#0f172a','#1d4ed8']) assert.ok(css.includes(color),color);
  assert.match(css,/color-scheme:\s*light/);
  for(const locale of ['', 'en/']) for(const file of ['index.html','privacy.html','open-source.html','download-status.html','404.html']) {
    const html=readFileSync(resolve(root,locale+file),'utf8');
    assert.ok(html.includes('/assets/design.css'),locale+file);
    assert.ok(!html.includes('/assets/readability.css'), 'No stacked legacy themes');
    assert.ok(html.includes('/assets/nawam.svg'),'Original USB logo preserved');
  }
});
