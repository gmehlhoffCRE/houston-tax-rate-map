// Browser check for a Liberty build (Liberty-only or all counties): boot, county toggle, LCAD property id search,
// card rate and labels, owner search.
//   node liberty_check.js http://localhost:8090/web/index.html <screenshot dir> <cdn map json>
// The cdn map ({"url regex": "local file"}) serves deck.gl, pmtiles and the MVT worker from npm copies when
// the CDNs are blocked. Basemap tile errors (Esri host blocked in the sandbox) fail the two "no script errors"
// checks there; everything else should pass.
// Expected: L18096 (Liberty ISD, City of Liberty) = county 0.48 + Liberty ISD 0.97 + City of Liberty 0.5838
// + hospital district 0.089328 + navigation south 0.01017 + water district 5 0.078708 = 2.2120;
// L254876 (Cleveland ISD) = 1.5041 base, plus Liberty County MMD 1 0.35 with "Incl. mgmt districts".
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
  check('county toggles list Liberty',counties.some(t=>/Liberty County/.test(t)),counties.join(' | '));
  await p.evaluate(()=>window.__app.setView(-94.8,30.15,10)); await sleep(12000);
  await p.screenshot({path:path.join(shots,'l1-county.png')});
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
  let d=await ask('18096',/18096/,'l2-card-18096');
  check('card L18096 rate 2.2120',/2\.2120/.test(d),d.match(/Rate \/ \$100\s*([\d.]+)/)?.[1]);
  check('card shows Liberty County and LCAD property ID 18096',/Liberty County/.test(d)&&/LCAD property ID\s*18096/i.test(d));
  check('card Liberty note',/Liberty CAD/.test(d));
  check('card breakdown has Liberty ISD and City of Liberty',/Liberty ISD/i.test(d)&&/City of Liberty/i.test(d));
  d=await ask('L254876',/254876/,'l3-card-254876');
  check('card L254876 base rate 1.5041',/1\.5041/.test(d),d.match(/Rate \/ \$100\s*([\d.]+)/)?.[1]);
  check('card notes Liberty County MMD 1 (mgmt)',/Liberty County Municipal Management District 1/i.test(d));
  d=await ask('international leadership of texas',/ROAD 5714/i,'l4-owner');
  check('owner search returns Liberty result',/Liberty County/.test(d));
  check('no script errors at end',errs.length===0,errs.slice(0,3).join(' | '));
  await b.close(); console.log(`${res.filter(x=>x).length}/${res.length} passed`);
})();
