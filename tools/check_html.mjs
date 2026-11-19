import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import { createHash } from 'node:crypto';
import { chromium } from 'playwright';
import {basePath,browserOptions,sourcePath} from './site_config.mjs';

const root = process.cwd();
const build = path.resolve(root, '_build/html');
const reportDir = path.resolve(root, 'tmp/html-review');
await fs.mkdir(reportDir, { recursive: true });
const manifest = JSON.parse(await fs.readFile('metadata/reading-manifest.json', 'utf8'));
const figureTables = JSON.parse(await fs.readFile('metadata/figure-tables.json', 'utf8'));
if (process.env.CHECK_DOCUMENT) manifest.documents = manifest.documents.filter(d => d.code === process.env.CHECK_DOCUMENT);
const sourceAssets=new Set(manifest.documents.flatMap(d=>d.page_assets.map(a=>a.asset)));
const verifySourceSamples=process.env.SOURCE_PDF_REVIEW==='1';
const types = { '.html':'text/html; charset=utf-8', '.js':'text/javascript', '.css':'text/css', '.svg':'image/svg+xml', '.png':'image/png', '.jpg':'image/jpeg', '.webp':'image/webp', '.json':'application/json', '.woff2':'font/woff2', '.ico':'image/x-icon' };
const server = http.createServer(async (req, res) => {
  try {
    let pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    if(basePath&&!pathname.startsWith(basePath+'/'))throw new Error('outside site base');
    pathname=pathname.slice(basePath.length);
    const targetRoot = pathname.startsWith('/__source__/') ? root : build;
    const relative = pathname.startsWith('/__source__/') ? pathname.slice('/__source__/'.length) : pathname.slice(1);
    let target = path.resolve(targetRoot, relative);
    if(pathname.startsWith('/__source__/')){
      if(!sourceAssets.has(relative))throw new Error('unknown source page');
      target=sourcePath(relative);
    }
    if (!pathname.startsWith('/__source__/') && !target.startsWith(targetRoot + path.sep) && target !== targetRoot) throw new Error('invalid path');
    const stat = await fs.stat(target);
    if (stat.isDirectory()) target = path.join(target, 'index.html');
    const bytes = await fs.readFile(target);
    res.writeHead(200, { 'Content-Type':types[path.extname(target)] || 'application/octet-stream' });
    res.end(bytes);
  } catch {
    res.writeHead(404, { 'Content-Type':'text/plain' }); res.end('Not found');
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}${basePath}`;
const browser = await chromium.launch(browserOptions);
const issues = [];
const results = [];
const samples = [];
const expectedBlocks = new Map();
const expectedMath = new Map();
const expectedDiagrams = new Map();
const expectedFigureCode = new Map();
const internalLinks=new Set();
async function collectLinks(page){
  for(const url of await page.locator('a[href]').evaluateAll(nodes=>nodes.map(a=>a.href))) {
    if(url.startsWith(origin+'/'))internalLinks.add(url.split('#')[0].split('?')[0]);
  }
}
for (const doc of manifest.documents) {
  const ledger=JSON.parse(await fs.readFile(doc.paragraph_ledger,'utf8'));
  for (const block of ledger.blocks.filter(b=>b.rendered!==false)) {
    const counts=expectedBlocks.get(block.file) || {};
    if(block.render_counts)for(const [kind,n] of Object.entries(block.render_counts))counts[kind]=(counts[kind]||0)+n;
    else if (!block.continuation_of) counts[block.kind]=(counts[block.kind] || 0)+1;
    expectedBlocks.set(block.file,counts);
  }
  for (const chapter of doc.chapters) {
    const source=await fs.readFile(chapter.path,'utf8');
    expectedMath.set(chapter.path,(source.match(/\$[^$\n]+\$/g) || []).length+(source.match(/^```\{math\}/gm) || []).length);
    expectedDiagrams.set(chapter.path,(source.match(/^```\{mermaid\}/gm)||[]).length);
    expectedFigureCode.set(chapter.path,[...source.matchAll(/:class: figure-code\n\n```asn1\n([\s\S]*?)\n```$/gm)].map(match=>match[1].trim()));
  }
}
const chapters = manifest.documents.flatMap(doc => doc.chapters.map(chapter => ({ doc, chapter })));
if (process.env.CHECK_CHAPTER) chapters.splice(0,chapters.length,...chapters.filter(x=>x.chapter.slug===process.env.CHECK_CHAPTER));
let cursor = 0;

async function imageCheck(page) {
  await page.evaluate(() => {
    for (const img of document.querySelectorAll('article img')) if (img.getClientRects().length) img.loading='eager';
  });
  try {
    await page.waitForFunction(()=>[...document.querySelectorAll('article img')].filter(i=>i.getClientRects().length).every(i=>i.complete && i.naturalWidth>0),undefined,{timeout:15000});
  } catch { /* report the current live image nodes, not detached hydration nodes */ }
  return page.evaluate(()=>[...document.querySelectorAll('article img')].filter(i=>i.getClientRects().length && (!i.complete || i.naturalWidth===0)).map(i=>({src:i.getAttribute('src'),current:i.currentSrc,complete:i.complete,width:i.naturalWidth})));
}

async function worker() {
  const context = await browser.newContext({ viewport:{ width:1440, height:1080 }, deviceScaleFactor:1 });
  const page = await context.newPage();
  let localErrors = [];
  page.on('pageerror', e => localErrors.push(String(e)));
  page.on('response', r => { if (r.status() >= 400 && r.url().startsWith(origin)) localErrors.push(`${r.status()} ${r.url()}`); });
  for (;;) {
    const idx = cursor++;
    if (idx >= chapters.length) break;
    const { doc, chapter } = chapters[idx];
    const route = `/${chapter.slug}/`;
    localErrors = [];
    const found = { code:doc.code, chapter:chapter.title, route, issues:[] };
    try {
      const response = await page.goto(origin + route, { waitUntil:'domcontentloaded', timeout:60000 });
      if (response.status() !== 200) throw new Error(`HTTP ${response.status()}`);
      await page.waitForFunction(()=>window.__sparklinkReaderReady===true,undefined,{timeout:60000});
      await page.locator('article').first().waitFor({ timeout:15000 });
      if(await page.locator('article [role="tab"],article .myst-tab-set,article img.pdf-facsimile').count())found.issues.push('paper reading controls remain');
      const articleText=await page.locator('article').innerText();
      if(/原版阅读|结构化阅读|PDF 第|封面与目录|ICS\s*35|CCS\s*L\s*79/.test(articleText))found.issues.push('paper-only metadata remains');
      // KaTeX uses private font glyphs for correctly rendered operators.
      // Check editorial text independently of its visual math font encoding.
      const editorialText=await page.locator('article').evaluate(e=>{const c=e.cloneNode(true);for(const n of c.querySelectorAll('.katex,script,style'))n.remove();return c.textContent;});
      if(/[\u0590-\u08ff\u0e00-\u0e7f\ue000-\uf8ff\u{f0000}-\u{10fffd}]/u.test(editorialText))found.issues.push('unconverted cover glyphs remain');
      const missingStructured = await imageCheck(page);
      if (missingStructured.length) found.issues.push({ missingStructured });
      const expected=expectedBlocks.get(chapter.path) || {};
      found.paragraphs=await page.locator('article .standard-paragraph > p, article .figure-table-bit-boundaries').count();
      found.definitions=await page.locator('article .standard-definitions dl').count();
      found.references=await page.locator('article .standard-reference > p').count();
      found.listItems=await page.locator('article .standard-list-block li').count();
      found.nativeMath=await page.locator('article .katex').count();
      if (found.nativeMath!==(expectedMath.get(chapter.path) || 0)) found.issues.push({mathRendering:{expected:expectedMath.get(chapter.path) || 0,actual:found.nativeMath}});
      if (await page.locator('article .katex-error').count()) found.issues.push('LaTeX rendering error');
      if (await page.locator('article .text-myst-warning-text[title]').count()) found.issues.push('Unrendered mathematics placeholder');
      for (const [kind,actual] of [['paragraph',found.paragraphs],['definition',found.definitions],['reference',found.references],['list_item',found.listItems]]) {
        if (actual!==(expected[kind] || 0)) found.issues.push({semanticBlockCount:{kind,expected:expected[kind] || 0,actual}});
      }
      found.tables = await page.locator('article table').count();
      const captionCount = await page.locator('article .standard-table-caption').count();
      const expectedCaptions=doc.logical_tables.filter(t=>t.file===chapter.path&&t.caption!=='字段结构').length;
      if (captionCount !== expectedCaptions) found.issues.push({tableCaptions:{expected:expectedCaptions,actual:captionCount}});
      found.mergedCells = await page.locator('article td[colspan], article td[rowspan], article th[colspan], article th[rowspan]').count();
      const badTables = await page.evaluate(() => [...document.querySelectorAll('article table.standard-table')].flatMap((table, ti) => {
        const grid = [];
        for (let r = 0; r < table.rows.length; r++) {
          grid[r] ||= [];
          let c = 0;
          for (const cell of table.rows[r].cells) {
            while (grid[r][c]) c++;
            for (let rr=r; rr<r+cell.rowSpan; rr++) {
              grid[rr] ||= [];
              for (let cc=c; cc<c+cell.colSpan; cc++) {
                if (grid[rr][cc]) return [{table:ti,reason:'overlapping DOM spans'}];
                grid[rr][cc] = true;
              }
            }
            c += cell.colSpan;
          }
        }
        if (grid.length !== table.rows.length) return [{table:ti,reason:'rowspan exceeds row count'}];
        const widths = grid.map(r => r.length);
        if (new Set(widths).size > 1) return [{table:ti,reason:'inconsistent DOM column counts',widths}];
        return [];
      }));
      if (badTables.length) found.issues.push({ badTables });
      const convertedFigures = await page.locator('article table.figure-table').evaluateAll(tables => tables.map(table => ({
        rows:table.rows.length,
        columns:[...(table.rows[0]?.cells||[])].reduce((sum,cell)=>sum+cell.colSpan,0),
        anchor:table.getAttribute('aria-labelledby')||'',
        unscoped:table.querySelectorAll('th:not([scope])').length,
      })));
      const expectedFigures = (figureTables[chapter.slug] || []).map(({rows,columns,anchor=''}) => ({
        rows,columns,anchor,unscoped:0,
      }));
      if(JSON.stringify(convertedFigures)!==JSON.stringify(expectedFigures)){
        found.issues.push({figureTables:{expected:expectedFigures,actual:convertedFigures}});
      }
      const retiredTableAssets=new Set((figureTables[chapter.slug]||[]).map(({asset})=>path.basename(asset)));
      if(retiredTableAssets.size){
        const remaining=await page.locator('article img').evaluateAll(images=>images.map(image=>new URL(image.src).pathname.split('/').pop()));
        const rasterTables=remaining.filter(name=>retiredTableAssets.has(name));
        if(rasterTables.length)found.issues.push({rasterTables});
      }
      const diagramCount=expectedDiagrams.get(chapter.path)||0;
      if(diagramCount){
        try{
          await page.waitForFunction(count=>[...document.querySelectorAll('article .standard-diagram')].filter(diagram=>
            diagram.querySelector('figure svg') && !/Syntax error|UnknownDiagramError/i.test(diagram.textContent)).length===count,
            diagramCount,{timeout:12000});
        }catch{
          const diagrams=await page.locator('article .standard-diagram').evaluateAll(nodes=>nodes.map(diagram=>({
            svg:!!diagram.querySelector('figure svg'),text:diagram.textContent.trim().slice(0,160),
          })));
          found.issues.push({diagramRendering:{expected:diagramCount,diagrams}});
        }
      }
      const figureCode=(await page.locator('article .figure-code pre code').allTextContents()).map(text=>text.trim());
      if(JSON.stringify(figureCode)!==JSON.stringify(expectedFigureCode.get(chapter.path)||[])){
        found.issues.push({figureCode:{expected:expectedFigureCode.get(chapter.path)?.length||0,actual:figureCode.length}});
      }
      const codeText = await page.locator('article pre').allTextContents();
      if (codeText.some(t => /::::|tab-item|tab-set|^\s*[\u3400-\u9fff]{10}/m.test(t))) found.issues.push('body/directive misparsed as code');
      await page.setViewportSize({ width:390, height:844 });
      const mobile = await page.evaluate(() => ({ width:innerWidth, scroll:document.documentElement.scrollWidth, scrollTables:[...document.querySelectorAll('.table-scroll')].map(e=>{
        const scroller=e.querySelector('[aria-label="table content"]') || e;
        return {width:scroller.clientWidth,scroll:scroller.scrollWidth,overflow:getComputedStyle(scroller).overflowX};
      }) }));
      if (mobile.scroll > mobile.width + 2) found.issues.push({ mobileOverflow:mobile });
      const wideTables = mobile.scrollTables.filter(x => x.scroll > x.width + 5);
      if (wideTables.some(x => x.overflow !== 'auto' && x.overflow !== 'scroll')) found.issues.push('wide table does not scroll');
      await page.setViewportSize({ width:1440, height:1080 });
      found.mobileTables = mobile.scrollTables.length;
      if (localErrors.length) found.issues.push({ browserErrors:localErrors });
      await collectLinks(page);
    } catch (e) { found.issues.push(String(e)); }
    results.push(found);
    if (found.issues.length) { issues.push(found);console.log(JSON.stringify(found)); }
    if (results.length % 15 === 0) console.log(`Checked ${results.length}/${chapters.length} chapters; ${issues.length} with issues`);
  }
  await context.close();
}

try {
  await Promise.all([worker(),worker(),worker()]);
  const retries=issues.filter(result=>result.issues.every(issue=>typeof issue==='string' && issue.startsWith('TimeoutError:')));
  if (retries.length) {
    // Loading hundreds of vector-heavy pages can temporarily starve a Chrome
    // renderer. Recheck navigation/action timeouts sequentially in a fresh
    // context; retain every original failure in the report's retry ledger.
    const originalChapters=chapters.slice();
    const routes=new Set(retries.map(result=>result.route));
    chapters.splice(0,chapters.length,...originalChapters.filter(({chapter})=>routes.has('/'+chapter.slug+'/')));
    for (const result of retries) {
      results.splice(results.indexOf(result),1);issues.splice(issues.indexOf(result),1);
    }
    cursor=0;
    await worker();
    chapters.splice(0,chapters.length,...originalChapters);
  }
  const context = await browser.newContext({ viewport:{ width:1440, height:1080 }, deviceScaleFactor:1 });
  const page = await context.newPage();
  async function htmlFiles(dir){
    const paths=[];
    for(const entry of await fs.readdir(dir,{withFileTypes:true})) {
      const file=path.join(dir,entry.name);
      if(entry.isDirectory())paths.push(...await htmlFiles(file));
      else if(entry.name.endsWith('.html'))paths.push(file);
    }
    return paths;
  }
  const legacyRoutes=new Map(manifest.documents.flatMap(d=>(d.legacy_routes||[]).map(r=>['/'+r.from+'/',r.to])));
  const allHtml=(await htmlFiles(build)).filter(file=>!legacyRoutes.has('/'+path.relative(build,file).split(path.sep).join('/').replace(/index\.html$/,'')));
  for(const [route,target] of legacyRoutes){await fs.access(path.join(build,target,'index.html'));const alias=await fs.readFile(path.join(build,route,'index.html'),'utf8');if(!alias.includes('noindex')||!alias.includes('/'+target+'/'))issues.push({invalidLegacyRedirect:route});}
  const chapterRoutes=new Set(chapters.map(({chapter})=>'/'+chapter.slug+'/'));
  const frontPages=[];
  for(const file of (process.env.CHECK_DOCUMENT||process.env.CHECK_CHAPTER?[]:allHtml)){
    const relative=path.relative(build,file).split(path.sep).join('/');
    const route='/'+relative.replace(/index\.html$/,'');
    if(chapterRoutes.has(route))continue;
    const found={route,issues:[]};
    try {
      const response=await page.goto(origin+route,{waitUntil:'domcontentloaded',timeout:60000});
      if(response.status()!==200)throw new Error('HTTP '+response.status());
      await page.waitForFunction(()=>window.__sparklinkReaderReady===true,undefined,{timeout:60000});
      await page.locator('article').first().waitFor();
      found.title=await page.title();
      if(!(await page.locator('article h1').count()))found.issues.push('missing page heading');
      const missing=await imageCheck(page);if(missing.length)found.issues.push({missing});
      await collectLinks(page);
      await page.setViewportSize({width:390,height:844});
      const mobile=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
      if(mobile.scroll>mobile.width+2)found.issues.push({mobileOverflow:mobile});
      await page.setViewportSize({width:1440,height:1080});
    }catch(error){found.issues.push(String(error));}
    frontPages.push(found);if(found.issues.length)issues.push(found);
  }
  const linkIssues=[];
  for(const url of internalLinks){
    const pathname=decodeURIComponent(new URL(url).pathname).slice(basePath.length);
    let file=path.resolve(build,'.'+pathname);
    try {
      if((await fs.stat(file)).isDirectory())file=path.join(file,'index.html');
      await fs.access(file);
    }catch{linkIssues.push(url.replace(origin,''));}
  }
  if(linkIssues.length)issues.push({brokenInternalLinks:linkIssues});
  for (const doc of manifest.documents) {
    const selected=doc.chapters.find(c=>doc.logical_tables.some(t=>t.file===c.path))||doc.chapters[0];
    await page.goto(origin+'/'+selected.slug+'/',{waitUntil:'networkidle'});
    await imageCheck(page);
    const firstTable=page.locator('.table-scroll').first();if(await firstTable.count())await firstTable.scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(reportDir,doc.code+'-web.png')});
    // Render real source SVGs in the browser at 144 dpi, independent of the
    // scaled reading width, for comparison with a fresh PDF rasterization.
    const tablePage = doc.tables[0]?.page || Math.min(20,doc.pages);
    for (const n of (verifySourceSamples?[...new Set([1,tablePage,doc.pages])]:[])) {
      const asset = doc.page_assets[n-1];
      const png = await page.evaluate(async ({url,w,h}) => {
        const img = new Image(); img.src=url; await img.decode();
        const canvas=document.createElement('canvas'); canvas.width=Math.ceil(w*2); canvas.height=Math.ceil(h*2);
        const ctx=canvas.getContext('2d'); ctx.fillStyle='#ffffff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,w*2,h*2);
        return canvas.toDataURL('image/png').split(',')[1];
      },{url:origin+'/__source__/'+asset.asset,w:asset.width,h:asset.height});
      const output=path.join(reportDir,`${doc.code}-p${String(n).padStart(4,'0')}-browser.png`);
      await fs.writeFile(output,Buffer.from(png,'base64'));
      samples.push({code:doc.code,page:n,path:path.relative(root,output)});
    }
  }
  await context.close();
  const report={manifest_sha256:createHash('sha256').update(await fs.readFile('metadata/reading-manifest.json')).digest('hex'),
    time:new Date().toISOString(),basePath,sourcePixelComparison:verifySourceSamples,documents:manifest.documents.length,chapters:chapters.length,pages:allHtml.length,frontPages,
    internalLinks:internalLinks.size,legacyRedirects:legacyRoutes.size,issues,retries,results,samples};
  await fs.writeFile(process.env.CHECK_DOCUMENT||process.env.CHECK_CHAPTER?'tmp/html-review/browser-smoke.json':'metadata/browser-check.json',JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({documents:report.documents,chapters:report.chapters,pages:report.pages,internalLinks:report.internalLinks,issues:issues.length,pixelSamples:samples.length}));
  if (issues.length) process.exitCode=1;
} finally {
  await browser.close();
  await new Promise(resolve=>server.close(resolve));
}
