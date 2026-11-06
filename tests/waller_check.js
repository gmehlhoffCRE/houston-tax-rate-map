// Browser check for a Waller build (Waller-only or all counties): boot, county toggle, WCAD id search,
// card rates and labels, owner search.
//   node waller_check.js http://localhost:8090/web/index.html <screenshot dir> <cdn map json>
// The cdn map ({"url regex": "local file"}) serves deck.gl, pmtiles and the MVT worker from npm copies when
// the CDNs are blocked. Basemap tile errors (Esri host blocked in the sandbox) fail the two "no script errors"
// checks there; everything else should pass.
// Expected values: W44584 = Hempstead ISD 1.076 + county 0.532596 + RFM 0.023591 + ESD 0.10 = 1.7322;
// W248025 = Katy ISD + City of Katy + Harris-Waller MUD 3 + B-K drainage + county + RFM + ESD = 3.1361.
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
  check('county toggles list Waller',counties.some(t=>/Waller County/.test(t)),counties.join(' | '));
  await p.evaluate(()=>window.__app.setView(-96.0,30.0,10)); await sleep(12000);
  await p.screenshot({path:path.join(shots,'w1-county.png')});
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
  let d=await ask('44584',/44584/,'w2-card-44584');
  check('card W44584 rate 1.7322',/1\.7322/.test(d)); check('card shows Waller County and WCAD property ID 44584',/Waller County/.test(d)&&/WCAD property ID\s*44584/i.test(d));
  check('card Waller note',/Waller-Harris ESD 200 is applied countywide/.test(d));
  check('card breakdown has Hempstead ISD',/Hempstead Isd|Hempstead ISD/i.test(d));
  d=await ask('W248025',/248025/,'w3-card-katy');
  check('card W248025 rate 3.1361',/3\.1361/.test(d),d.match(/Rate \/ \$100\s*([\d.]+)/)?.[1]);
  d=await ask('kloecker',/KLOECKER/i,'w4-owner');
  check('owner search returns Waller result',/Waller County/.test(d));
  check('no script errors at end',errs.length===0,errs.slice(0,3).join(' | '));
  await b.close(); console.log(`${res.filter(x=>x).length}/${res.length} passed`);
})();
