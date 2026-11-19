// tract layers: workers by job group (picker), population growth, drive-time population, site check line
const { chromium } = require('playwright'); const fs=require('fs'), path=require('path');
const [url,cdnFile,shots]=process.argv.slice(2); const cdn=JSON.parse(fs.readFileSync(cdnFile,'utf8'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms)); const res=[]; const check=(n,ok,d='')=>{res.push(!!ok);console.log(`${ok?'PASS':'FAIL'}  ${n}${d?'  ('+String(d).slice(0,260)+')':''}`)};
(async()=>{
 const b=await chromium.launch({args:['--use-gl=angle','--enable-unsafe-swiftshader']});
 const ctx=await b.newContext({viewport:{width:1440,height:900},deviceScaleFactor:2});
 for(const [re,f] of Object.entries(cdn)) await ctx.route(new RegExp(re),r=>r.fulfill({path:f,contentType:'application/javascript',headers:{'Access-Control-Allow-Origin':'*'}}));
 await ctx.route(/arcgisonline|geocode\.arcgis/,r=>r.abort());
 const p=await ctx.newPage(); const errs=[]; p.on('pageerror',e=>errs.push(e.message)); p.on('console',m=>{if(m.type()==='error'&&!/Failed to (load|fetch)/.test(m.text()))errs.push(m.text())});
 await p.goto(url,{waitUntil:'load'}); await p.waitForFunction(()=>window.__app&&!document.getElementById('loading'),null,{timeout:240000});
 await sleep(2000);
 const row=async re=>p.$$eval('#indLayers .lrow',(rs,src)=>{ const r=rs.find(x=>new RegExp(src).test(x.textContent)); if(r){ r.querySelector('input[type=checkbox]').click(); return true; } return false; },re);
 await p.click('button[data-tab="layers"]'); await sleep(400);   // the pickers live on the Layers tab
 check('job group layer row exists and turns on',await row('Workers by job group'));
 await p.evaluate(()=>window.__app.setView(-95.40,29.78,9.6)); await sleep(5000);
 let ids=await p.evaluate(()=>window.__app.layerIds());
 const leg1=await p.$eval('#layLeg',e=>e.innerText);
 check('job heat map drawn, legend shows worker counts',ids.includes('ind-jobs_tract-f')&&/Material moving/.test(leg1)&&/and up/.test(leg1),leg1.replace(/\n/g,' | '));
 check('picker visible',await p.isVisible('#jobSel'));
 await p.selectOption('#jobSel','health'); await sleep(1200);
 const leg2=await p.$eval('#layLeg',e=>e.innerText);
 check('picker switches job group and breaks',/Healthcare/.test(leg2)&&leg2!==leg1,leg2.split('\n').slice(0,4).join(' | '));
 await p.screenshot({path:path.join(shots,'T1-jobs.png')});
 await row('Workers by job group');
 check('population growth row turns on',await row('Population growth'));
 await sleep(2500); ids=await p.evaluate(()=>window.__app.layerIds());
 const leg3=await p.$eval('#layLeg',e=>e.innerText);
 check('growth map drawn with classes',ids.includes('ind-pop_growth-f')&&/More than doubled/.test(leg3),leg3.replace(/\n/g,' | '));
 await p.screenshot({path:path.join(shots,'T2-growth.png')});
 // drive time population
 await p.evaluate(()=>window.__app.dtRun(-95.55,29.85,'test')); await p.waitForFunction(()=>window.__app.DT.pop,null,{timeout:60000}).catch(()=>{});
 const dp=await p.evaluate(()=>window.__app.DT.pop);
 check('drive time population by band, growing outward',dp&&dp[0].p20>0&&dp[3].p20>dp[1].p20&&dp[3].p20>dp[3].p10,JSON.stringify(dp));
 const lab=await p.$eval('#dtLab',e=>e.innerText).catch(()=>'');
 check('drive time panel shows a Population table',/Population/.test(lab)&&/Growth since 2010/.test(lab));
 // site check line
 await p.evaluate(()=>window.__app.openAccount('0011860000010',{fly:false}));
 await p.waitForSelector('.dtabs button[data-dt="site"]',{timeout:60000}); await p.$eval('.dtabs button[data-dt="site"]',e=>e.click());
 await p.waitForFunction(()=>/Population growth/.test(document.getElementById('siteChk').innerText),null,{timeout:60000}).catch(()=>{});
 const sc=await p.evaluate(()=>document.getElementById('siteChk').innerText);
 check('site checks: population growth line',/Population growth\n.*(tract|New area)/.test(sc),(sc.match(/Population growth\n[^\n]*/)||[''])[0]);
 check('no script errors',errs.length===0,errs.join(' | '));
 console.log(`${res.filter(Boolean).length}/${res.length} passed`); await b.close();
})();
