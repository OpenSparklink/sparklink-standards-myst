import fs from 'node:fs';
import path from 'node:path';
export const basePath=(process.env.BASE_URL||'').replace(/\/$/,'');
if(basePath&&(!basePath.startsWith('/')||basePath.includes('..')))throw new Error('BASE_URL must be an absolute site path');
export const reviewOrigin=(process.env.REVIEW_ORIGIN||'http://127.0.0.1:8800'+basePath).replace(/\/$/,'');
const macChrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
export const browserOptions={headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:fs.existsSync(macChrome)?{executablePath:macChrome}:{})};
export function sourcePath(relative){
  for(const root of [process.cwd(),process.env.SPARKLINK_AUDIT_ARCHIVE||path.resolve('.local-archive')]){
    const file=path.resolve(root,relative);if(fs.existsSync(file))return file;
  }
  throw new Error('Private source asset unavailable: '+relative);
}
