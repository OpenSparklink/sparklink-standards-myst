import {browserOptions,reviewOrigin,basePath,sourcePath} from './site_config.mjs';
// Resolve secondary SVG-renderer differences with the actual browser.
import fs from 'node:fs/promises';import http from 'node:http';import {chromium} from 'playwright';
const manifest=JSON.parse(await fs.readFile('metadata/reading-manifest.json','utf8'));
const report=JSON.parse(await fs.readFile('tmp/full-audit/visual-check.json','utf8'));
const tasks=report.issues.filter(i=>i.kind==='pages'&&i.mae>0);
const out='tmp/full-audit/svg-browser';await fs.mkdir(out,{recursive:true});
const server=http.createServer(async(req,res)=>{try{const parts=req.url.split('/');if(parts.length<3){res.end('<!doctype html>');return;}const doc=manifest.documents.find(d=>d.code===parts[1]);const asset=doc.page_assets[Number(parts[2])-1];res.setHeader('Content-Type','image/svg+xml');res.end(await fs.readFile(sourcePath(asset.asset)));}catch{res.writeHead(404);res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({...browserOptions});
try{const page=await browser.newPage();await page.goto(origin);
for(const task of tasks){const doc=manifest.documents.find(d=>d.code===task.code),asset=doc.page_assets[task.page-1];
 const png=await page.evaluate(async({url,w,h})=>{const img=new Image();img.src=url;await img.decode();const c=document.createElement('canvas');c.width=Math.ceil(w*2);c.height=Math.ceil(h*2);const ctx=c.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,c.width,c.height);ctx.drawImage(img,0,0,w*2,h*2);return c.toDataURL('image/png').split(',')[1];},{url:`${origin}/${task.code}/${task.page}`,w:asset.width,h:asset.height});
 await fs.writeFile(`${out}/${task.code}-p${task.page}.png`,Buffer.from(png,'base64'));
}console.log('Rendered '+tasks.length+' SVG pages in Chromium.');
}finally{await browser.close();await new Promise(r=>server.close(r));}
