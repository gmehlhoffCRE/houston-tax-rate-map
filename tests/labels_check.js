// reference labels: highways and place names drawn above the shading, Labels toggle, Hybrid swap
const { chromium } = require('playwright'); const fs=require('fs'), path=require('path');
const [url,cdnFile,shots]=process.argv.slice(2); const cdn=JSON.parse(fs.readFileSync(cdnFile,'utf8'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms)); const res=[]; const check=(n,ok,d='')=>{res.push(!!ok);console.log(`${ok?'PASS':'FAIL'}  ${n}${d?'  ('+String(d).slice(0,240)+')':''}`)};
(async()=>{
 const b=await chromium.launch({args:['--use-gl=angle','--enable-unsafe-swiftshader']});
 const ctx=await b.newContext({viewport:{width:1440,height:900},deviceScaleFactor:2});
 for(const [re,f] of Object.entries(cdn)) await ctx.route(new RegExp(re),r=>r.fulfill({path:f,contentType:'application/javascript',headers:{'Access-Control-Allow-Origin':'*'}}));
 await ctx.route(/arcgisonline|geocode\.arcgis/,r=>r.abort());
 const p=await ctx.newPage(); const errs=[]; p.on('pageerror',e=>errs.push(e.message)); p.on('console',m=>{if(m.type()==='error'&&!/Failed to (load|fetch)/.test(m.text()))errs.push(m.text())});
 await p.goto(url,{waitUntil:'load'}); await p.waitForFunction(()=>window.__app&&!document.getElementById('loading'),null,{timeout:240000});
 await sleep(6000);
 let ids=await p.evaluate(()=>window.__app.layerIds());
 check('home view: highway lines, route labels and place names',['ref-hwy','ref-hwy-shield','ref-places'].every(i=>ids.includes(i)),ids.filter(i=>/^ref/.test(i)).join(','));
 const ord=ids.indexOf('ref-places')>ids.indexOf('parcels')||!ids.includes('parcels');
 check('labels drawn above the rate shading',ord&&ids.indexOf('ref-hwy-shield')>ids.findIndex(i=>/zones|parcel/.test(i)),ids.slice(0,6).join(','));
 await p.screenshot({path:path.join(shots,'L1-home.png')});
 await p.evaluate(()=>window.__app.setView(-95.45,29.80,10)); await sleep(5000);
 await p.screenshot({path:path.join(shots,'L2-z10.png')});
 await p.$eval('#lblBtn',e=>e.click()); await sleep(800);
 ids=await p.evaluate(()=>window.__app.layerIds());
 check('Labels button hides them',!ids.some(i=>/^ref-/.test(i))&&(await p.getAttribute('#lblBtn','aria-pressed'))==='false');
 await p.$eval('#lblBtn',e=>e.click()); await sleep(500);
 await p.$eval('#mtBar .mt[data-t="hybrid"]',e=>e.click()); await sleep(800);
 ids=await p.evaluate(()=>window.__app.layerIds());
 check('Hybrid: Esri labels above data, ours hidden',ids.some(i=>/World_Transportation/.test(i))&&!ids.includes('ref-places')&&ids.indexOf(ids.find(i=>/World_Transportation/.test(i)))>ids.findIndex(i=>/zones|parcel/.test(i)),ids.filter(i=>/base|ref|World/.test(i)).join(','));
 check('no script errors',errs.length===0,errs.join(' | '));
 console.log(`${res.filter(Boolean).length}/${res.length} passed`); await b.close();
})();
