import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
await import('./build_math_styles.mjs');
const preload = pathToFileURL(path.join(root,'tools/limit_build_network.mjs')).href;
const args = process.argv.slice(2);
const preview = args[0] === '--preview';
if (preview) args.shift();
const command = preview ? ['start','--keep-host'] : ['build','--html','--strict','--keep-host'];
// The CLI's optional background version lookup can crash on a registry
// retry. Resolve that one package to the installed version for this build;
// other package requests retain the normal public registry.
const installed=JSON.parse(await fs.readFile(path.join(root,'node_modules/mystmd/package.json'),'utf8')).version;
const registry=http.createServer((req,res)=>{
  if (req.url==='/mystmd') {
    res.writeHead(200,{'Content-Type':'application/json'});
    res.end(JSON.stringify({'dist-tags':{latest:installed},versions:{[installed]:{name:'mystmd',version:installed}}}));
  } else {res.writeHead(307,{Location:'https://registry.npmjs.org'+req.url});res.end();}
});
await new Promise(resolve=>registry.listen(0,'127.0.0.1',resolve));
// Retain lossless source crops. The CLI otherwise launches cwebp once per
// image with unbounded concurrency and applies lossy compression to glyphs.
const publicDir=path.join(root,'_build/site/public');
if(!preview){
  // Publish only current routes/assets; obsolete paper pages must not remain
  // reachable or searchable after an edition change.
  await fs.rm(path.join(root,'_build/html'),{recursive:true,force:true});
  await fs.rm(path.join(root,'_build/site'),{recursive:true,force:true});
}
try {
  const files=await fs.readdir(publicDir);
  await Promise.all(files.filter(f=>f.endsWith('.webp') && files.includes(f.slice(0,-5)+'.png')).map(f=>fs.unlink(path.join(publicDir,f))));
} catch (error) { if (error.code!=='ENOENT') throw error; }
const child = spawn(process.execPath,[path.join(root,'node_modules/mystmd/dist/myst.cjs'), ...command, ...args], {
  cwd:root, stdio:'inherit',
  env:{ ...process.env, HOST:'127.0.0.1',
    PATH:[path.dirname(process.execPath),'/usr/bin','/bin','/usr/sbin','/sbin'].join(path.delimiter),
    npm_config_registry:`http://127.0.0.1:${registry.address().port}/`,
    NODE_OPTIONS:[process.env.NODE_OPTIONS, '--dns-result-order=ipv4first', `--import=${preload}`].filter(Boolean).join(' '),
  },
});
for (const signal of ['SIGINT','SIGTERM']) process.on(signal,()=>child.kill(signal));
child.on('exit',async (code,signal)=>{
  await new Promise(resolve=>registry.close(resolve));
  if (signal || code) process.exit(code || 1);
  if (!preview) await import('./postprocess_html.mjs');
  process.exit(0);
});
