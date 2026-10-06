const { chromium } = require('/tmp/claude-0/-home-user-python-dashboard/1ec0f3b4-2640-5887-99f0-34b8037f6e91/scratchpad/node_modules/playwright');
const path = require('path'), fs = require('fs');
const pages = process.argv[2].split(',');
const widths = process.argv[3].split(',').map(Number);
fs.mkdirSync(path.join(__dirname,'shots'), {recursive:true});
(async () => {
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  for (const w of widths) {
    const ctx = await b.newContext({ viewport:{width:w,height:900}, deviceScaleFactor:1 });
    const p = await ctx.newPage();
    const errs = []; p.on('pageerror', e => errs.push(e.message));
    for (const n of pages) {
      await p.goto('file://' + path.join(__dirname,'out', n + '.html'), {waitUntil:'load'});
      // تصویرهای lazy را وادار به بارگذاری می‌کنیم و منتظر می‌مانیم
      // تا واقعاً decode شوند، وگرنه اسکرین‌شات کادرهای خالی می‌گیرد.
      await p.evaluate(() => document.querySelectorAll('img[loading="lazy"]').forEach(i=>i.loading='eager'));
      await p.evaluate(async () => {
        await new Promise(r => { let y=0; const t=setInterval(()=>{ window.scrollTo(0,y); y+=600;
          if (y > document.body.scrollHeight) { clearInterval(t); window.scrollTo(0,0); r(); } }, 30); });
        await Promise.all([...document.images].map(i => i.complete ? null : i.decode().catch(()=>{})));
      });
      // منتظرِ قطعیِ بارگذاری، نه یک وقفه‌ی حدسی. وقفه‌ی ثابت باعث
      // می‌شد گاهی عکسِ اعضای تیم در اسکرین‌شات نیفتد و مقایسه‌ی
      // تصویری الکی هشدار بدهد.
      await p.evaluate(() => document.fonts && document.fonts.ready);
      await p.waitForFunction(
        () => [...document.images]
          .filter(i => { const s = i.getAttribute('src'); return s && !/^https?:/i.test(s); })
          .every(i => i.complete && i.naturalWidth > 0),
        null, { timeout: 15000 }
      ).catch(() => {});
      await p.waitForTimeout(900);
      const ov = await p.evaluate(() => {
        const de = document.documentElement, bad = [];
        document.querySelectorAll('*').forEach(el=>{const r=el.getBoundingClientRect();
          if(r.width>0 && (r.right>de.clientWidth+1 || r.left<-1)) bad.push(el.className||el.tagName);});
        const imgs=[...document.images].filter(i=>{const s=i.getAttribute('src');
          return s && !/^https?:/i.test(s);});   // بدونِ src یعنی قابِ خالیِ لایت‌باکس، نه تصویرِ خراب
        return {sw:de.scrollWidth, cw:de.clientWidth, bad:[...new Set(bad)].slice(0,5),
                imgs:imgs.length, broken:imgs.filter(i=>!(i.complete&&i.naturalWidth>0)).map(i=>i.currentSrc.split('/').pop())};
      });
      console.log(`${n}@${w}`.padEnd(16),
        ov.sw>ov.cw+1 ? `⚠️ سرریز ${ov.sw}>${ov.cw} :: ${ov.bad.join(' | ')}` : '✓',
        `تصاویر ${ov.imgs}`, ov.broken.length ? '⚠️ خراب: '+ov.broken.join(', ') : '✓');
      await p.screenshot({path: path.join(__dirname,'shots',`${n}-${w}.png`), fullPage:true});
    }
    if (errs.length) console.log('  JS:', errs[0]);
    await ctx.close();
  }
  await b.close();
})();
