import {browserOptions,reviewOrigin,basePath,sourcePath} from './site_config.mjs';
// Capture repaired paragraph layout from the actual constructed website.
import fs from 'node:fs/promises';
import {chromium} from 'playwright';
const file='metadata/review/corpus/repaired-math.json';
const packet=JSON.parse(await fs.readFile(file,'utf8'));
const selectors={paragraph:'.standard-paragraph > p',list_item:'.standard-list-block li > p'};
const browser=await chromium.launch({...browserOptions});
try{
 const page=await browser.newPage({viewport:{width:1440,height:1080}});
 for(const row of packet.samples){
  await page.goto((reviewOrigin)+'/'+row.slug+'/',{waitUntil:'networkidle'});
  const node=page.locator('article '+selectors[row.kind]).nth(row.node_index);
  await node.screenshot({path:row.html_crop});
  row.native_tex=await node.locator('.katex annotation').allTextContents();
 }
}finally{await browser.close();}
await fs.writeFile(file,JSON.stringify(packet,null,2)+'\n');
console.log('Captured '+packet.samples.length+' repaired paragraphs from actual HTML.');
