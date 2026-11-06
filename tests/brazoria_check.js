// Browser check for a Brazoria build (Brazoria-only or all counties): boot, county toggle, BCAD property id search,
// card rate and labels, owner search.
//   node brazoria_check.js http://localhost:8090/web/index.html <screenshot dir> <cdn map json>
// The cdn map ({"url regex": "local file"}) serves deck.gl, pmtiles and the MVT worker from npm copies when
// the CDNs are blocked. Basemap tile errors (Esri host blocked in the sandbox) fail the two "no script errors"
// checks there; everything else should pass.
// Expected: B600116 (Pearland Town Center) = county 0.262548 + road & bridge 0.04221 + Alvin ISD 1.15
// + City of Pearland 0.63 + drainage district 4 0.113276 + Alvin College 0.156543 = 2.3546, plus Pearland MMD 2
// 0.06598 with "Incl. mgmt districts" (see data/br_combos.csv); B500027 = 2.8546.
const { chromium } = require('playwright');
const fs=require('fs'), path=require('path');
const [url, shots, cdnFile] = process.argv.slice(2);
const cdn = JSON.parse(fs.readFileSync(cdnFile,'utf8'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const res=[]; const check=(n,ok,d='')=>{res.push(ok);console.log(`${ok?'PASS':'FAIL'}  ${n}${d?'  ('+d+')':''}`)};
(async()=>{
  const b=await chromium.launch({args:['--use-gl=angle','--enable-unsafe-swiftshader']});
  const ctx=await b.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1});
  for(const [re,f] of Object.entries(cdn)) await ctx.route(new RegExp(re),r=>r.fulfill({path:f,contentType:'application/javascript',headers:{'Access-Control-Allow-Origin':'*'}}));
  const p=await ctx.newPage(); const errs=[];
  p.on('pageerror',e=>errs.push(e.message)); p.on('console',m=>{if(m.type()==='error'&&!/Failed to load resource/.test(m.text()))errs.push(m.text())});
  await p.goto(url,{waitUntil:'load'});
  await p.waitForFunction(()=>window.__app&&!document.getElementById('loading'),null,{timeout:60000});
  await sleep(8000);
  check('boots without script errors',errs.length===0,errs.slice(0,3).join(' | '));
  check('status',true,await p.textContent('#statusTxt'));
  const counties=await p.evaluate(()=>[...document.querySelectorAll('#countyBox label')].map(l=>l.innerText.replace(/\s+/g,' ').trim()));
  check('county toggles list Brazoria',counties.some(t=>/Brazoria County/.test(t)),counties.join(' | '));
  await p.evaluate(()=>window.__app.setView(-95.45,29.2,10)); await sleep(12000);
  await p.screenshot({path:path.join(shots,'b1-county.png')});
  const ask=async(q,re,name)=>{
    await p.fill('#q',''); await p.type('#q',q,{delay:20});
    await p.waitForFunction(()=>document.querySelector('#sres.open'),null,{timeout:20000}).catch(()=>{});
    await sleep(800);
    const items=await p.evaluate(()=>[...document.querySelectorAll('#sres .sr')].map(e=>e.innerText.replace(/\s+/g,' ')));
    check(`search "${q}" finds it`,items.some(t=>re.test(t)),items.slice(0,3).join(' | '));
    const i=items.findIndex(t=>re.test(t)); if(i<0) return '';
    await p.click(`#sres .sr[data-i="${i}"]`);
    await p.waitForFunction(()=>/Rate \/ \$100/.test(document.getElementById('drawerHost').innerText),null,{timeout:20000}).catch(()=>{});
    await sleep(6000); await p.screenshot({path:path.join(shots,name+'.png')});
    return p.evaluate(()=>document.getElementById('drawerHost').innerText);
  };
  let d=await ask('600116',/BCAD 600116/,'b2-card-600116');
  check('card B600116 rate 2.3546',/2\.3546/.test(d),d.match(/Rate \/ \$100\s*([\d.]+)/)?.[1]);
  check('card shows Brazoria County and BCAD property ID 600116',/Brazoria County/.test(d)&&/BCAD property ID\s*600116/i.test(d));
  check('card Brazoria note',/Brazoria CAD/.test(d));
  check('card has building area',/367,766 SF/.test(d));
  check('card breakdown has Alvin ISD and City of Pearland',/Alvin Independent/i.test(d)&&/City Of Pearland/i.test(d));
  check('card notes Pearland MMD 2 (mgmt)',/Pearland Municipal Management/i.test(d));
  d=await ask('B500027',/500027/,'b3-card-500027');
  check('card B500027 rate 2.8546',/2\.8546/.test(d),d.match(/Rate \/ \$100\s*([\d.]+)/)?.[1]);
  d=await ask('cbl pearland town center',/11200 BROADWAY/i,'b4-owner');
  check('owner search returns Brazoria result',/Brazoria County/.test(d));
  check('no script errors at end',errs.length===0,errs.slice(0,3).join(' | '));
  await b.close(); console.log(`${res.filter(x=>x).length}/${res.length} passed`);
})();
