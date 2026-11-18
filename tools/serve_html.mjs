import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import {basePath} from './site_config.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../_build/html');
const port=Number(process.env.PORT || 8800);
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.json':'application/json','.woff2':'font/woff2','.ico':'image/x-icon'};
await fs.access(path.join(root,'index.html'));
http.createServer(async(req,res)=>{
  try {
    let pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
    if(basePath&&!pathname.startsWith(basePath+'/')){
      res.writeHead(302,{Location:basePath+(pathname==='/'?'/':pathname)});res.end();return;
    }
    const relative=pathname.slice(basePath.length+1);
    let target=path.resolve(root,relative);
    if (target!==root && !target.startsWith(root+path.sep)) throw new Error('Invalid path');
    if ((await fs.stat(target)).isDirectory()) target=path.join(target,'index.html');
    res.writeHead(200,{'Content-Type':types[path.extname(target)] || 'application/octet-stream'});
    res.end(await fs.readFile(target));
  } catch {res.writeHead(404,{'Content-Type':'text/plain; charset=utf-8'});res.end('未找到文件，请先运行 npm run build。');}
}).listen(port,'127.0.0.1',()=>console.log(`星闪标准阅读：http://127.0.0.1:${port}`));
