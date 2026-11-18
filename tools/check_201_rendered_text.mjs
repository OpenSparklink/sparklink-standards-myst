import {browserOptions,reviewOrigin,basePath,sourcePath} from './site_config.mjs';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {chromium} from 'playwright';

const bytes=await fs.readFile('metadata/reading-manifest.json');
const manifest=JSON.parse(bytes),doc=manifest.documents.find(d=>d.code==='GBT-48336.201-2026');
const ledger=JSON.parse(await fs.readFile(doc.paragraph_ledger,'utf8'));
const chinese=s=>(s.match(/[\u3400-\u9fff]/g)||[]).join('');
const tokens=s=>{
  s=s.normalize('NFKC').replaceAll('ϕ','φ').replaceAll('ϵ','ε');
  const counts={};for(const c of s.match(/[A-Za-z0-9α-ωΑ-Ω]/g)||[])counts[c]=(counts[c]||0)+1;
  return counts;
};
const delta=(a,b)=>Object.fromEntries(Object.entries(a).filter(([c,n])=>n>(b[c]||0)).map(([c,n])=>[c,n-(b[c]||0)]));
const key=b=>b.page+':'+b.line_ids.join(',');
const records=ledger.blocks.filter(b=>b.rendered!==false).map(b=>({...b,comparison_text:b.source_text,chinese:chinese(b.reading_order_text||b.source_text)}));
const byKey=new Map(records.map(b=>[key(b),b]));
const bySourceLine=new Map(records.flatMap(b=>b.line_ids.map(i=>[b.page+':'+i,b])));
for(const b of records)if(b.kind==='math_fragment'){
  const target=bySourceLine.get(b.page+':'+b.math_fragment_of);
  if(!target)throw new Error('Missing formula fragment destination');
  target.comparison_text+='\n'+b.source_text;target.chinese+=b.chinese;
}
for(const b of records)if(b.continuation_of){const target=byKey.get(b.continuation_of.page+':'+b.continuation_of.line_ids.join(','));if(!target)throw new Error('Missing continuation source');target.chinese+=b.chinese;target.comparison_text+='\n'+b.comparison_text;}
const captured=process.env.CAPTURED_DOM==='1';
const snapshots=captured?new Map(JSON.parse(await fs.readFile('tmp/full-audit/dom/GBT-48336.201-2026.json','utf8')).map(c=>[c.path,c])):null;
const selectors={paragraph:'.standard-paragraph > p',list_item:'.standard-list-block li > p',definition:'.standard-definitions dl',reference:'.standard-reference > p',equation:'.standard-equation-row'};
const browser=captured?null:await chromium.launch({...browserOptions});
async function assertSnapshot(snapshot,chapter){if(!snapshot)throw new Error('Missing snapshot '+chapter.path);const sha=b=>createHash('sha256').update(b).digest('hex');if(sha(await fs.readFile(chapter.path))!==snapshot.markdown_sha256||sha(await fs.readFile('_build/html/'+chapter.slug+'/index.html'))!==snapshot.html_sha256)throw new Error('Stale snapshot '+chapter.path);}
const results=[],issues=[];let cursor=0;
try{
  async function worker(){const page=captured?null:await browser.newPage({viewport:{width:1440,height:1080}});
    for(;;){const i=cursor++;if(i>=doc.chapters.length)break;const chapter=doc.chapters[i];
      if(captured)await assertSnapshot(snapshots.get(chapter.path),chapter);
      else await page.goto((reviewOrigin)+'/'+chapter.slug+'/',{waitUntil:'networkidle'});
      for(const [kind,selector] of Object.entries(selectors)){
        const expected=records.filter(b=>b.file===chapter.path&&b.kind===kind&&!b.continuation_of).sort((a,b)=>a.page-b.page||a.bbox[1]-b.bbox[1]);
        const actual=captured?snapshots.get(chapter.path).blocks[kind].map(n=>n.text):await page.locator('article '+selector).evaluateAll(nodes=>nodes.map(node=>{const clone=node.cloneNode(true);for(const e of clone.querySelectorAll('.katex-mathml,.standard-equation-number'))e.remove();return clone.textContent;}));
        if(expected.length!==actual.length){issues.push({chapter:chapter.path,kind,expected:expected.length,actual:actual.length});continue;}
        for(let n=0;n<expected.length;n++){
          const block=expected[n],same=block.chinese===chinese(actual[n]);const row={chapter:chapter.path,kind,page:block.page,line_ids:block.line_ids,reviewed:!!block.reviewed_math,matches:same};
          const source=kind==='equation'?block.comparison_text.replace(/(?:[.·…]\s*){2,}[（(]\s*\d+\s*[）)]/g,''):block.comparison_text;
          const a=tokens(source),b=tokens(actual[n]),missing=delta(a,b),extra=delta(b,a);
          row.source_tokens_match=!Object.keys(missing).length&&!Object.keys(extra).length;
          if(!row.source_tokens_match)issues.push({...row,source:block.source_text,rendered:actual[n],missing,extra});
          if(!same)issues.push({...row,source:block.source_text,rendered:actual[n],expectedChinese:block.chinese,actualChinese:chinese(actual[n])});results.push(row);
        }
      }
    }if(page)await page.close();}
  await Promise.all([worker(),worker(),worker()]);
}finally{if(browser)await browser.close();}
const report={capture:captured?'current corpus browser snapshot':'independent browser navigation',manifest_sha256:createHash('sha256').update(bytes).digest('hex'),chapters:doc.chapters.length,blocks:results.length,issues,results};
await fs.writeFile('metadata/201-rendered-text-check.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({chapters:report.chapters,blocks:report.blocks,issues:issues.length}));if(issues.length)process.exitCode=1;
