import {browserOptions,reviewOrigin,basePath,sourcePath} from './site_config.mjs';
// Capture every structured chapter for source-based content verification.
import fs from 'node:fs/promises';
import {chromium} from 'playwright';
import {createHash} from 'node:crypto';
const manifest=JSON.parse(await fs.readFile('metadata/reading-manifest.json','utf8'));
const out='tmp/full-audit/dom';await fs.mkdir(out,{recursive:true});
const documents=manifest.documents.filter(d=>!process.env.AUDIT_CODE||d.code.includes(process.env.AUDIT_CODE));
if(!documents.length)throw new Error('No matching standard');
const chapters=documents.flatMap(d=>d.chapters.map(c=>({...c,code:d.code})));
const browser=await chromium.launch({...browserOptions});
const results=[];let cursor=0;
try{
 async function worker(){const page=await browser.newPage({viewport:{width:1440,height:1080}});
  for(;;){const i=cursor++;if(i>=chapters.length)break;const chapter=chapters[i];
   await page.goto((reviewOrigin)+'/'+chapter.slug+'/',{waitUntil:'domcontentloaded',timeout:60000});
   await page.waitForFunction(()=>window.__sparklinkReaderReady===true,undefined,{timeout:60000});
   const data=await page.locator('article').evaluate(article=>{
    function snapshot(node){
     const clone=node.cloneNode(true);for(const e of clone.querySelectorAll('.katex-mathml,.standard-equation-number,button'))e.remove();
     const semantic=node.cloneNode(true);for(const e of semantic.querySelectorAll('.standard-equation-number,button'))e.remove();
     for(const e of semantic.querySelectorAll('.katex')){const m=e.querySelector('math')?.cloneNode(true);if(m){for(const a of m.querySelectorAll('annotation'))a.remove();e.replaceWith(document.createTextNode(m.textContent));}}
     const math=[...node.querySelectorAll('.katex annotation')].map(e=>e.textContent);
     const scripts=[...node.querySelectorAll('sub,sup')].map(e=>({kind:e.tagName.toLowerCase(),text:e.textContent}));
     const script_atoms=[...scripts];
     for(const e of node.querySelectorAll('sub,sup')){
      let text=e.textContent,next=e.nextSibling;
      while(next){if(next.nodeType===3&&!next.textContent.trim()){next=next.nextSibling;continue;}if(next.nodeType===1&&next.tagName===e.tagName){text+=next.textContent;next=next.nextSibling;}else break;}
      if(text!==e.textContent)script_atoms.push({kind:e.tagName.toLowerCase(),text});
     }
     for(const e of node.querySelectorAll('.katex-mathml msub,.katex-mathml msup,.katex-mathml msubsup')){
      const c=e.children,base=c[0]?.textContent||'',ancestors=[];
      for(let parent=e.parentElement;parent&&parent.localName!=='math';parent=parent.parentElement)if(['msub','msup','msubsup'].includes(parent.localName))ancestors.push(parent.children[0]?.textContent||'');
      if(e.localName==='msub'||e.localName==='msubsup')script_atoms.push({kind:'sub',base,ancestors,text:c[1]?.textContent||''});
      if(e.localName==='msup')script_atoms.push({kind:'sup',base,ancestors,text:c[1]?.textContent||''});
      if(e.localName==='msubsup')script_atoms.push({kind:'sup',base,ancestors,text:c[2]?.textContent||''});
     }
     return {text:clone.textContent,semantic_text:semantic.textContent,math,scripts,script_atoms};
    }
    const selectors={paragraph:'.standard-paragraph > p',list_item:'.standard-list-block li > p',definition:'.standard-definitions dl',reference:'.standard-reference > p',equation:'.standard-equation-row',caption:'.standard-caption > p',pseudocode:'.algorithm-line > p,.standard-algorithm,pre'};
    const blocks=Object.fromEntries(Object.entries(selectors).map(([kind,selector])=>[kind,[...article.querySelectorAll(selector)].filter(e=>kind!=='pseudocode'||!/^\s*--\s*ASN1(?:START|STOP)/.test(e.textContent)).map(snapshot)]));
    for(const kind of ['note','example'])blocks[kind]=[...article.querySelectorAll('aside.myst-admonition')].filter(e=>new RegExp(kind==='note'?'^注':'^示例').test(e.querySelector('.myst-admonition-header-text')?.textContent||'')).map(snapshot);
    const headings=[...article.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(e=>({level:Number(e.tagName[1]),...snapshot(e)}));
    const captions=[...article.querySelectorAll('.standard-table-caption > p')].map(snapshot);
    const tables=[...article.querySelectorAll('table.standard-table')].map(table=>{
     const occupied=[];const cells=[];
     [...table.rows].forEach((row,r)=>{occupied[r]||=[];let c=0;
      for(const cell of row.cells){while(occupied[r][c])c++;const rs=cell.rowSpan,cs=cell.colSpan;
       for(let y=r;y<r+rs;y++){occupied[y]||=[];for(let x=c;x<c+cs;x++)occupied[y][x]=true;}
       cells.push({r,c,rowspan:rs,colspan:cs,...snapshot(cell)});c+=cs;
      }
     });return {cells};
    });
    const paragraph_list_flow=[...article.querySelectorAll('.standard-paragraph > p,.standard-list-block li > p')].map(snapshot);
    const ids=[...article.querySelectorAll('[id]')].map(e=>e.id);
    const references=[...article.querySelectorAll('a.spec-reference')].map(e=>e.getAttribute('href'));
    return {blocks,headings,captions,tables,paragraph_list_flow,ids,references};
   });
   const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
   results.push({...chapter,markdown_sha256:sha(await fs.readFile(chapter.path)),html_sha256:sha(await fs.readFile('_build/html/'+chapter.slug+'/index.html')),...data});if(results.length%25===0)console.log('Captured '+results.length+'/'+chapters.length+' chapters');
  }await page.close();}
 await Promise.all([worker(),worker(),worker()]);
}finally{await browser.close();}
for(const doc of documents)await fs.writeFile(`${out}/${doc.code}.json`,JSON.stringify(results.filter(c=>c.code===doc.code))+'\n');
console.log('Captured all '+results.length+' chapters.');
