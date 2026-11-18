import {browserOptions,reviewOrigin,basePath,sourcePath} from './site_config.mjs';
// Reproducible visual samples for the repaired table and complex mathematics.
import fs from 'node:fs/promises';
import path from 'node:path';
import {chromium} from 'playwright';
const manifest=JSON.parse(await fs.readFile('metadata/reading-manifest.json','utf8'));
const doc=manifest.documents.find(d=>d.code==='GBT-48336.201-2026');
const out='metadata/review';await fs.mkdir(out,{recursive:true});
const targets=[
  {name:'native-table-120khz',page:18,table:true},
  {name:'native-piecewise-fts',page:21,tex:'d_{\\mathrm{FTS}}(n)'},
  {name:'native-matrix',page:30,tex:'\\boldsymbol X(k,n)'},
  {name:'native-fractions-in-text',page:56,text:'计算信道比特序列数'},
  {name:'native-table-fractions',page:69,table:true},
  {name:'native-qam1024',page:91,tex:'\\sqrt{682}'},
  {name:'native-evm',page:290,tex:'\\mathrm{EVM}'},
  {name:'native-phase-ranging',page:344,tex:'\\varphi_{\\mathrm R}'},
];
const browser=await chromium.launch({...browserOptions});
const results=[];
try{
  const page=await browser.newPage({viewport:{width:1440,height:1080}});
  for(const target of targets){
    const candidates=doc.chapters.filter(c=>c.page<=target.page&&(c.end_page>target.page||c.end_page===target.page&&c.end_y>0));
    let chapter;
    if(target.table){
      const table=doc.tables.find(t=>t.page===target.page);
      chapter=candidates.find(c=>(c.page<target.page||c.y<=table.bbox[1])&&(c.end_page>target.page||c.end_y>table.bbox[1]));
    }else{
      for(const c of candidates){if((await fs.readFile(c.path,'utf8')).includes(target.tex||target.text)){chapter=c;break;}}
    }
    if(!chapter)throw new Error('Missing reviewed chapter '+target.name);
    await page.goto((reviewOrigin)+'/'+chapter.slug+'/',{waitUntil:'networkidle'});
    await page.waitForFunction(()=>window.__sparklinkReaderReady===true);
    if(target.tex){
      const found=await page.evaluate(tex=>{
        const annotation=[...document.querySelectorAll('article .katex annotation')].find(e=>e.textContent.includes(tex));
        const math=annotation?.closest('.katex-display')||annotation?.closest('.katex');
        math?.scrollIntoView({block:'center'});return !!math;
      },target.tex);
      if(!found)throw new Error('Missing reviewed formula '+target.name);
    }else if(target.text)await page.locator('.standard-paragraph').filter({hasText:target.text}).first().scrollIntoViewIfNeeded();
    else await page.locator('.table-scroll').first().scrollIntoViewIfNeeded();
    const file=path.join(out,target.name+'.png');await page.screenshot({path:file});
    results.push({...target,chapter:chapter.slug,screenshot:file});
  }
  await fs.writeFile('metadata/review/native-math-samples.json',JSON.stringify(results,null,2)+'\n');
}finally{await browser.close();}
console.log('Saved '+results.length+' native-math visual samples.');
