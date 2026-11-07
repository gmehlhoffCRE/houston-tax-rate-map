// Browser check for the industrial layers and the drive-time tool (any build with layers embedded or served).
//   node layers_check.js http://localhost:8090/web/index.html <cdn map json> <screenshot dir>
// Turns every Industrial layer on (no script errors), then runs a real map click and car / truck drive times.
const { chromium } = require('playwright'); const fs=require('fs'), path=require('path');
const [url,cdnFile,shots]=process.argv.slice(2); const cdn=JSON.parse(fs.readFileSync(cdnFile,'utf8'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const res=[]; const check=(n,ok,d='')=>{res.push(ok);console.log(`${ok?'PASS':'FAIL'}  ${n}${d?'  ('+d+')':''}`)};
(async()=>{
 const b=await chromium.launch({args:['--use-gl=angle','--enable-unsafe-swiftshader']});
 const ctx=await b.newContext({viewport:{width:1440,height:900}});
 for(const [re,f] of Object.entries(cdn)) await ctx.route(new RegExp(re),r=>r.fulfill({path:f,contentType:'application/javascript',headers:{'Access-Control-Allow-Origin':'*'}}));
 const p=await ctx.newPage(); const errs=[];
 p.on('pageerror',e=>errs.push(e.message)); p.on('console',m=>{if(m.type()==='error'&&!/Failed to load resource/.test(m.text()))errs.push(m.text())});
 await p.goto(url,{waitUntil:'load'}); await p.waitForFunction(()=>window.__app&&!document.getElementById('loading'),null,{timeout:180000});
 await sleep(4000);
 const labels=await p.$$eval('#indLayers label',ls=>ls.map(l=>l.innerText.trim()));
 check('Industrial section lists 11 layers',labels.length===11,labels.join(' | '));
 // turn every layer on
 for(let i=0;i<labels.length;i++){ const on=await p.$eval(`#indLayers label:nth-child(${i+1}) input`,e=>e.checked); if(!on) await p.click(`#indLayers label:nth-child(${i+1})`); }
 await p.evaluate(()=>window.__app.setView(-95.05,29.68,11)); await sleep(15000);
 await p.screenshot({path:path.join(shots,'L1-all-layers-z11.png')});
 const ids=await p.evaluate(()=>{const d=window.__ovl?window.__ovl._deck:null; return null;});
 check('no script errors with all layers on',errs.filter(e=>!/Failed to fetch/.test(e)).length===0,errs.filter(e=>!/Failed to fetch/.test(e)).slice(0,3).join(' | '));
 await p.evaluate(()=>window.__app.setView(-95.03,29.73,14)); await sleep(12000);
 await p.screenshot({path:path.join(shots,'L2-all-layers-z14.png')});
 // drive time
 await p.click('#dtBtn'); await sleep(500);
 const vis=await p.$eval('#dtBar',e=>e.classList.contains('open'));
 check('drive time panel opens',vis);
 const box=await p.evaluate(()=>{const r=document.getElementById('map').getBoundingClientRect();return [r.x+r.width*0.5,r.y+r.height*0.5]});
 await p.evaluate(()=>window.__app.setView(-95.1,29.72,10)); await sleep(6000);
 await p.evaluate(()=>{const st=window.__app.state; for(const k in st.ind) st.ind[k]=false; window.__app.refresh();});
 await sleep(8000); await p.mouse.click(box[0],box[1]);
 await p.waitForFunction(()=>/drive time from/i.test(document.getElementById('dtMsg').textContent),null,{timeout:30000}).catch(()=>{});
 check('real click on the map starts a drive time (layers off)',/drive time from/i.test(await p.textContent('#dtMsg')),await p.textContent('#dtMsg'));
 await p.evaluate(()=>window.__app.dtRun(-95.075,29.70));
 await p.waitForFunction(()=>/drive time from/i.test(document.getElementById('dtMsg').textContent)||/unavailable|outside/i.test(document.getElementById('dtMsg').textContent),null,{timeout:60000}).catch(()=>{});
 const msg=await p.textContent('#dtMsg'); const ms=await p.evaluate(()=>window.__dtMs);
 check('car drive time computed',/Car drive time from/.test(msg),`${msg} | ${ms} ms`);
 await sleep(5000); await p.screenshot({path:path.join(shots,'L3-drivetime-car.png')});
 await p.click('#dtMode .mt[data-m="truck"]');
 await p.waitForFunction(()=>/Truck drive time from/.test(document.getElementById('dtMsg').textContent),null,{timeout:60000}).catch(()=>{});
 check('truck drive time computed',/Truck drive time from/.test(await p.textContent('#dtMsg')),String(await p.evaluate(()=>window.__dtMs))+' ms');
 await sleep(5000); await p.screenshot({path:path.join(shots,'L4-drivetime-truck.png')});
 check('no script errors at end',errs.filter(e=>!/Failed to fetch/.test(e)).length===0,errs.filter(e=>!/Failed to fetch/.test(e)).slice(0,3).join(' | '));
 await b.close(); console.log(`${res.filter(x=>x).length}/${res.length} passed`);
})();
