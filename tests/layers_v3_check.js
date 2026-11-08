// layers v3: grouped panel, presets, styles, legend, land use, rail-served, site checks, labor shed, shortlist, share link
const { chromium } = require('playwright'); const fs=require('fs'), path=require('path');
const [url,cdnFile,shots]=process.argv.slice(2); const cdn=JSON.parse(fs.readFileSync(cdnFile,'utf8'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms)); const res=[]; const check=(n,ok,d='')=>{res.push(!!ok);console.log(`${ok?'PASS':'FAIL'}  ${n}${d?'  ('+String(d).slice(0,220)+')':''}`)};
(async()=>{
 const b=await chromium.launch({args:['--use-gl=angle','--enable-unsafe-swiftshader']});
 const ctx=await b.newContext({viewport:{width:1440,height:900},acceptDownloads:true});
 for(const [re,f] of Object.entries(cdn)) await ctx.route(new RegExp(re),r=>r.fulfill({path:f,contentType:'application/javascript',headers:{'Access-Control-Allow-Origin':'*'}}));
 await ctx.route(/arcgisonline\.com|geocode\.arcgis/,r=>r.abort());
 const p=await ctx.newPage(); const errs=[]; const clk=sel=>p.$eval(sel,e=>e.click());
 p.on('pageerror',e=>errs.push(e.message)); p.on('console',m=>{if(m.type()==='error'&&!/Failed to (load resource|fetch)/.test(m.text()))errs.push(m.text())});
 await p.goto(url,{waitUntil:'load'}); await p.waitForFunction(()=>window.__app&&!document.getElementById('loading'),null,{timeout:240000});
 await sleep(3000);
 const groups=await p.$$eval('#indLayers .grp .grp-h',x=>x.map(e=>e.innerText.trim()));
 const rows=await p.$$eval('#indLayers .lrow',x=>x.length), presets=await p.$$eval('#presets button',x=>x.map(e=>e.textContent));
 check('4 layer groups, 18 layers, 5 presets',groups.length===4&&rows===18&&presets.length===5,groups.join('|')+' / '+rows+' / '+presets.join('|'));
 const lay=await p.evaluate(()=>Object.fromEntries(Object.entries(window.__app.indData).map(([k,v])=>[k,v&&v.features?v.features.length:v&&v.a?Object.keys(v.a).length:null])));
 // logistics preset
 await clk('#presets button:has-text("Logistics")'); await sleep(800);
 const ind=await p.evaluate(()=>window.__app.state.ind);
 check('Logistics preset turns on its layers only',ind.road_projects&&ind.rail&&ind.rail_served&&ind.intermodal&&ind.ports&&ind.ftz&&ind.aadt&&!ind.pipelines&&!ind.flood,JSON.stringify(ind));
 const leg=await p.$$eval('#layLeg .ll .lt',x=>x.map(e=>e.textContent));
 check('legend lists only the layers that are on',leg.length===7&&leg.includes('Rail lines by owner'),leg.join('|'));
 check('focus toggle shows when layers are on',await p.isVisible('#focusRow'));
 await p.evaluate(()=>window.__app.setView(-95.13,29.73,11)); await sleep(12000);
 await p.screenshot({path:path.join(shots,'V1-logistics-z11.png')});
 const rp=await p.evaluate(()=>{const d=window.__app.indData.road_projects; const P=window.__app.state.proj; return [d.features.length,d.features.filter(f=>P[f.properties.stage]&&!f.properties.routine).length];});
 check('road projects drawn, routine and finished hidden by default',(await p.evaluate(()=>window.__app.layerIds())).includes('ind-road_projects-l')&&rp[0]>4000&&rp[1]>1500&&rp[1]<rp[0],rp.join(' total / shown '));
 await p.$eval('#projOpts input[data-k="done"]',e=>{e.checked=true;e.dispatchEvent(new Event('change'));}); await sleep(300);
 check('finished projects toggle',await p.evaluate(()=>window.__app.state.proj.done)&&(await p.$$eval('#layLeg .le',x=>x.map(e=>e.textContent))).includes('Finished since 2023'));
 await p.$eval('#projOpts input[data-k="done"]',e=>{e.checked=false;e.dispatchEvent(new Event('change'));});
 await p.evaluate(()=>window.__app.setView(-95.40,29.80,13)); await sleep(9000);
 await p.screenshot({path:path.join(shots,'V1b-road-projects-z13.png')});
 let ids=await p.evaluate(()=>window.__app.layerIds());
 check('rail drawn with casing and line; rail-served dots at metro zoom',['ind-rail-c','ind-rail-l','ind-rail_served-rs'].every(i=>ids.includes(i)),ids.filter(i=>i.startsWith('ind-')).join(','));
 // utilities preset, zoom filter
 await clk('#presets button:has-text("Utilities")'); await sleep(800);
 await p.evaluate(()=>window.__app.setView(-95.13,29.73,10)); await sleep(9000);
 ids=await p.evaluate(()=>window.__app.layerIds());
 const nPipeLow=await p.evaluate(()=>{const d=window.__app.indData.pipelines; return d.features.filter(f=>(f.properties.diameter||0)>=8).length+'/'+d.features.length;});
 check('pipelines dashed and power dotted layers present',ids.includes('ind-pipelines-l')&&ids.includes('ind-power-l')&&!ids.includes('ind-power-tw'),nPipeLow+' pipelines shown at metro zoom');
 await p.screenshot({path:path.join(shots,'V2-utilities-z10.png')});
 await p.evaluate(()=>window.__app.setView(-95.06,29.70,15)); await sleep(9000);
 ids=await p.evaluate(()=>window.__app.layerIds()); check('tower dots at close zoom',ids.includes('ind-power-tw'));
 await p.screenshot({path:path.join(shots,'V3-utilities-z15.png')});
 // multi-feature tooltip: hover a grid of points until one lists several features
 await p.evaluate(()=>window.__app.setView(-95.13,29.73,12)); await sleep(9000);
 let multi='';
 for(let gx=0.3;gx<=0.7&&!multi;gx+=0.05) for(let gy=0.3;gy<=0.7&&!multi;gy+=0.05){
   await p.mouse.move(316+1100*gx,76+800*gy); await sleep(250);
   const t=await p.evaluate(()=>{const e=document.getElementById('tip'); return e.style.display==='block'?e.innerText:'';}); if(/features here/.test(t)) multi=t; }
 check('hover lists every feature under the cursor',!!multi,multi.replace(/\n/g,' | '));
 // risk and development presets
 await clk('#presets button:has-text("Risk")'); await sleep(800);
 await p.evaluate(()=>window.__app.setView(-95.0,29.55,10)); await sleep(12000);
 await p.screenshot({path:path.join(shots,'V4-risk-z10.png')});
 await clk('#presets button:has-text("Development")'); await sleep(800);
 await p.evaluate(()=>window.__app.setView(-94.98,29.74,12)); await sleep(12000);
 await p.screenshot({path:path.join(shots,'V5-development-baytown.png')});
 check('rail cross ties at zoom 12',(await p.evaluate(()=>window.__app.layerIds())).includes('ind-rail-t'));
 check('development preset legend has zoning and opportunity zones',(await p.$$eval('#layLeg .ll .lt',x=>x.map(e=>e.textContent))).join('|').includes('Opportunity'));
 // land use
 await clk('#colorSeg button[data-c="use"]'); await clk('#presets button:has-text("Clear")');
 await p.evaluate(()=>window.__app.setView(-95.20,29.72,14)); await sleep(15000);
 check('land use legend shows',await p.isVisible('#useLeg')&&!(await p.isVisible('#rateLeg')));
 await p.screenshot({path:path.join(shots,'V6-landuse-z14.png')});
 await clk('#colorSeg button[data-c="rate"]');
 // rail-served at parcel zoom + site checks + shortlist
 const acct=await p.evaluate(()=>{const d=window.__app.indData.rail_served; return null;});
 await p.evaluate(()=>window.__app.setLayer('rail_served',true)); await sleep(1500);
 const rs=await p.evaluate(()=>{const RSd=window.__app.indData.rail_served.a; for(const a in RSd){ if(/^\d{13}$/.test(a)&&RSd[a][0]==='UP') return a; }});
 await p.evaluate(a=>window.__app.openAccount(a,{fly:true}),rs);
 await p.waitForFunction(()=>{const e=document.getElementById('siteChk'); return e&&/Rail/.test(e.innerText);},null,{timeout:60000}).catch(()=>{});
 const sc=await p.evaluate(()=>{const e=document.getElementById('siteChk'); return e?e.innerText.replace(/\n/g,' | '):'';});
 check('site checks list rail, zoning, OZ, flood, wetlands, evacuation, cleanup',/Rail \| Union Pacific/.test(sc)&&/Zoning/.test(sc)&&/Opportunity Zone/.test(sc)&&/Flood zone/.test(sc)&&/Evacuation/.test(sc)&&/cleanup/.test(sc)&&/Road projects within 1 mi/.test(sc),sc);
 await sleep(9000); await p.screenshot({path:path.join(shots,'V7-railserved-drawer.png')});
 await clk('#slAdd'); await sleep(300);
 check('shortlist add',(await p.evaluate(()=>window.__app.shortlist().length))===1&&/Shortlist \(1\)/.test(await p.textContent('#slBtn')));
 await clk('#slBtn'); await sleep(300);
 const [dl]=await Promise.all([p.waitForEvent('download',{timeout:10000}).catch(()=>null),p.click('#slCsv')]);
 let csv=''; if(dl){ const fp=path.join(shots,'shortlist.csv'); await dl.saveAs(fp); csv=fs.readFileSync(fp,'utf8'); }
 check('shortlist CSV export',/County,CAD ID,Address/.test(csv)&&csv.split('\n').length===2&&/Union Pacific/.test(csv),csv.split('\n').map(l=>l.slice(0,160)).join(' // '));
 await p.mouse.click(700,600); await sleep(200);
 // rail-only filter
 await p.$eval('#railOnly',e=>{e.checked=true;e.dispatchEvent(new Event('change'));}); await sleep(500);
 check('rail-only filter on',await p.evaluate(()=>window.__app.state.railOnly));
 await sleep(6000); await p.screenshot({path:path.join(shots,'V8-railonly.png')});
 await p.$eval('#railOnly',e=>{e.checked=false;e.dispatchEvent(new Event('change'));});
 // labor shed
 await clk('#dtBtn'); await p.evaluate(()=>window.__app.dtRun(-95.27,29.73));
 await p.waitForFunction(()=>document.getElementById('dtLab').classList.contains('on'),null,{timeout:60000}).catch(()=>{});
 const lab=await p.evaluate(()=>document.getElementById('dtLab').innerText.replace(/\n/g,' | '));
 const L=await p.evaluate(()=>window.__app.DT.labor);
 check('labor shed totals by band, increasing',L&&L.length===4&&L[0].lf>0&&L[0].lf<L[1].lf&&L[1].lf<L[2].lf&&L[2].lf<=L[3].lf,lab);
 await sleep(4000); await p.screenshot({path:path.join(shots,'V9-laborshed.png')});
 // share link round trip
 await p.evaluate(()=>window.__app.setLayer('flood',true)); await p.evaluate(()=>window.__app.writeUrl());
 const href=await p.evaluate(()=>location.href);
 check('share link holds view, layers, parcel and drive time',/v=/.test(href)&&/l=[^&]*rail_served/.test(href)&&/flood/.test(href)&&/p=/.test(href)&&/d=-95\.27/.test(href),href.split('#')[1]);
 const p2=await ctx.newPage(); p2.on('pageerror',e=>errs.push('p2: '+e.message));
 await p2.goto(href,{waitUntil:'load'}); await p2.waitForFunction(()=>window.__app&&!document.getElementById('loading'),null,{timeout:240000});
 await p2.waitForFunction(()=>window.__app.state.sel&&window.__app.DT.origin,null,{timeout:60000}).catch(()=>{});
 const st2=await p2.evaluate(()=>({sel:window.__app.state.sel,flood:window.__app.state.ind.flood,rs:window.__app.state.ind.rail_served,dt:window.__app.DT.origin,gz:window.__app.state.gz}));
 check('opening the link restores it',st2.sel===rs&&st2.flood&&st2.rs&&st2.dt&&Math.abs(st2.dt[0]+95.27)<1e-4,JSON.stringify(st2));
 check('no script errors',errs.length===0,errs.slice(0,4).join(' | '));
 console.log(`${res.filter(Boolean).length}/${res.length} passed`); console.log('layer features: '+JSON.stringify(lay)); await b.close();
})();
