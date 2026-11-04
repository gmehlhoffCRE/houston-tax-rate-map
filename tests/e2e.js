// End-to-end check of the built page in headless Chromium (Playwright).
//   node e2e.js http://localhost:8090/web/index.html <screenshot dir> [cdn map json]
// The optional cdn map ({"url regex": "local file"}) serves CDN scripts from disk when the CDN is unreachable.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const [url, shots = '.', cdnMapFile] = process.argv.slice(2);
const cdnMap = cdnMapFile ? JSON.parse(fs.readFileSync(cdnMapFile, 'utf8')) : {};
const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  (' + detail + ')' : ''}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--enable-unsafe-swiftshader'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const errors = [], failed = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
  page.on('requestfailed', r => { if (!/ERR_ABORTED/.test(r.failure() && r.failure().errorText)) failed.push(r.url()); });
  for (const [re, file] of Object.entries(cdnMap)) {
    await context.route(new RegExp(re), r => r.fulfill({ path: file, contentType: 'application/javascript', headers: { 'Access-Control-Allow-Origin': '*' } }));
  }
  const shot = async name => page.screenshot({ path: path.join(shots, name + '.png') });
  const drawerText = () => page.evaluate(() => document.getElementById('drawerHost').innerText);
  const waitIdle = async (ms = 2500) => { await sleep(ms); };
  // wait until the footer reflects the current zoom mode and has a nonzero count (rendering can be slow headless)
  const waitFoot = async (re, ms = 30000) => page.waitForFunction(r => new RegExp(r).test(document.getElementById('mFoot').innerText) && !/^0\s/.test(document.getElementById('mFoot').innerText.trim()), re.source, { timeout: ms }).catch(() => {});
  const waitDrawer = async (re, ms = 20000) => page.waitForFunction(r => new RegExp(r, 'i').test(document.getElementById('drawerHost').innerText), re.source, { timeout: ms }).catch(() => {});
  const waitResults = async (ms = 10000) => page.waitForFunction(() => document.querySelector('#sres.open'), null, { timeout: ms }).catch(() => {});

  await page.goto(url, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__app && !document.getElementById('loading'), null, { timeout: 30000 });
  await waitIdle(10000);
  await shot('01-county');
  check('page boots without script errors', errors.length === 0, errors.slice(0, 3).join(' | '));
  const status = await page.textContent('#statusTxt');
  check('status shows rate year, value year, account count', /2025 RATES · 2026 VALUES · [\d,]+ ACCOUNTS/.test(status), status);

  // zoom to parcel level over the Ship Channel
  await page.evaluate(() => window.__app.setView(-95.175, 29.72, 14)); await waitFoot(/parcels in view match/); await waitIdle(1500);
  await shot('02-parcels-z14');
  const foot = await page.textContent('#mFoot');
  check('parcel mode footer counts parcels in view', /parcels in view match/.test(foot) && !/^0 /.test(foot.trim()), foot.trim());

  // search by owner name
  await page.fill('#q', 'pasadena refining'); await waitResults();
  const res1 = await page.$$eval('#sres .sr', els => els.map(e => e.innerText.replace(/\n/g, ' | ')));
  check('owner search finds Pasadena Refining', res1.some(t => /0281700000001/.test(t)), res1[0]);
  await page.keyboard.press('Enter'); await waitDrawer(/1\.9557/); await waitIdle(4000);
  let d = await drawerText();
  check('acceptance: 0281700000001 shows rate 1.9557', /1\.9557/.test(d) && /Pasadena ISD/i.test(d) && /Unincorporated/.test(d), d.split('\n').slice(0, 8).join(' / '));
  await shot('03-search-owner');

  // search by account number
  await page.fill('#q', '0402040000009'); await waitResults();
  await page.keyboard.press('Enter'); await waitDrawer(/TIRZ/); await waitIdle(4000);
  d = await drawerText(); console.log('   drawer:', d.replace(/\n/g,' / ').slice(0, 300));
  check('acceptance: 0402040000009 shows 2.1252 with TIRZ Eastside', /2\.1252/.test(d) && /TIRZ/i.test(d) && /Eastside/i.test(d), (d.match(/TIRZ[^\n]*/) || [''])[0]);
  await shot('04-search-account');

  // account with blank values (no CAMA or rate record) must still load
  const blank = await page.evaluate(() => window.__app.getAccount('1042940000003').then(r => r && r.acct).catch(e => 'error ' + e.message));
  check('account record with blank values loads', blank === '1042940000003', String(blank));

  // search by address
  await page.fill('#q', '431 n preston'); await waitResults();
  const res3 = await page.$$eval('#sres .sr', els => els.map(e => e.innerText.replace(/\n/g, ' | ')));
  check('address search finds 431 N Preston Rd', res3.some(t => /431 N PRESTON/i.test(t)), res3[0]);
  await page.keyboard.press('Escape');

  // partial account number
  await page.fill('#q', '040218001'); await waitResults();
  const res4 = await page.$$eval('#sres .sr', els => els.length);
  check('partial account number lists matches', res4 > 0, res4 + ' results');
  await page.keyboard.press('Escape');

  // most common combo
  const common = await page.evaluate(async () => {
    const c = window.__app.combos.find(c => c.isd === 'HOUSTON ISD' && c.city === 'CITY OF HOUSTON' && !c.water && !c.mg && !c.tirz && !c.esd);
    return c ? { id: c.id, isd: c.isd, city: c.city, college: c.college, b: c.b } : {};
  });
  check('acceptance: most common combo (HISD + City of Houston) is 2.1252', Math.abs(common.b - 2.12522) < 1e-5 && /HOUSTON ISD/.test(common.isd), JSON.stringify(common));

  // click a parcel on the map
  await page.evaluate(() => { window.__app.state.sel = null; document.getElementById('drawerHost').innerHTML = ''; window.__app.setView(-95.2118, 29.7206, 16); });
  await waitFoot(/parcels in view match/); await waitIdle(3000);
  // find a screen point that has a parcel under it (the view center can fall on a street)
  const box = await page.evaluate(() => {
    const r = document.getElementById('map').getBoundingClientRect();
    const d = window.__ovl ? window.__ovl._deck : null;
    if (d) { for (let gy = 0.3; gy <= 0.7; gy += 0.05) for (let gx = 0.3; gx <= 0.7; gx += 0.05) {
      const o = d.pickObject({ x: r.width * gx, y: r.height * gy });
      if (o && o.object && o.object.properties && o.object.properties.a) return [r.x + r.width * gx, r.y + r.height * gy]; } }
    return [r.x + r.width / 2, r.y + r.height / 2];
  });
  await page.mouse.move(box[0] - 30, box[1] - 30); await page.mouse.move(box[0], box[1]);
  await page.waitForFunction(() => document.getElementById('tip').style.display === 'block', null, { timeout: 20000 }).catch(() => {});
  const tipShown = await page.$eval('#tip', e => e.style.display === 'block' ? e.innerText : '');
  check('hover tooltip shows rate', /per \$100/.test(tipShown), tipShown.replace(/\n/g, ' / '));
  await page.mouse.click(box[0], box[1]); await waitDrawer(/HCAD account/); await waitIdle(1000);
  d = await drawerText();
  check('clicking a parcel opens the drawer', /RATE \/ \$100|Rate \/ \$100/i.test(d) && /HCAD account/i.test(d), d.split('\n').slice(0, 3).join(' / '));
  await shot('05-click-parcel');

  // shading off
  await page.click('#shadeBtn'); await waitIdle(8000);
  await shot('06-shading-off');
  check('shading toggle turns off', await page.evaluate(() => !window.__app.state.shade));
  await page.click('#shadeBtn'); await waitIdle(1000);

  // filter: industrial only
  await page.evaluate(() => { document.getElementById('drawerHost').innerHTML = ''; window.__app.setView(-95.175, 29.72, 14); });
  await waitFoot(/parcels in view match/); await waitIdle(4000);
  const before = await page.textContent('#mCount');
  await page.click('#msType .ms-btn'); await page.click('#msType .ms-opt[data-o="Industrial"]'); await page.keyboard.press('Escape');
  await waitIdle(8000);
  const after = await page.textContent('#mCount');
  check('property type filter reduces matches', +after.replace(/,/g, '') < +before.replace(/,/g, '') && +after.replace(/,/g, '') > 0, `${before} -> ${after}`);
  await shot('07-filter-industrial');
  await page.click('#fClear'); await waitIdle(1500);

  // county view histogram (zones)
  await page.evaluate(() => window.__app.setView(-95.175, 29.72, 11)); await waitFoot(/accounts countywide match/); await waitIdle(6000);
  const foot2 = await page.textContent('#mFoot');
  check('zoomed out footer counts accounts countywide', /accounts countywide match/.test(foot2), foot2.trim());
  await shot('08-zones-z11');

  // smoothness: frames during continuous panning at parcel zoom
  await page.evaluate(() => window.__app.setView(-95.175, 29.72, 15)); await waitIdle(8000);
  const fps = await page.evaluate(async () => {
    const g = document.querySelector('#map');
    let frames = 0, worst = 0, last = performance.now(); const t0 = last;
    await new Promise(res => { const step = now => { frames++; worst = Math.max(worst, now - last); last = now;
      if (now - t0 < 3000) requestAnimationFrame(step); else res(); }; requestAnimationFrame(step);
      const iv = setInterval(() => { try { const m = window.__gmap; if (m) m.panBy(12, 4); } catch (e) {} }, 16); setTimeout(() => clearInterval(iv), 3000); });
    return { fps: frames / 3, worstMs: Math.round(worst) };
  });
  console.log('INFO  pan frame rate under headless software GL (not representative of a GPU):', JSON.stringify(fps));

  check('no failed requests to app data', !failed.some(u => /pmtiles|shards|data\//.test(u)), failed.filter(u => /pmtiles|shards|data\//.test(u)).slice(0, 3).join(' '));
  check('no script errors during the run', errors.length === 0, errors.slice(0, 3).join(' | '));
  const unrouted = failed.filter(u => !/pmtiles|shards|data\//.test(u));
  if (unrouted.length) console.log('other failed requests:', [...new Set(unrouted.map(u => u.split('?')[0]))].slice(0, 6).join('\n  '));
  fs.writeFileSync(path.join(shots, 'e2e-results.json'), JSON.stringify(results, null, 1));
  await browser.close();
  process.exit(results.every(r => r.ok) ? 0 : 1);
})();
