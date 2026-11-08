// freeway access site check, development sites filter, compare panel and PDF
const { chromium } = require('playwright'); const fs=require('fs'), path=require('path');
const [url,cdnFile,shots]=process.argv.slice(2); const cdn=JSON.parse(fs.readFileSync(cdnFile,'utf8'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms)); const res=[]; const check=(n,ok,d='')=>{res.push(!!ok);console.log(`${ok?'PASS':'FAIL'}  ${n}${d?'  ('+String(d).slice(0,240)+')':''}`)};
(async()=>{
 const b=await chromium.launch({args:['--use-gl=angle','--enable-unsafe-swiftshader']});
 const ctx=await b.newContext({viewport:{width:1440,height:900}});
 for(const [re,f] of Object.entries(cdn)) await ctx.route(new RegExp(re),r=>r.fulfill({path:f,contentType:'application/javascript',headers:{'Access-Control-Allow-Origin':'*'}}));
 await ctx.route(/arcgisonline|geocode\.arcgis/,r=>r.abort());
 const p=await ctx.newPage(); const errs=[]; p.on('pageerror',e=>errs.push(e.message)); p.on('console',m=>{if(m.type()==='error'&&!/Failed to (load|fetch)/.test(m.text()))errs.push(m.text())});
 const clk=sel=>p.$eval(sel,e=>e.click());
 await p.goto(url,{waitUntil:'load'}); await p.waitForFunction(()=>window.__app&&!document.getElementById('loading'),null,{timeout:240000});
 await sleep(2000);
 // development sites
 await p.$eval('#devAc',e=>{e.value='25';e.dispatchEvent(new Event('change'));});
 await p.$eval('#devChk',e=>{e.checked=true;e.dispatchEvent(new Event('change'));});
 await p.evaluate(()=>window.__app.setView(-95.10,29.75,10)); await sleep(9000);
 const lab=await p.textContent('#mLab'), cnt=await p.textContent('#mCount'), ids=await p.evaluate(()=>window.__app.layerIds());
 check('development sites filter (25+ acres): dots and count',ids.includes('dev-dots')&&/development sites/.test(lab)&&parseInt(cnt.replace(/,/g,''))>100,cnt+' '+lab);
 await p.screenshot({path:path.join(shots,'S1-devsites.png')});
 await p.$eval('#devChk',e=>{e.checked=false;e.dispatchEvent(new Event('change'));});
 // two sites into the shortlist, check freeway access
 const accts=['0011860000010','0480680000038'];
 for(const a of accts){
   await p.evaluate(a=>window.__app.openAccount(a,{fly:false}),a);
   await p.waitForFunction(()=>{const e=document.getElementById('siteChk'); return e&&/Freeway access/.test(e.innerText)&&/Road projects/.test(e.innerText);},null,{timeout:60000}).catch(()=>{});
   const sc=await p.evaluate(()=>document.getElementById('siteChk').innerText.replace(/\n/g,' | '));
   if(a===accts[0]) check('site check: freeway access minutes',/Freeway access \(truck\) \| \d+ min/.test(sc),sc.match(/Freeway[^|]*\|[^|]*/));
   await clk('#slAdd'); await sleep(300);
 }
 check('two sites shortlisted',(await p.evaluate(()=>window.__app.shortlist().length))===2);
 await p.evaluate(()=>window.__app.openCompare());
 await p.waitForFunction(()=>{const t=document.querySelector('#cmp table'); return t&&!/…/.test(t.innerText);},null,{timeout:60000}).catch(()=>{});
 const ct=await p.evaluate(()=>{const t=document.querySelector('#cmp table'); return {cols:t.querySelectorAll('thead td').length,text:t.innerText};});
 check('compare panel: 2 site columns, labor shed filled, access rows',ct.cols===2&&/Labor force\t\d/i.test(ct.text)&&/Freeway access\t\d+ min/i.test(ct.text)&&/Rate per \$100\t\d\.\d{4}/i.test(ct.text)&&/34 min; Bayport/.test(ct.text)&&!/&amp;/.test(ct.text),ct.text.split('\n').slice(0,4).join(' | '));
 await p.screenshot({path:path.join(shots,'S2-compare.png')});
 await p.evaluate(()=>document.body.classList.add('printing')); await p.emulateMedia({media:'print'});
 await p.pdf({path:path.join(shots,'compare.pdf'),landscape:true,printBackground:true});
 const sz=fs.statSync(path.join(shots,'compare.pdf')).size; check('compare prints to PDF',sz>20000,sz+' bytes');
 check('no script errors',errs.length===0,errs.slice(0,3).join(' | '));
 console.log(`${res.filter(Boolean).length}/${res.length} passed`); await b.close();
})();
