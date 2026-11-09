// labor tool: detailed occupations by drive-time band, occupation map layer and picker, Compare rows
//   node labor_occ_check.js <page url> <cdn map json> <screenshot dir>
const { chromium } = require('playwright'); const fs=require('fs'), path=require('path');
const [url,cdnFile,shots]=process.argv.slice(2); const cdn=JSON.parse(fs.readFileSync(cdnFile,'utf8'));
const res=[]; const check=(n,ok,d='')=>{res.push(!!ok);console.log(`${ok?'PASS':'FAIL'}  ${n}${d?'  ('+String(d).slice(0,220)+')':''}`)};
(async()=>{
 const b=await chromium.launch({args:['--use-gl=angle','--enable-unsafe-swiftshader']});
 const ctx=await b.newContext({viewport:{width:1440,height:900}});
 for(const [re,f] of Object.entries(cdn)) await ctx.route(new RegExp(re),r=>r.fulfill({path:f,contentType:'application/javascript',headers:{'Access-Control-Allow-Origin':'*'}}));
 await ctx.route(/arcgisonline|geocode\.arcgis/,r=>r.abort());
 const p=await ctx.newPage(); const errs=[]; p.on('pageerror',e=>errs.push(e.message));
 await p.goto(url); await p.waitForFunction(()=>window.__app&&!document.getElementById('loading'),null,{timeout:240000});
 // drive time from the Ship Channel (Galena Park)
 await p.evaluate(()=>{ __app.DT.mode='car'; __app.dtRun(-95.23,29.74); });
 await p.waitForFunction(()=>document.getElementById('occDet'),null,{timeout:180000});
 await p.$eval('#occDet',e=>e.open=true); await p.waitForTimeout(300);
 const rows=await p.$$eval('#occDet tr',trs=>trs.map(r=>[...r.children].map(c=>c.textContent.trim())));
 const data=rows.filter(r=>r.length>=6&&r[0]!=='Lives within');
 check('occupation table lists the occupation groups',data.length>=17,data.length+' rows');
 const fk=data.find(r=>/Forklift/.test(r[0])); const num=s=>{ const m=/([\d.]+)(k|M)?/.exec(s||''); return m?(+m[1])*(m[2]==='M'?1e6:m[2]==='k'?1e3:1):0; };
 check('counts grow with drive time (forklift operators)',fk&&num(fk[1])>0&&num(fk[2])>=num(fk[1])&&num(fk[4])>=num(fk[3]),fk&&fk.join(' | '));
 check('pay column filled',data.every(r=>/\$\d+k/.test(r[5])),data.slice(0,3).map(r=>r[5]).join(','));
 const tr=data.find(r=>/Truck drivers/.test(r[0])); check('truck drivers counted',tr&&num(tr[4])>10000,tr&&tr.join(' | '));
 await p.screenshot({path:path.join(shots,'L1-occupations.png')});
 // map layer and picker
 await p.evaluate(()=>{ __app.setLayer('pumas',true); __app.renderLegend(); });
 await p.waitForFunction(()=>document.getElementById('occSel'),null,{timeout:60000});
 const leg1=await p.$eval('#layLeg',e=>e.innerText);
 check('occupation layer legend names the occupation',/Forklift and industrial truck operators per 1,000/.test(leg1),leg1.slice(0,120));
 await p.$eval('#occSel',s=>{ s.value=[...s.options].find(o=>o.text==='Welders, cutters and solderers').value; s.dispatchEvent(new Event('change')); }); await p.waitForTimeout(800);
 const leg2=await p.$eval('#layLeg',e=>e.innerText); check('picker switches the occupation',/Welders, cutters and solderers per 1,000/.test(leg2));
 await p.evaluate(()=>__app.setView(-95.3,29.78,9.6)); await p.waitForTimeout(6000);
 await p.screenshot({path:path.join(shots,'L2-occupation-layer.png')});
 // compare rows
 await p.evaluate(()=>{ __app.openAccount('1309900010004',{fly:false}); });
 await p.waitForTimeout(2500);
 await p.evaluate(()=>{ const b=document.getElementById('slAdd'); if(b) b.click(); });
 await p.evaluate(()=>__app.openCompare()); await p.waitForFunction(()=>/Forklift operators \(30 min\)/i.test(document.getElementById('cmp')?.innerText||''),null,{timeout:180000});
 await p.waitForFunction(()=>!/…/.test([...document.querySelectorAll('#cmp tr')].find(r=>/Forklift operators/i.test(r.innerText))?.innerText||'…'),null,{timeout:300000}).catch(()=>{});
 const crow=await p.evaluate(()=>[...document.querySelectorAll('#cmp tr')].find(r=>/Forklift operators/i.test(r.innerText))?.innerText||'');
 check('Compare shows occupation rows for 30 min',/\d/.test(crow.replace(/Forklift operators \(30 min\)/i,'')),crow.replace(/\s+/g,' '));
 check('no script errors',errs.length===0,errs.join(' | '));
 console.log(`${res.filter(Boolean).length}/${res.length} passed`); await b.close();
})();
