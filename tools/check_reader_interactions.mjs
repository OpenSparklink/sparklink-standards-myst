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

  const chapterWithContext='gbt-46803-2-2025-clause-6-3-2-11';
  for (const width of [390,948,1440]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin+'/'+chapterWithContext+'/');
    const context=page.getByRole('navigation',{name:'规范版本和相关阅读'});
    await context.waitFor();
    const gap=await context.evaluate(nav=>{
      const title=nav.previousElementSibling;
      return nav.getBoundingClientRect().top-title.getBoundingClientRect().bottom;
    });
    assert.ok(gap>=6,`章节标题和导航在 ${width}px 视口下的间距为 ${gap}px`);
  }
  results.push({check:'窄屏和桌面章节标题与标准检索导航留有间距',passed:true});

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

  const syncChapter='gbt-46803-1-2025-clause-6-1';
  for (const width of [1440,390]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin+'/'+syncChapter+'/');
    const sequence=page.locator('article .standard-literal code');
    const expected=[
      BigInt('0x5A2BDA62').toString(2).padStart(32,'0').split('').reverse().join(''),
      BigInt('0x7DE7585C6D226540').toString(2).padStart(64,'0').split('').reverse().join(''),
    ];
    assert.deepEqual(await sequence.allTextContents(),expected);
    for (const [index,bits] of expected.entries()) {
      const layout=await sequence.nth(index).evaluate(element=>{
        const range=document.createRange();
        range.selectNodeContents(element);
        const selection=window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        const result={
          selected:selection.toString(),
          lines:range.getClientRects().length,
          valueWidth:range.getBoundingClientRect().width,
          wrapperWidth:element.parentElement.clientWidth,
          paragraphWidth:element.closest('p').clientWidth,
          documentWidth:document.documentElement.scrollWidth,
          viewport:innerWidth,
        };
        selection.removeAllRanges();
        return result;
      });
      assert.equal(layout.selected,bits);
      assert.equal(layout.lines,1);
      assert.ok(layout.wrapperWidth<=layout.paragraphWidth);
      assert.ok(layout.documentWidth<=layout.viewport+2);
      if (width===390 && index===1) assert.ok(layout.valueWidth>layout.wrapperWidth);
    }
  }
  results.push({check:'固定同步序列在桌面和手机均可整段复制，长序列只在段内横向滚动',passed:true,chapter:syncChapter});

  await page.goto(origin+'/gbt-48336-202-2026-clause-6-1-3/');
  const scheduling=page.locator('article table tr').filter({has:page.getByRole('cell',{name:'6.1.3.3-47',exact:true})});
  const requirements=await scheduling.locator('td').nth(2).innerText();
  assert.match(requirements,/\ne\).*minGlinkDataDelay.*minTlinkDataDelay.*\nf\)/);
  results.push({check:'表格内的长字段完整，测试子项边界保留',passed:true});

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
  const vector=page.locator('article .reader-vector-zoom').first();
  await vector.focus();
  await vector.press('Enter');
  const zoom=page.locator('dialog[open]');await zoom.waitFor();
  await zoom.locator('img').evaluate(e=>e.decode());
  await zoom.getByRole('button',{name:'适应宽度 / 原尺寸'}).click();
  assert.equal(await zoom.locator('.reader-dialog-scroll').evaluate(e=>e.classList.contains('fit')),false);
  await zoom.getByRole('button',{name:'关闭',exact:true}).click();
  results.push({check:'键盘打开矢量图并切换放大尺寸',passed:true,chapter:vectorChapter});

  await page.goto(origin+'/gbt-48336-304-2026-clause-6-4/');
  const label=page.locator('article .reader-vector svg text.vector-label').getByText('3.PDU会话上下文建立请求',{exact:true});
  assert.equal(await label.evaluate(text=>{
    const range=document.createRange();range.selectNodeContents(text);
    const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
    const selected=selection.toString();selection.removeAllRanges();return selected;
  }),'3.PDU会话上下文建立请求');
  results.push({check:'PDF 轮廓图的标签可在正文中选取复制',passed:true});

  await page.goto(origin+'/gbt-48336-304-2026-clause-6-1/');
  const diagram=page.locator('article .standard-diagram').filter({hasText:'释放与可信G节点之间的5G融合资源'}).locator('rect.actor-top').first();
  await diagram.waitFor();
  const lightFill=await diagram.evaluate(rect=>getComputedStyle(rect).fill);
  assert.equal(lightFill,'rgb(255, 255, 255)');
  assert.ok(await diagram.evaluate(rect=>{
    const viewport=rect.closest('.standard-diagram');
    return viewport.scrollWidth<=viewport.clientWidth+1;
  }));
  await page.locator('html').evaluate(node=>node.classList.add('dark'));
  assert.equal(await diagram.evaluate(rect=>getComputedStyle(rect).fill),'rgb(25, 29, 35)');
  await page.locator('html').evaluate(node=>node.classList.remove('dark'));
  const conditions=page.locator('article .standard-list-block > ol > li').filter({hasText:'如果该定时器未配置'}).locator(':scope > ol > li');
  assert.equal(await conditions.count(),3);
  assert.match(await conditions.first().textContent(),/1）/);
  assert.match(await conditions.last().textContent(),/3）/);
  results.push({check:'时序图跟随明暗主题，步骤内三项条件同级对齐',passed:true});

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

  await page.goto(origin+'/');
  const entrances=page.locator('article .reading-entry-grid');
  assert.deepEqual(await entrances.getByRole('link').allTextContents(),['规范正文','专题指南','技术索引']);
  await entrances.getByRole('link',{name:'技术索引'}).click();
  const catalog=page.getByRole('search',{name:'查找技术条目'});
  const query=catalog.getByRole('searchbox');
  await query.fill('requestType');
  await catalog.getByLabel('类别').selectOption('field');
  const field=page.locator('.technical-index-results li').filter({hasText:'GlinkChannelStatusRequest'});
  await field.getByRole('link',{name:'requestType',exact:true}).click();
  await page.waitForFunction(()=>location.hash==='#gbt-48336-201-2026-clause-7-5-2-2'&&!!document.getElementById(location.hash.slice(1)));
  await page.getByRole('link',{name:'合读查询与反馈',exact:true}).click();
  const pairedCode=page.locator('article pre');
  await page.waitForURL('**/slb-link-status/');
  await pairedCode.last().waitFor();
  assert.equal(await pairedCode.count(),2);
  assert.match(await pairedCode.first().textContent(),/GlinkChannelStatusRequest ::= SEQUENCE/);
  assert.match(await pairedCode.last().textContent(),/GlinkChannelStatusFeedback ::= SEQUENCE/);
  const outline=page.locator('.reader-mobile-outline');
  await outline.locator('summary').click();
  assert.equal(await page.locator('article .myst-outline').isVisible(),false);
  await outline.getByRole('link',{name:/G 链路信道反馈消息/}).click();
  await page.waitForFunction(()=>location.hash==='#status-feedback');
  assert.equal(await outline.getAttribute('open'),null);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
  results.push({check:'手机首页到字段检索、规范原条款和查询反馈合读',passed:true});

  await page.goto(origin+'/technical-index/?q=CSI-RS4&kind=test&standard=GBT-48336.202-2026&role=T');
  await catalog.getByLabel('测试角色').waitFor();
  assert.equal(await catalog.getByLabel('测试角色').inputValue(),'T');
  const testLinks=page.locator('.technical-index-results a');
  assert.equal(await testLinks.count(),1);
  assert.match(await testLinks.first().getAttribute('href'),/8-2-3-4\/#gbt-48336-202-2026-clause-8-2-3-4$/);
  await catalog.getByLabel('测试角色').selectOption('G');
  assert.equal(await testLinks.count(),1);
  assert.match(await testLinks.first().getAttribute('href'),/8-1-3-4\/#gbt-48336-202-2026-clause-8-1-3-4$/);
  await page.reload();
  await catalog.getByLabel('测试角色').waitFor();
  assert.equal(await catalog.getByLabel('测试角色').inputValue(),'G');
  results.push({check:'同名试验按 G/T 角色区分，筛选链接可分享',passed:true});

  await page.goto(origin+'/gbt-48336-201-2026-clause-7-5-2/');
  assert.equal(await page.locator('.myst-primary-sidebar a:is([href$="clause-7-5-2-2"],[href$="clause-7-5-2-2/"])').count(),0);
  await page.getByRole('link',{name:'报文索引',exact:true}).click();
  assert.equal(await catalog.getByLabel('类别').inputValue(),'message');
  assert.equal(await catalog.getByLabel('规范版本').inputValue(),'GBT-48336.201-2026');
  await catalog.getByRole('button',{name:/7\.5\.2.*清除条款范围/}).waitFor();
  assert.equal(await page.locator('.technical-index-results li').count(),30);
  results.push({check:'章节到同组报文索引与原文锚点',passed:true});

  await page.setViewportSize({width:1440,height:900});
  await page.goto(origin+'/slb-link-status/');
  await page.getByRole('navigation',{name:'本页目录'}).getByRole('link',{name:/7\.5\.2\.3/}).waitFor();
  await page.context().grantPermissions(['clipboard-read','clipboard-write'],{origin:new URL(origin).origin});
  await page.goto(origin+'/gbt-48336-101-2026-clause-6/');
  await page.getByRole('button',{name:'复制图 2 的链接',exact:true}).click();
  assert.match(await page.evaluate(()=>navigator.clipboard.readText()),/#gbt-48336-101-2026-figure-2$/);
  results.push({check:'桌面页内目录与图号固定链接复制',passed:true});

  await page.goto(origin+'/gbt-46803-1-2025-appendix-c/');
  const longTable=page.locator('.reader-long-table').first();
  await longTable.waitFor();
  assert.ok(await longTable.evaluate(table=>{
    const header=table.querySelector('.reader-sticky-header th');
    table.scrollTop=250;
    const before=header.getBoundingClientRect().top;
    table.scrollTop=350;
    return table.scrollTop>250&&Math.abs(header.getBoundingClientRect().top-before)<1;
  }));
  results.push({check:'滚动长表时保留表头',passed:true});

  assert.deepEqual(external,[],'Reader unexpectedly requested external resources');
  results.push({check:'正文、数学字体与全文搜索无需外部 CDN',passed:true});
} finally {await browser.close();}
const report={manifest_sha256:createHash('sha256').update(bytes).digest('hex'),time:new Date().toISOString(),results,issues:[]};
await fs.writeFile('metadata/reader-interactions.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({checks:results.length,issues:0}));
