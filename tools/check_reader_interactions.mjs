import {browserOptions,reviewOrigin,basePath} from './site_config.mjs';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {chromium} from 'playwright';

const bytes=await fs.readFile('metadata/reading-manifest.json');
const manifest=JSON.parse(bytes);
const origin=reviewOrigin;
const browser=await chromium.launch({...browserOptions});
const results=[];
try {
  const page=await browser.newPage({viewport:{width:1440,height:1080}});
  // All reading, fonts, formula rendering and search must work without CDNs.
  const external=[];
  await page.route('**/*',route=>{
    const url=route.request().url();
    if(url.startsWith(origin+'/')||url.startsWith('data:'))return route.continue();
    external.push(url);return route.abort();
  });
  await page.goto(origin+'/',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:/搜索标准正文|Search/}).first().click();
  await page.getByRole('searchbox').fill('循环前缀');
  const result=page.getByRole('dialog').locator('a').first();
  await result.waitFor();
  const href=await result.getAttribute('href');
  await result.click();
  await page.locator('article h1').waitFor();
  await page.waitForFunction(()=>!!document.getElementById(decodeURIComponent(location.hash.slice(1))));
  results.push({check:'中文全文搜索及结果锚点跳转',passed:true,query:'循环前缀',target:href});

  assert.equal(await page.locator('article [role="tab"],article img.pdf-facsimile').count(),0);
  results.push({check:'直接阅读正文，无纸版切换或原页图像',passed:true});
  await page.goto(origin+'/gbt-48336-101-2026-01/',{waitUntil:'networkidle'});
  assert.equal(new URL(page.url()).pathname,basePath+'/gbt-48336-101-2026/');
  assert.ok(!(await page.locator('article').innerText()).includes('封面与目录'));
  results.push({check:'旧封面地址转到标准概览',passed:true});
  const candidate=manifest.documents.find(d=>d.code==='GBT-48336.101-2026').chapters.find(c=>c.title==='6 架构');
  await page.goto(origin+'/'+candidate.slug+'/',{waitUntil:'networkidle'});
  const cross=page.locator('article a.spec-reference').first();await cross.waitFor();
  const crossHref=await cross.getAttribute('href');await cross.click();
  await page.waitForFunction(()=>!!document.getElementById(decodeURIComponent(location.hash.slice(1))))
  results.push({check:'正文交叉引用跳转到图表或条款',passed:true,target:crossHref});
  const codeChapter='gbt-48336-201-2026-clause-7-5-1';
  await page.goto(origin+'/'+codeChapter+'/',{waitUntil:'networkidle'});
  const code=page.locator('article .figure-code code').filter({hasText:'Glink-CommonControl-Message'}).first();
  const selected=await code.evaluate(element=>{
    const range=document.createRange();
    range.selectNodeContents(element);
    const selection=window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    const result=selection.toString().replace(/\s+/g,' ');
    selection.removeAllRanges();
    return result;
  });
  assert.match(selected,/-- ASN1START Glink-CommonControl-Message ::= CHOICE \{/);
  assert.equal(await page.locator('article img.source-code').count(),0);
  results.push({check:'ASN.1 作为可选取的原生代码显示',passed:true,chapter:codeChapter});

  await page.goto(origin+'/gbt-48336-201-2026-clause-7-5-2-2/');
  const queryCode=page.locator('article pre').filter({hasText:'GlinkChannelStatusRequest'});
  assert.equal(await queryCode.count(),1);
  assert.match(await queryCode.textContent(),/^\s*-- ASN1START[\s\S]*GlinkChannelStatusRequest ::= SEQUENCE \{[\s\S]*-- ASN1STOP\s*$/);

  await page.goto(origin+'/gbt-48336-303-2026-clause-8/');
  for (const [message,continuedType] of [['DomainResourceReport','SLEDedicatedReport'],['DomainResourceConfiguration','SLBDedicatedConfig']]) {
    const definition=page.locator('article pre').filter({hasText:new RegExp('^\\s*'+message+' ::=')});
    assert.equal(await definition.count(),1);
    assert.match(await definition.textContent(),new RegExp('\\n}\\n\\s*'+continuedType+' ::= SEQUENCE'));
  }
  results.push({check:'跨页 ASN.1 定义、分隔符和注释完整保留在代码块内',passed:true});

  await page.goto(origin+'/gbt-48336-202-2026-clause-8-1-3-4/');
  const stepFive=page.locator('article table tr').filter({has:page.getByRole('cell',{name:'步骤5',exact:true})});
  assert.equal(await stepFive.count(),1);
  assert.equal(await stepFive.locator('td').nth(1).locator('.katex annotation').first().textContent(),'k=k+1');
  results.push({check:'测试表的步骤编号与赋值公式各自对齐',passed:true});

  for (const width of [1440,390]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin+'/gbt-48336-201-2026-clause-9-3-7/');
    const table=page.locator('article table.figure-table.source-bit-table');
    const headers=table.getByRole('columnheader');
    assert.deepEqual(await headers.allTextContents(),['0–3','4–7','8–11','12–15','16–19','20–23']);
    assert.ok(await table.evaluate(node=>[...node.rows[0].cells].every((header,i)=>{
      const label=header.getBoundingClientRect();
      const field=node.rows[1].cells[i].getBoundingClientRect();
      return Math.abs(label.left-field.left)<1 && Math.abs(label.width-field.width)<1;
    })));
    const bytes=page.locator('article .source-bit-table:not(.figure-table)').getByRole('rowheader');
    assert.deepEqual(await bytes.allTextContents(),['字节 1','字节 2','字节 3','字节 4']);
  }
  await page.setViewportSize({width:1440,height:1080});
  results.push({check:'位域范围与字段在桌面和手机上逐列对齐',passed:true});

  const vectorChapter='gbt-46803-1-2025-appendix-b';
  await page.goto(origin+'/'+vectorChapter+'/',{waitUntil:'networkidle'});
  const vector=page.locator('article img.standard-vector-figure').first();
  await vector.focus();
  await vector.press('Enter');
  const zoom=page.locator('dialog[open]');await zoom.waitFor();
  await zoom.locator('img').evaluate(e=>e.decode());
  await zoom.getByRole('button',{name:'适应宽度 / 原尺寸'}).click();
  assert.equal(await zoom.locator('.reader-dialog-scroll').evaluate(e=>e.classList.contains('fit')),false);
  await zoom.getByRole('button',{name:'关闭',exact:true}).click();
  results.push({check:'键盘打开矢量图并切换放大尺寸',passed:true,chapter:vectorChapter});

  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:/搜索标准正文|Search/}).first().click();
  await page.getByRole('searchbox').fill('循环前缀');
  await page.getByRole('dialog').locator('a').first().waitFor();
  assert.ok(await page.getByRole('dialog').locator('a').count());
  results.push({check:'390 px 手机宽度中文搜索',passed:true});

  const diagramChapter='gbt-48336-301-2026-clause-9-4';
  await page.goto(origin+'/'+diagramChapter+'/');
  const wideDiagram=page.locator('article .standard-diagram').filter({hasText:'SLB切换SLE完成'}).first();
  await wideDiagram.locator('svg[data-reader-layout]').waitFor();
  const diagramLayout=await wideDiagram.evaluate(element=>({
    viewport:innerWidth,
    document:document.documentElement.scrollWidth,
    width:element.clientWidth,
    content:element.scrollWidth,
    inset:element.querySelector('svg').getBoundingClientRect().width,
  }));
  assert.ok(diagramLayout.document<=diagramLayout.viewport+2);
  assert.ok(diagramLayout.content>diagramLayout.width && diagramLayout.inset>diagramLayout.viewport*2);
  await wideDiagram.focus();
  await wideDiagram.press('ArrowRight');
  await page.waitForFunction(()=>document.activeElement?.matches('.standard-diagram') && document.activeElement.scrollLeft>0);
  results.push({check:'手机长时序图保留可读字号，支持键盘横向滚动',passed:true,chapter:diagramChapter});

  const tableChapter='gbt-48336-201-2026-clause-9-4';
  await page.goto(origin+'/'+tableChapter+'/');
  for(const name of ['S1 的字节展开（MSB 至 LSB）','Octet 0 的位域']){
    const region=page.getByRole('region',{name,exact:true});
    await region.waitFor();
    assert.equal(await region.locator('.figure-table-label').innerText(),name);
    assert.equal(await region.locator('table.figure-table').getAttribute('aria-label'),name);
  }
  results.push({check:'组合位域表保留独立标题和可访问名称',passed:true,chapter:tableChapter});

  const glossaryTerms = {
    '101': ['COT', 'CP-OFDM', 'SSAP', 'S-AODV', 'S-RPL', 'TCID'],
    '304': ['EAP', 'EAP-5G', 'GPRS', 'GTP-U', 'NAS', 'NAS-PDU', 'NG-RAN', 'SLB', 'SLB-CMTC', 'SLB-SMTC'],
  };
  for (const [part, expected] of Object.entries(glossaryTerms)) {
    await page.goto(origin + '/gbt-48336-' + part + '-2026-clause-4/');
    const definitions = await page.locator('article .standard-definitions dt').evaluateAll(terms =>
      terms.map(term => ({term: term.textContent.trim(), definition: term.nextElementSibling.textContent.trim()})));
    assert.deepEqual(definitions.filter(entry => expected.includes(entry.term)).map(entry => entry.term), expected);
    for (const entry of definitions.filter(entry => expected.includes(entry.term))) {
      assert.ok(entry.definition, 'Missing definition for ' + entry.term);
      for (const term of expected) {
        assert.ok(!entry.definition.includes(term + '：'), 'Merged definition for ' + term);
      }
    }
  }
  results.push({check:'带连字符的缩略语独立成条，保留原有顺序',passed:true});

  const paragraphGaps = {};
  for (const width of [1440, 390]) {
    await page.setViewportSize({width, height: 900});
    await page.goto(origin + '/gbt-48336-101-2026-clause-5/');
    const gaps = await page.locator('article .standard-paragraph > p').evaluateAll(paragraphs => {
      const first = paragraphs.slice(0, 6).map(p => p.getBoundingClientRect());
      return first.slice(1).map((rect, index) => Math.round(rect.top - first[index].bottom));
    });
    assert.equal(gaps.length, 5);
    assert.ok(gaps.every(gap => gap >= 6 && gap <= 20), 'Unexpected paragraph gaps at ' + width + ' px: ' + gaps);
    paragraphGaps[width] = gaps;
  }
  results.push({check:'桌面与手机连续正文段距',passed:true,gaps_px:paragraphGaps});

  assert.deepEqual(external,[],'Reader unexpectedly requested external resources');
  results.push({check:'正文、数学字体与全文搜索无需外部 CDN',passed:true});
} finally {await browser.close();}
const report={manifest_sha256:createHash('sha256').update(bytes).digest('hex'),time:new Date().toISOString(),results,issues:[]};
await fs.writeFile('metadata/reader-interactions.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({checks:results.length,issues:0}));
