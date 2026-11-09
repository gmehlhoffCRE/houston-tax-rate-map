// filter panel: Rate | Property | Map | Layers tabs, tab badges, Clear all, saved filter sets
//   node filter_tabs_check.js <page url> <cdn map json> <screenshot dir>
const { chromium } = require('playwright'); const fs=require('fs'), path=require('path');
const [url,cdnFile,shots]=process.argv.slice(2); const cdn=JSON.parse(fs.readFileSync(cdnFile,'utf8'));
const res=[]; const check=(n,ok,d='')=>{res.push(!!ok);console.log(`${ok?'PASS':'FAIL'}  ${n}${d?'  ('+String(d).slice(0,200)+')':''}`)};
(async()=>{
 const b=await chromium.launch({args:['--use-gl=angle','--enable-unsafe-swiftshader']});
 const ctx=await b.newContext({viewport:{width:1440,height:900}});
 for(const [re,f] of Object.entries(cdn)) await ctx.route(new RegExp(re),r=>r.fulfill({path:f,contentType:'application/javascript',headers:{'Access-Control-Allow-Origin':'*'}}));
 await ctx.route(/arcgisonline|geocode\.arcgis/,r=>r.abort());
 const p=await ctx.newPage(); const errs=[]; p.on('pageerror',e=>errs.push(e.message));
 let promptAnswer='Industrial under 2.4'; p.on('dialog',d=>d.type()==='prompt'?d.accept(promptAnswer):d.accept());
 await p.goto(url); await p.waitForFunction(()=>window.__app&&!document.getElementById('loading'),null,{timeout:240000});
 const vis=sel=>p.$eval(sel,e=>!e.closest('[hidden]')&&e.offsetParent!==null);
 const tabs=await p.$$eval('.tabs button',bs=>bs.map(b=>b.textContent.trim()));
 check('four tabs: Rate, Property, Map, Layers',tabs.join('|').replace(/\d/g,'')==='Rate|Property|Map|Layers',tabs.join('|'));
 check('Rate tab shows rate filters only',await vis('#rLo')&&!(await vis('#msType'))&&!(await vis('#shadeChk'))&&!(await vis('#indLayers')));
 await p.click('.tabs button[data-tab="prop"]'); check('Property tab shows property filters',await vis('#msType')&&await vis('#devChk')&&!(await vis('#rLo')));
 await p.click('.tabs button[data-tab="map"]'); check('Map tab: shading, counties, boundaries; saved row hidden',await vis('#shadeChk')&&await vis('#countyBox')&&!(await vis('#fsSel')));
 await p.click('.tabs button[data-tab="layers"]'); check('Layers tab: presets and groups',await vis('#presets')&&await vis('#indLayers'));
 const lay0=await p.$eval('#tbLayers',e=>e.textContent);
 await p.$eval('#presets button',e=>e.click()); await p.waitForTimeout(500);
 const lay1=await p.$eval('#tbLayers',e=>e.textContent); check('Layers badge counts layers that are on',+lay1>+lay0,lay0+' -> '+lay1);
 await p.screenshot({path:path.join(shots,'T1-layers-tab.png')});
 // property + rate filters
 await p.click('.tabs button[data-tab="prop"]');
 await p.evaluate(()=>{ __app.state.types=['Industrial']; document.querySelectorAll('.ms').forEach(m=>m._render&&m._render()); });
 await p.$eval('#devChk',e=>e.click());
 await p.click('.tabs button[data-tab="rate"]'); await p.fill('#rHi','2.4'); await p.press('#rHi','Enter'); await p.waitForTimeout(800);
 await p.evaluate(()=>applyFilters&&applyFilters()).catch(()=>{});
 const badges=await p.$$eval('.tabs .tb',e=>e.map(x=>x.textContent));
 check('Rate and Property badges count active filters',+badges[0]>=1&&+badges[1]>=2,badges.join(','));
 check('Clear all shows when filters are on',await vis('#fClearAll'));
 await p.screenshot({path:path.join(shots,'T2-rate-tab.png')});
 // save, clear, reapply
 await p.click('#fsSave'); await p.waitForTimeout(300);
 const opts=await p.$$eval('#fsSel option',o=>o.map(x=>x.textContent)); check('saved filter set listed',opts.includes('Industrial under 2.4'),opts.join('|'));
 await p.click('#fClearAll'); await p.waitForTimeout(800);
 const st=await p.evaluate(()=>({t:__app.state.types.length,dev:__app.state.dev.on,r:__app.state.rate,ind:Object.values(__app.state.ind).filter(Boolean).length}));
 check('Clear all resets rate, type and development sites, keeps layers',st.t===0&&!st.dev&&!(await vis('#fClearAll'))&&st.ind>=+lay1,JSON.stringify(st));
 await p.selectOption('#fsSel',{label:'Industrial under 2.4'}); await p.waitForTimeout(1500);
 const st2=await p.evaluate(()=>({t:__app.state.types,dev:__app.state.dev.on,hi:__app.state.rate[1]}));
 check('applying the saved set restores it',st2.t.includes('Industrial')&&st2.dev&&Math.abs(st2.hi-2.4)<0.011,JSON.stringify(st2));
 const reload=await ctx.newPage(); reload.on('dialog',d=>d.accept()); await reload.goto(url); await reload.waitForFunction(()=>window.__app&&!document.getElementById('loading'),null,{timeout:240000});
 check('saved sets survive a reload',(await reload.$$eval('#fsSel option',o=>o.map(x=>x.textContent))).includes('Industrial under 2.4'));
 await reload.close();
 await p.click('#fsDel'); await p.waitForTimeout(300);
 check('delete removes the saved set',!(await p.$$eval('#fsSel option',o=>o.map(x=>x.textContent))).includes('Industrial under 2.4'));
 // Tax rate / Land use stays lit after switching the rate basis
 await p.click('.tabs button[data-tab="rate"]'); await p.click('.pane .seg button[data-m="1"]'); await p.waitForTimeout(400);
 check('rate basis switch leaves the Tax rate button lit',await p.$eval('#colorSeg button[data-c="rate"]',e=>e.classList.contains('on')));
 check('no script errors',errs.length===0,errs.join(' | '));
 console.log(`${res.filter(Boolean).length}/${res.length} passed`); await b.close();
})();
