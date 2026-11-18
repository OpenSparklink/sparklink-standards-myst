import fs from 'node:fs/promises';
import path from 'node:path';
import {localizeStyles} from './localize_styles.mjs';
const root=process.cwd();
const out=path.join(root,'_build/html');
const prefix=(process.env.BASE_URL || '').replace(/\/$/,'');
const tag=`<script defer src="${prefix}/reader.js"></script>`;
await localizeStyles(out,prefix);
async function walk(dir) {
  for (const entry of await fs.readdir(dir,{withFileTypes:true})) {
    const file=path.join(dir,entry.name);
    if (entry.isDirectory()) await walk(file);
    else if (entry.name.endsWith('.html')) {
      let text=await fs.readFile(file,'utf8');
      text=text.replace('<html lang="en"','<html lang="zh-CN"');
      const route=path.relative(out,path.dirname(file)).split(path.sep).join('/');
      if(route&&!route.includes('/'))text=text.replace(/<h1\b([^>]*)>/,(_,attrs)=>'<h1'+attrs.replace(/\s+id="[^"]*"/g,'')+' id="'+route+'">');
      if (!text.includes(tag)) text=text.replace('</body>',tag+'</body>');
      await fs.writeFile(file,text);
    }
  }
}
const scope=await fs.readFile(path.join(root,'web/reference_scope.js'),'utf8');
await fs.writeFile(path.join(out,'reader.js'),scope+'\n'+await fs.readFile(path.join(root,'web/reader.js'),'utf8'));
await fs.copyFile(path.join(root,'metadata/web-references.json'),path.join(out,'reader-index.json'));
await fs.writeFile(path.join(out,'.nojekyll'),'');
await walk(out);
const manifest=JSON.parse(await fs.readFile(path.join(root,'metadata/reading-manifest.json'),'utf8'));
let redirects=0;
for(const doc of manifest.documents)for(const route of doc.legacy_routes||[]){
  const file=path.join(out,route.from,'index.html');
  try{const existing=await fs.readFile(file,'utf8');if(!existing.includes('name="robots" content="noindex"'))throw new Error('Legacy route collides with published chapter: '+route.from);}catch(error){if(error.code!=='ENOENT')throw error;}
  const target=prefix+'/'+route.to+'/';
  await fs.mkdir(path.dirname(file),{recursive:true});
  await fs.writeFile(file,`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="robots" content="noindex"><link rel="canonical" href="${target}"><meta http-equiv="refresh" content="0;url=${target}"><title>正在打开技术条款</title></head><body><a href="${target}">打开技术条款</a><script>location.replace(${JSON.stringify(target)}+location.hash)</script></body></html>`);
  redirects++;
}
console.log(`Published continuous reading, technical cross-references and ${redirects} legacy redirects.`);
