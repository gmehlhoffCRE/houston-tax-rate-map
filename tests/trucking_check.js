// trucking layers: TxDOT top 100 congested roads and hazmat routes (map, legend, hover card, site checks)
const { chromium } = require('playwright'); const fs=require('fs'), path=require('path');
const [url,cdnFile,shots]=process.argv.slice(2); const cdn=JSON.parse(fs.readFileSync(cdnFile,'utf8'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms)); const res=[]; const check=(n,ok,d='')=>{res.push(!!ok);console.log(`${ok?'PASS':'FAIL'}  ${n}${d?'  ('+String(d).slice(0,260)+')':''}`)};
(async()=>{
 const b=await chromium.launch({args:['--use-gl=angle','--enable-unsafe-swiftshader']});
 const ctx=await b.newContext({viewport:{width:1440,height:900},deviceScaleFactor:2});
 for(const [re,f] of Object.entries(cdn)) await ctx.route(new RegExp(re),r=>r.fulfill({path:f,contentType:'application/javascript',headers:{'Access-Control-Allow-Origin':'*'}}));
 await ctx.route(/arcgisonline|geocode\.arcgis/,r=>r.abort());
 const p=await ctx.newPage(); const errs=[]; p.on('pageerror',e=>errs.push(e.message)); p.on('console',m=>{if(m.type()==='error'&&!/Failed to (load|fetch)/.test(m.text()))errs.push(m.text())});
 await p.goto(url,{waitUntil:'load'}); await p.waitForFunction(()=>window.__app&&!document.getElementById('loading'),null,{timeout:240000}); await sleep(2000);
 const row=async re=>p.$$eval('#indLayers .lrow',(rs,src)=>{ const r=rs.find(x=>new RegExp(src).test(x.textContent)); if(r){ r.querySelector('input[type=checkbox]').click(); return true; } return false; },re);
 await p.click('button[data-tab="layers"]'); await sleep(400);
 check('congestion row turns on',await row('Most congested roads'));
 check('hazmat row turns on',await row('Hazmat truck routes'));
 await p.evaluate(()=>window.__app.setView(-95.30,29.76,10)); await sleep(5000);
 const ids=await p.evaluate(()=>window.__app.layerIds());
 check('both layers drawn',ids.includes('ind-congestion-l')&&ids.includes('ind-hazmat-l'),ids.filter(i=>/congestion|hazmat/.test(i)).join(','));
 const leg=await p.$eval('#layLeg',e=>e.innerText);
 check('legends: rank bands and hazmat classes',/Top 25 in Texas/.test(leg)&&/Hazmat prohibited/.test(leg)&&/hurricane warning/.test(leg),leg.replace(/\n/g,' | '));
 await p.screenshot({path:path.join(shots,'TR1-trucking.png')});
 // hover the #1 segment (W Loop / IH 610) at its middle vertex
 const pt=await p.evaluate(async()=>{ const d=window.__app.indData.congestion; const f=d.features.find(f=>f.properties.rank===1); const g=f.geometry, c=g.type==='LineString'?g.coordinates:g.coordinates[0], m=c[Math.floor(c.length/2)];
   window.__app.setView(m[0],m[1],13); await new Promise(r=>setTimeout(r,3500)); const v=window.__app.deck().getViewports()[0], [x,y]=v.project(m), r=document.getElementById('map').getBoundingClientRect(); return [r.left+x,r.top+y]; });
 await p.mouse.move(pt[0],pt[1]); await sleep(1200);
 const tip=await p.$eval('#tip',e=>e.innerText);
 check('hover card: rank, truck rank, delay, cost',/#1 most congested in Texas/.test(tip)&&/for trucks/.test(tip)&&/hours of delay per mile/.test(tip)&&/\$\d+M a year/.test(tip),tip.replace(/\n/g,' | '));
 await p.screenshot({path:path.join(shots,'TR2-hover.png')});
 // site checks near downtown (prohibited I-45 / US 59 segments, 610 through route)
 await p.evaluate(()=>window.__app.openAccount('0011860000010',{fly:false}));
 await p.waitForSelector('.dtabs button[data-dt="site"]',{timeout:60000}); await p.$eval('.dtabs button[data-dt="site"]',e=>e.click());
 await p.waitForFunction(()=>/Hazmat routes/.test(document.getElementById('siteChk').innerText),null,{timeout:60000}).catch(()=>{});
 const sc=await p.evaluate(()=>document.getElementById('siteChk').innerText);
 check('site check: congested roads line',/Most congested roads within 5 mi\n(#\d+|None)/.test(sc),(sc.match(/Most congested roads within 5 mi\n[^\n]*/)||[''])[0]);
 check('site check: hazmat line',/Hazmat routes\n(Through route|No designated)/.test(sc),(sc.match(/Hazmat routes\n[^\n]*(\n[^\n]*)?/)||[''])[0]);
 check('no script errors',errs.length===0,errs.join(' | '));
 console.log(`${res.filter(Boolean).length}/${res.length} passed`); await b.close();
})();
