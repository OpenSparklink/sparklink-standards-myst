// These standards contain no notebook widgets. Drop their two template-only
// stylesheets and use the installed KaTeX version with embedded local fonts.
// Apply to both SSR HTML and hydration bundles so SPA navigation agrees.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';

export async function localizeStyles(out,prefix='') {
  const unused=[
    'https://cdn.jsdelivr.net/npm/jupyter-matplotlib@0.11.3/css/mpl_widget.css',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.css',
  ];
  const oldKatex='https://cdn.jsdelivr.net/npm/katex@0.15.2/dist/katex.min.css';
  const oldIntegrity='sha384-MlJdn/WNKDGXveldHDdyRP1R4CTHr3FeuDNfhsLPYrq2t0UBkUdK2jyTnXPEK1NQ';
  const generated=await fs.readFile('styles/reader.css','utf8');
  const css=generated.split('\n').slice(0,2).join('\n')+'\n';
  if(!css.includes('@font-face')||/url\(fonts\//.test(css))throw new Error('KaTeX fonts must be embedded');
  const integrity='sha384-'+createHash('sha384').update(css).digest('base64');
  await fs.mkdir(path.join(out,'reader'),{recursive:true});
  await fs.writeFile(path.join(out,'reader/katex.css'),css);
  await fs.copyFile('styles/KaTeX-LICENSE.txt',path.join(out,'reader/KaTeX-LICENSE.txt'));
  let htmlFiles=0,bundles=0;
  const esc=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  async function walk(dir){
    for(const entry of await fs.readdir(dir,{withFileTypes:true})){
      const file=path.join(dir,entry.name);
      if(entry.isDirectory()){await walk(file);continue;}
      if(!/\.(?:html|js)$/.test(file))continue;
      let text=await fs.readFile(file,'utf8'),before=text;
      for(const url of unused){
        text=text.replace(new RegExp('<link\\b[^>]*href="'+esc(url)+'"[^>]*>','g'),'');
      }
      // The book template exports these unused notebook styles together.
      const objects=unused.map(url=>'\\{rel:`stylesheet`,href:`'+esc(url)+'`\\}');
      text=text.replace(new RegExp('\\['+objects.join(',')+'\\]','g'),'[]');
      text=text.replaceAll(oldKatex,prefix+'/reader/katex.css').replaceAll(oldIntegrity,integrity);
      if(text!==before){await fs.writeFile(file,text);if(file.endsWith('.html'))htmlFiles++;else bundles++;}
      if(unused.some(url=>text.includes(url)))throw new Error('Unused remote stylesheet survived in '+file);
    }
  }
  await walk(out);
  console.log(`Localized stylesheet dependencies in ${htmlFiles} HTML files and ${bundles} hydration bundles.`);
}
