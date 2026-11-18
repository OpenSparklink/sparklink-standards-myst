import {browserOptions,reviewOrigin,basePath,sourcePath} from './site_config.mjs';
// Reproducible visual review of the continuous publication, including the
// source-checked merged field table and fixed-width byte-layout diagram.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {chromium} from 'playwright';
const bytes=await fs.readFile('metadata/reading-manifest.json');
const manifest=JSON.parse(bytes),out='metadata/review/web-edition';
const origin=reviewOrigin;
const doc=code=>manifest.documents.find(d=>d.code===code);
const architecture=doc('GBT-48336.101-2026'),physical=doc('GBT-48336.201-2026'),link=doc('GBT-46803.2-2025');
const browser=await chromium.launch({...browserOptions});
const results=[];
try{
 const page=await browser.newPage({viewport:{width:1440,height:1080}});
 async function capture(name,route,{mobile=false,selector=null}={}){
  await page.setViewportSize(mobile?{width:390,height:844}:{width:1440,height:1080});
  const started=Date.now();
  await page.goto(origin+route,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>window.__sparklinkReaderReady===true);
  const readyMs=Date.now()-started;
  await page.evaluate(()=>document.fonts.ready);
  if(selector)await page.locator(selector).first().scrollIntoViewIfNeeded();
  await page.locator('article img').evaluateAll(nodes=>Promise.all(nodes.filter(n=>n.getBoundingClientRect().top<innerHeight&&n.getBoundingClientRect().bottom>0).map(n=>n.decode())));
  await page.screenshot({path:path.join(out,name+'.png')});
  const layout=await page.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth}));
  if(layout.document>layout.width+2)throw new Error('Page overflow: '+route);
  results.push({name,route,ready_ms:readyMs,...layout});
 }
 await capture('home','/');
 await capture('overview','/'+path.basename(architecture.index,'.md').toLowerCase().replaceAll('.','-')+'/');
 await capture('body','/'+architecture.chapters.find(c=>c.title==='6 架构').slug+'/');
 const table=physical.logical_tables.find(t=>/^表\s*1\D/.test(t.caption));
 await capture('table','/'+path.basename(table.file,'.md')+'/',{selector:'.table-scroll'});
 const fields=link.logical_tables.find(t=>/^表\s*9\D/.test(t.caption));
 await capture('field-table','/'+path.basename(fields.file,'.md')+'/',{selector:'.standard-table-caption:has-text("表 9")'});
 const figure=JSON.parse(await fs.readFile(link.paragraph_ledger,'utf8')).regions.find(r=>r.page===14&&r.kind==='figure');
 await capture('byte-layout','/'+path.basename(figure.file,'.md')+'/',{selector:'img[src*="p0014-figure"]'});
 await capture('mobile-home','/',{mobile:true});
 await capture('mobile-terms','/'+architecture.chapters.find(c=>c.title.startsWith('3 ')).slug+'/',{mobile:true});
}finally{await browser.close();}
await fs.writeFile(path.join(out,'visual-check.json'),JSON.stringify({manifest_sha256:createHash('sha256').update(bytes).digest('hex'),results,issues:[]},null,2)+'\n');
console.log('Captured and checked '+results.length+' current web layouts.');
