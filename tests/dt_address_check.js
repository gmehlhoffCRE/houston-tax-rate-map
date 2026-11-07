const { chromium } = require('playwright'); const fs=require('fs'), path=require('path');
const [url,cdnFile,shots]=process.argv.slice(2); const cdn=JSON.parse(fs.readFileSync(cdnFile,'utf8'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms)); const res=[]; const check=(n,ok,d='')=>{res.push(ok);console.log(`${ok?'PASS':'FAIL'}  ${n}${d?'  ('+d+')':''}`)};
(async()=>{
 const b=await chromium.launch({args:['--use-gl=angle','--enable-unsafe-swiftshader']});
 const ctx=await b.newContext({viewport:{width:1440,height:900}});
 for(const [re,f] of Object.entries(cdn)) await ctx.route(new RegExp(re),r=>r.fulfill({path:f,contentType:'application/javascript',headers:{'Access-Control-Allow-Origin':'*'}}));
 let geoDown=false; const calls=[];
 await ctx.route(/geocode\.arcgis\.com/,r=>{const u=new URL(r.request().url()); calls.push(u.pathname.split('/').pop()+' '+(u.searchParams.get('text')||u.searchParams.get('SingleLine')));
   if(geoDown) return r.abort('connectionreset');
   const body=u.pathname.endsWith('suggest')?{suggestions:[{text:'Port Houston Turning Basin, Houston, TX, USA',magicKey:'abc',isCollection:false},{text:'Ports',magicKey:'x',isCollection:true}]}
     :{candidates:[{address:u.searchParams.get('SingleLine'),location:{x:-95.27,y:29.73},score:100}]};
   r.fulfill({body:JSON.stringify(body),contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'}});});
 const p=await ctx.newPage(); const errs=[]; p.on('pageerror',e=>errs.push(e.message));
 await p.goto(url,{waitUntil:'load'}); await p.waitForFunction(()=>window.__app&&!document.getElementById('loading'),null,{timeout:180000});
 await sleep(2000);
 await p.click('#dtBtn'); await sleep(300);
 check('address box shows in drive time panel',await p.isVisible('#dtQ'));
 // a real parcel address from the loaded data
 const addr=await p.evaluate(()=>{const EMB=window.__dt.emb(),C=EMB.cols; for(let i=0;i<EMB.n;i++){const r=EMB.row(i); if(/^\d+ \w+/.test(C.addr[i])&&r[9]!=null) return C.addr[i];}});
 const q=addr.split(' ').slice(0,3).join(' ');
 await p.fill('#dtQ',q); await p.waitForFunction(()=>document.querySelectorAll('#dtRes .sr').length>1,null,{timeout:60000}).catch(()=>{});
 const items=await p.$$eval('#dtRes .sr',x=>x.map(e=>e.innerText.replace(/\n/g,' / ')));
 check('typing shows parcel and Esri matches',items.some(t=>/Parcel ·/.test(t))&&items.some(t=>/Esri/.test(t)),`${q}: ${items.slice(0,3).join(' | ')}`);
 check('collection suggestions skipped',!items.some(t=>/^Ports \//.test(t)));
 await p.keyboard.press('Enter');
 await p.waitForFunction(()=>/drive time from/i.test(document.getElementById('dtMsg').textContent),null,{timeout:60000}).catch(()=>{});
 check('Enter picks the parcel and runs drive time',/Car drive time from .*\d/.test(await p.textContent('#dtMsg')),await p.textContent('#dtMsg'));
 // Esri suggestion click
 await p.fill('#dtQ','port houston turning'); await p.waitForFunction(()=>[...document.querySelectorAll('#dtRes .sr')].some(e=>/Turning Basin/.test(e.innerText)),null,{timeout:20000}).catch(()=>{});
 await p.click('#dtRes .sr:has-text("Turning Basin")');
 await p.waitForFunction(()=>/Turning Basin/.test(document.getElementById('dtMsg').textContent),null,{timeout:60000}).catch(()=>{});
 const o=await p.evaluate(()=>window.__app.DT.origin);
 check('Esri suggestion geocodes and runs',/Car drive time from Port Houston Turning Basin/.test(await p.textContent('#dtMsg'))&&o&&Math.abs(o[0]+95.27)<1e-6,JSON.stringify(o));
 await sleep(4000); await p.screenshot({path:path.join(shots,'A1-esri.png')});
 await p.click('#dtMode .mt[data-m="truck"]');
 await p.waitForFunction(()=>/Truck drive time from Port Houston/.test(document.getElementById('dtMsg').textContent),null,{timeout:60000}).catch(()=>{});
 check('truck keeps the address label',/Truck drive time from Port Houston/.test(await p.textContent('#dtMsg')));
 // typed address + Enter, no suggestion chosen, suggest offline -> findAddressCandidates
 geoDown=true; await p.fill('#dtQ','zzqx nowhere'); await sleep(900);
 const off=await p.textContent('#dtRes'); check('Esri offline message',/offline/i.test(off),off.slice(0,90));
 geoDown=false; await p.evaluate(()=>{window.__app; }); await p.fill('#dtQ',''); await p.evaluate(()=>{document.getElementById('dtQ').value='1 Main St, Houston';});
 await p.evaluate(()=>window.__dt.dtSubmit());
 await p.waitForFunction(()=>/1 Main St/.test(document.getElementById('dtMsg').textContent),null,{timeout:60000}).catch(()=>{});
 check('typed address with Enter geocodes',/Truck drive time from 1 Main St, Houston/.test(await p.textContent('#dtMsg')),await p.textContent('#dtMsg'));
 // drawer button
 await p.click('#dtClear');
 const acct=await p.evaluate(()=>{const EMB=window.__dt.emb(); for(let i=0;i<EMB.n;i++){const r=EMB.row(i); if(r[9]!=null&&r[2]) return r[0];}});
 await p.evaluate(a=>window.__app.openAccount?window.__app.openAccount(a,{}):null,acct);
 await p.waitForSelector('#dtHere',{timeout:20000}).catch(()=>{});
 const hasBtn=!!(await p.$('#dtHere')); check('drawer has Drive time from here',hasBtn,acct);
 if(hasBtn){ await p.click('#dtHere'); await p.waitForFunction(()=>/drive time from/i.test(document.getElementById('dtMsg').textContent),null,{timeout:60000}).catch(()=>{});
   check('drawer button runs drive time',/drive time from \d/.test(await p.textContent('#dtMsg')),await p.textContent('#dtMsg'));
   await sleep(3000); await p.screenshot({path:path.join(shots,'A2-drawer.png')}); }
 check('no script errors',errs.length===0,errs.slice(0,3).join(' | '));
 console.log(`${res.filter(Boolean).length}/${res.length} passed; geocoder calls: ${calls.length}`); await b.close();
})();
