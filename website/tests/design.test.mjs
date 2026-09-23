import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../public');
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
