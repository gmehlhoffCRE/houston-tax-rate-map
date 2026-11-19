// multi-site: ctrl-click and Select mode add parcels, numbered pins, paste-a-list search, comparison (best values, reorder, remove), report
const { chromium } = require('playwright'); const fs=require('fs'), path=require('path');
const [url,cdnFile,shots]=process.argv.slice(2); const cdn=JSON.parse(fs.readFileSync(cdnFile,'utf8'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms)); const res=[]; const check=(n,ok,d='')=>{res.push(!!ok);console.log(`${ok?'PASS':'FAIL'}  ${n}${d?'  ('+String(d).slice(0,300)+')':''}`)};
(async()=>{
 const b=await chromium.launch({args:['--use-gl=angle','--enable-unsafe-swiftshader']});
 const ctx=await b.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1});
 for(const [re,f] of Object.entries(cdn)) await ctx.route(new RegExp(re),r=>r.fulfill({path:f,contentType:'application/javascript',headers:{'Access-Control-Allow-Origin':'*'}}));
 await ctx.route(/arcgisonline|geocode\.arcgis/,r=>r.abort());
 const p=await ctx.newPage(); const errs=[]; p.on('pageerror',e=>errs.push(e.message)); p.on('console',m=>{if(m.type()==='error'&&!/Failed to (load|fetch)/.test(m.text()))errs.push(m.text())});
 await p.addInitScript(()=>{ try{ localStorage.removeItem('taxmap.shortlist'); }catch(e){} });
 await p.goto(url,{waitUntil:'load'}); await p.waitForFunction(()=>window.__app&&!document.getElementById('loading'),null,{timeout:240000}); await sleep(1500);
 const n=()=>p.evaluate(()=>window.__app.shortlist().length);
 // 1. ctrl-click a parcel (deck.gl click gestures do not fire in headless Chrome, so call the parcel layer's click handler with the event it gets)
 const at=await p.evaluate(async()=>{ const r=await window.__app.getAccount('0011860000010'); window.__app.setView(r.lon,r.lat,17); await new Promise(z=>setTimeout(z,4500));
   const v=window.__app.deck().getViewports()[0], [x,y]=v.project([r.lon,r.lat]), m=document.getElementById('map').getBoundingClientRect(); return [m.left+x,m.top+y]; });
 const clickParcel=(x,y,mods)=>p.evaluate(([x,y,mods])=>{ const d=window.__app.deck(), m=document.getElementById('map').getBoundingClientRect(), o=d.pickObject({x:x-m.left,y:y-m.top,radius:2});
   if(!o||o.layer.id.indexOf('parcels')!==0) return null; let L=o.layer; while(L.parent) L=L.parent; L.props.onClick(o,{srcEvent:mods}); return o.object.properties.a; },[x,y,mods]);
 const a1=await clickParcel(at[0],at[1],{ctrlKey:true}); await sleep(1500);
 check('ctrl-click adds a parcel without opening it',a1&&await n()===1&&!(await p.$('.drawer .hero')),'shortlist '+(await n()));
 let ids=await p.evaluate(()=>window.__app.layerIds()); check('numbered pin drawn',ids.includes('sl-pins')&&ids.includes('sl-pin-n'));
 // 2. Select mode
 await p.click('#selBtn'); let a2=null;
 for(const [dx,dy] of [[60,50],[-60,50],[60,-50],[-60,-50],[90,0],[0,90],[-90,0],[0,-90],[120,80]]){ const a=await p.evaluate(([x,y])=>{ const d=window.__app.deck(), m=document.getElementById('map').getBoundingClientRect(), o=d.pickObject({x:x-m.left,y:y-m.top,radius:2}); return o&&o.layer.id.indexOf('parcels')===0?o.object.properties.a:null; },[at[0]+dx,at[1]+dy]);
   if(a&&a!==a1){ a2=await clickParcel(at[0]+dx,at[1]+dy,{}); break; } }
 await sleep(1500);
 const n2=await n(); check('Select mode click adds another parcel',n2===2,'shortlist '+n2);
 await p.click('#selBtn'); await p.screenshot({path:path.join(shots,'M1-pins.png')});
 // 3. paste a list
 const [addr,acct3]=await p.evaluate(async()=>{ const r=await window.__app.searchList('westpark'); const x=r.list.find(q=>/^\d+ /.test(q.addr||'')); const y=r.list.find(q=>q.acct!==x.acct&&/^\d+ /.test(q.addr||'')); return [x.addr,y.acct]; });
 await p.click('#slBtn'); await sleep(300); await p.click('#slList'); await sleep(300);
 await p.fill('#lsText',`${addr}, Houston, TX 77063\n1. ${acct3}\nzzzz qqqq nowhere 99999`); await p.click('#lsFind');
 await p.waitForSelector('#lsAdd',{timeout:60000}); const st=await p.$$eval('table.lst tbody tr',rs=>rs.map(r=>r.lastElementChild.innerText.split('\n')[0]));
 check('list search: two matched, one not found',st[0]==='Matched'&&st[1]==='Matched'&&st[2]==='Not found',st.join(' | '));
 await p.screenshot({path:path.join(shots,'M2-list.png')});
 await p.click('#lsAdd'); await sleep(800); const n3=await n(); check('list adds checked sites',n3>=3,'shortlist '+n3);
 // 4. comparison
 await p.click('#slCmp'); await p.waitForSelector('#cmp.open',{timeout:20000});
 await p.waitForFunction(()=>{ const s=window.__app.shortlist(); return s.every(x=>x.lon==null||Object.keys(x.checks||{}).length>3); },null,{timeout:120000}).catch(()=>{});
 await sleep(1500); const filled=await p.evaluate(()=>window.__app.shortlist().filter(x=>Object.keys(x.checks||{}).length>3).length);
 check('comparison fills site checks for sites never opened',filled>=3,filled+' sites with checks');
 const best=await p.$$eval('#cmp td.best',e=>e.length); check('best values highlighted',best>0,best+' cells');
 const first=await p.evaluate(()=>window.__app.shortlist()[0].acct);
 await p.click('#cmp [data-mv="0"][data-d="1"]'); await sleep(400);
 check('move right reorders the shortlist',await p.evaluate(a=>window.__app.shortlist()[1].acct===a,first));
 await p.screenshot({path:path.join(shots,'M3-compare.png'),fullPage:false});
 const before=await n(); await p.click(`#cmp [data-rm="${before-1}"]`); await sleep(400); check('remove drops a site',await n()===before-1);
 // 5. report
 await p.click('#cmpRpt'); await p.waitForSelector('.rpt .rpg',{timeout:240000});
 const pages=await p.$$eval('.rpt .rpg',e=>e.length), imgs=await p.$$eval('.rpt img',e=>e.map(i=>i.src.length));
 check('report: cover plus one page per site',pages===(await n())+1,pages+' pages');
 check('report: map pictures captured',imgs.length>=2&&imgs.every(l=>l>20000),imgs.join(','));
 const cov=await p.$eval('.rpt .cover',e=>e.innerText); check('cover matrix has key rows',/Rate per \$100/.test(cov)&&/Est. annual tax/.test(cov)&&/Fire station/.test(cov));
 const pg=await p.$eval('.rpt .rpg:nth-child(2)',e=>e.innerText); check('site page: taxing units and site checks',/Taxing unit/.test(pg)&&/Combined/.test(pg)&&/site checks/i.test(pg)&&/Nearest fire station/.test(pg));
 await p.fill('#rptFor','Acme Logistics'); await p.press('#rptFor','Tab'); await sleep(400);
 check('prepared-for appears on the cover',/Prepared for Acme Logistics/.test(await p.$eval('.rpt .cover',e=>e.innerText)));
 await p.screenshot({path:path.join(shots,'M4-report.png')});
 await p.$eval('.rpt .rpg:nth-child(2)',e=>e.scrollIntoView()); await sleep(300); await p.screenshot({path:path.join(shots,'M5-report-site.png')});
 // print layout: emulate print and check pages are separate
 await p.evaluate(()=>document.body.classList.add('printing','printing-rpt')); await p.emulateMedia({media:'print'});
 const pdf=await p.pdf({landscape:true,format:'Letter',printBackground:true,path:path.join(shots,'M6-report.pdf')}).catch(e=>null);
 check('PDF renders',!!pdf&&pdf.length>50000,pdf?pdf.length+' bytes':'failed');
 check('no script errors',errs.length===0,errs.join(' | '));
 console.log(`${res.filter(Boolean).length}/${res.length} passed`); await b.close();
})();
