// Browser check for a Chambers build (Chambers-only or all counties): boot, county toggle, Chambers CAD id search,
// card rate and labels, owner search.
//   node chambers_check.js http://localhost:8090/web/index.html <screenshot dir> <cdn map json>
// The cdn map ({"url regex": "local file"}) serves deck.gl, pmtiles and the MVT worker from npm copies when
// the CDNs are blocked. Basemap tile errors (Esri host blocked in the sandbox) fail the two "no script errors"
// checks there; everything else should pass.
// Expected: C49490 (O'Reilly, Baytown) = county 0.414192 + school equalization 0.025554 + Goose Creek CISD 1.07
// + City of Baytown 0.69803 + Lee College 0.18706 - see data/ch_combos.csv; C67998 = 2.2509.
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
  check('county toggles list Chambers',counties.some(t=>/Chambers County/.test(t)),counties.join(' | '));
  await p.evaluate(()=>window.__app.setView(-94.7,29.75,10)); await sleep(12000);
  await p.screenshot({path:path.join(shots,'c1-county.png')});
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
  let d=await ask('49490',/Chambers CAD 49490/,'c2-card-49490');
  check('card C49490 rate 2.2568',/2\.2568/.test(d),d.match(/Rate \/ \$100\s*([\d.]+)/)?.[1]);
  check('card shows Chambers County and Chambers CAD property ID 49490',/Chambers County/.test(d)&&/Chambers CAD property ID\s*49490/i.test(d));
  check('card Chambers note',/certified roll/.test(d));
  check('card breakdown has Goose Creek and Baytown',/Goose Creek/i.test(d)&&/Baytown/i.test(d));
  d=await ask('C67998',/67998/,'c3-card-67998');
  check('card C67998 rate 2.2509',/2\.2509/.test(d),d.match(/Rate \/ \$100\s*([\d.]+)/)?.[1]);
  d=await ask('ahc chambers commons',/AHC CHAMBERS|Ahc Chambers/i,'c4-owner');
  check('owner search returns Chambers result',/Chambers County/.test(d));
  check('no script errors at end',errs.length===0,errs.slice(0,3).join(' | '));
  await b.close(); console.log(`${res.filter(x=>x).length}/${res.length} passed`);
})();
