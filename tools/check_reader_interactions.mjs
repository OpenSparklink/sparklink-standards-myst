import {browserOptions,reviewOrigin,basePath,sourcePath} from './site_config.mjs';
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
  let chapter;
  for(const doc of manifest.documents) {
    for(const c of doc.chapters)if((await fs.readFile(c.path,'utf8')).includes(':class: source-code')){chapter=c;break;}
    if(chapter)break;
  }
  assert.ok(chapter,'Missing original raster code sample');
  await page.goto(origin+'/'+chapter.slug+'/',{waitUntil:'networkidle'});
  await page.locator('article img.source-code').first().click();
  const zoom=page.locator('dialog[open]');await zoom.waitFor();
  await zoom.locator('img').evaluate(e=>e.decode());
  await zoom.getByRole('button',{name:'适应宽度 / 原尺寸'}).click();
  assert.equal(await zoom.locator('.reader-dialog-scroll').evaluate(e=>e.classList.contains('fit')),false);
  await zoom.getByRole('button',{name:'关闭',exact:true}).click();
  results.push({check:'原始栅格代码图放大与原尺寸查看',passed:true,chapter:chapter.slug});

  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:/搜索标准正文|Search/}).first().click();
  await page.getByRole('searchbox').fill('循环前缀');
  await page.getByRole('dialog').locator('a').first().waitFor();
  assert.ok(await page.getByRole('dialog').locator('a').count());
  results.push({check:'390 px 手机宽度中文搜索',passed:true});
  assert.deepEqual(external,[],'Reader unexpectedly requested external resources');
  results.push({check:'正文、数学字体与全文搜索无需外部 CDN',passed:true});
} finally {await browser.close();}
const report={manifest_sha256:createHash('sha256').update(bytes).digest('hex'),time:new Date().toISOString(),results,issues:[]};
await fs.writeFile('metadata/reader-interactions.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({checks:results.length,issues:0}));
