// jobs by industry (LEHD), business crime grid (Houston PD), fire stations, ETJ: map, pickers, hover, site checks
const { chromium } = require('playwright'); const fs=require('fs'), path=require('path');
const [url,cdnFile,shots]=process.argv.slice(2); const cdn=JSON.parse(fs.readFileSync(cdnFile,'utf8'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms)); const res=[]; const check=(n,ok,d='')=>{res.push(!!ok);console.log(`${ok?'PASS':'FAIL'}  ${n}${d?'  ('+String(d).slice(0,300)+')':''}`)};
(async()=>{
 const b=await chromium.launch({args:['--use-gl=angle','--enable-unsafe-swiftshader']});
 const ctx=await b.newContext({viewport:{width:1440,height:900},deviceScaleFactor:2});
 for(const [re,f] of Object.entries(cdn)) await ctx.route(new RegExp(re),r=>r.fulfill({path:f,contentType:'application/javascript',headers:{'Access-Control-Allow-Origin':'*'}}));
 await ctx.route(/arcgisonline|geocode\.arcgis/,r=>r.abort());
 const p=await ctx.newPage(); const errs=[]; p.on('pageerror',e=>errs.push(e.message)); p.on('console',m=>{if(m.type()==='error'&&!/Failed to (load|fetch)/.test(m.text()))errs.push(m.text())});
 await p.goto(url,{waitUntil:'load'}); await p.waitForFunction(()=>window.__app&&!document.getElementById('loading'),null,{timeout:240000}); await sleep(2000);
 const row=async re=>p.$$eval('#indLayers .lrow',(rs,src)=>{ const r=rs.find(x=>new RegExp(src).test(x.textContent)); if(r){ r.querySelector('input[type=checkbox]').click(); return true; } return false; },re);
 await p.click('button[data-tab="layers"]'); await sleep(400);
 // jobs by industry
 check('jobs by industry row turns on',await row('Jobs by industry'));
 await p.evaluate(()=>window.__app.setView(-95.40,29.78,9.6)); await sleep(5000);
 let ids=await p.evaluate(()=>window.__app.layerIds()); let leg=await p.$eval('#layLeg',e=>e.innerText);
 check('jobs map drawn, legend industrial',ids.includes('ind-wjobs-f')&&/Industrial \(manufacturing/.test(leg)&&/and up/.test(leg),leg.split('\n').slice(0,4).join(' | '));
 check('industry picker visible',await p.isVisible('#wjobsOpts select'));
 await p.selectOption('#wjobsOpts select','wm'); await sleep(1200); leg=await p.$eval('#layLeg',e=>e.innerText);
 check('picker switches to manufacturing',/^Manufacturing: jobs/m.test(leg),leg.split('\n').slice(0,2).join(' | '));
 await p.screenshot({path:path.join(shots,'S1-jobs.png')});
 await row('Jobs by industry');
 // crime
 check('crime row turns on',await row('Business crime'));
 await p.evaluate(()=>window.__app.setView(-95.37,29.76,10.2)); await sleep(5000);
 ids=await p.evaluate(()=>window.__app.layerIds()); leg=await p.$eval('#layLeg',e=>e.innerText);
 check('crime grid drawn',ids.includes('ind-crime-f'),ids.filter(i=>/crime/.test(i)).join(','));
 check('crime legend: classes, years, coverage',/Over 4x the Houston average/.test(leg)&&/2022 to 2024/.test(leg)&&/City of Houston only/.test(leg),leg.split('\n').slice(0,9).join(' | '));
 await p.screenshot({path:path.join(shots,'S2-crime.png')});
 const pt=await p.evaluate(async()=>{ const d=window.__app.indData.crime; const c=d.cells.filter(c=>c[2]>0).sort((a,b)=>b[2]-a[2])[200]; const m=[d.x0+(c[0]+.5)*d.dx,d.y0+(c[1]+.5)*d.dy];
   window.__app.setView(m[0],m[1],14); await new Promise(r=>setTimeout(r,3000)); const v=window.__app.deck().getViewports()[0], [x,y]=v.project(m), r=document.getElementById('map').getBoundingClientRect(); return [r.left+x,r.top+y]; });
 await p.mouse.move(pt[0],pt[1]); await sleep(1200); const tip=await p.$eval('#tip',e=>e.innerText);
 check('crime hover: incidents a year and multiple of average',/Business property crime/.test(tip)&&/incidents a year in this 1\/4-mile square/.test(tip)&&/Houston average/.test(tip),tip.replace(/\n/g,' | '));
 await p.selectOption('#crimeOpts select','a'); await sleep(1500); leg=await p.$eval('#layLeg',e=>e.innerText);
 check('crime picker: all crime',/All reported crime/.test(leg));
 await row('Business crime');
 // fire stations
 check('fire stations row turns on',await row('Fire stations'));
 await p.evaluate(()=>window.__app.setView(-95.40,29.78,9.4)); await sleep(4000);
 ids=await p.evaluate(()=>window.__app.layerIds()); const nf=await p.evaluate(()=>window.__app.indData.fire.features.length);
 check('fire stations drawn',ids.some(i=>/^ind-fire-/.test(i))&&nf>450,'stations '+nf);
 await p.screenshot({path:path.join(shots,'S3-fire.png')});
 // site checks (Houston parcel)
 await p.evaluate(()=>window.__app.openAccount('0011860000010',{fly:false}));
 await p.waitForSelector('.dtabs button[data-dt="site"]',{timeout:60000}); await p.$eval('.dtabs button[data-dt="site"]',e=>e.click());
 await p.waitForFunction(()=>/Nearest fire station/.test(document.getElementById('siteChk').innerText),null,{timeout:90000}).catch(()=>{});
 const sc=await p.evaluate(()=>document.getElementById('siteChk').innerText), line=re=>(sc.match(new RegExp(re+'\\n[^\\n]*'))||[''])[0].replace('\n',' => ');
 check('site check: fire station with drive time',/Nearest fire station\n.*(Station|FD).* mi · about \d+ min drive/.test(sc),line('Nearest fire station'));
 check('site check: business crime within 1 mi',/Business crime within 1 mi\n[\d,]+ incidents a year/.test(sc),line('Business crime within 1 mi'));
 check('site check: industrial jobs within 5 mi',/Industrial jobs within 5 mi\n[\d,]+ manufacturing/.test(sc),line('Industrial jobs within 5 mi'));
 // ETJ: a Katy-area parcel point check via the layer itself
 await p.click('button[data-tab="layers"]').catch(()=>{}); await sleep(300);
 check('ETJ row turns on',await row('City ETJs'));
 await p.evaluate(()=>window.__app.setView(-95.60,29.85,9.5)); await sleep(4000);
 const etj=await p.evaluate(()=>{ const d=window.__app.indData.etj; return d&&d.features?d.features.map(f=>f.properties.city):[]; });
 check('ETJs loaded for major cities',['Houston','Katy','Baytown','League City','Conroe','Pearland','Tomball'].every(c=>etj.includes(c)),etj.length+' cities');
 ids=await p.evaluate(()=>window.__app.layerIds()); check('ETJ outlines drawn',ids.some(i=>/^ind-etj-/.test(i)));
 await p.screenshot({path:path.join(shots,'S4-etj.png')});
 check('no script errors',errs.length===0,errs.join(' | '));
 console.log(`${res.filter(Boolean).length}/${res.length} passed`); await b.close();
})();
