(() => {
  const scriptUrl=document.currentScript?.src||new URL('reader.js',location.href).href;
  const siteRoot=new URL('.',scriptUrl);
  const basePath=siteRoot.pathname.replace(/\/$/,'');
  const currentRoute=()=>location.pathname.slice(basePath.length).split('/').filter(Boolean)[0];
  let dialog,referenceIndex;
  let processed=new WeakMap(),referenceRoute;
  let vectorId=0;
  const vectorElements=new Set(['svg','title','desc','defs','g','path','line','rect','circle','ellipse','polygon','polyline','marker','clipPath','text','tspan']);
  const vectorAttributes=new Set('id viewBox role aria-label aria-labelledby aria-describedby orient refX refY markerWidth markerHeight d fill width height stroke font-family stroke-width x1 x2 y1 y2 x y dx dy font-size text-anchor textLength lengthAdjust marker-end marker-start baseline-shift stroke-dasharray cx cy r rx ry stroke-opacity transform points version clip-rule clip-path stroke-linecap stroke-linejoin stroke-miterlimit opacity class'.split(' '));
  const translations=new Map([['Search','搜索'],['Contents','本页'],['CONTENTS','本页'],['On this page','本页'],['Next','下一节'],['Previous','上一节']]);
  function hydrated(element) {
    const key=Object.keys(element||{}).find(k=>k.startsWith('__reactFiber$'));
    let fiber=key&&element[key];if(!fiber)return false;
    while(fiber.return){
      if(fiber.tag===13&&fiber.memoizedState?.dehydrated)return false;
      fiber=fiber.return;
    }
    return fiber.stateNode?.current?.memoizedState?.isDehydrated===false;
  }
  function zoom(image) {
    if (!dialog) {
      dialog=document.createElement('dialog');dialog.className='reader-dialog';
      const toolbar=document.createElement('div');toolbar.className='reader-dialog-toolbar';
      const close=document.createElement('button');close.textContent='关闭';close.addEventListener('click',()=>dialog.close());
      const fit=document.createElement('button');fit.textContent='适应宽度 / 原尺寸';
      const link=document.createElement('a');link.textContent='打开图像';link.target='_blank';link.rel='noopener';
      const scroll=document.createElement('div');scroll.className='reader-dialog-scroll fit';
      const large=document.createElement('img');scroll.append(large);
      fit.addEventListener('click',()=>scroll.classList.toggle('fit'));
      toolbar.append(close,fit,link);dialog.append(toolbar,scroll);document.body.append(dialog);
    }
    const large=dialog.querySelector('img');large.src=image.currentSrc||image.src;large.alt=image.alt;
    dialog.querySelector('a').href=large.src;dialog.setAttribute('aria-label',image.alt||'图示');dialog.showModal();
  }
  async function showVector(image) {
    const url=new URL(image.currentSrc||image.src);
    if(url.origin!==location.origin||!url.pathname.endsWith('.svg'))return;
    const response=await fetch(url);
    if(!response.ok)return;
    const svg=new DOMParser().parseFromString(await response.text(),'image/svg+xml').documentElement;
    if(svg.localName!=='svg'||svg.namespaceURI!=='http://www.w3.org/2000/svg'||!image.isConnected)return;
    const prefix='reader-vector-'+(++vectorId)+'-';
    for(const element of [svg,...svg.querySelectorAll('*')]){
      if(!vectorElements.has(element.localName)||element.namespaceURI!==svg.namespaceURI){element.remove();continue;}
      for(const {name,value} of [...element.attributes]){
        if(!vectorAttributes.has(name)||(/url\(/i.test(value)&&!/^url\(#[\w.-]+\)$/.test(value))){
          element.removeAttribute(name);
        }else if(name==='id'){
          element.setAttribute(name,prefix+value);
        }else if(name==='aria-labelledby'||name==='aria-describedby'){
          element.setAttribute(name,value.trim().split(/\s+/).map(id=>prefix+id).join(' '));
        }else if(value.startsWith('url(#')){
          element.setAttribute(name,'url(#'+prefix+value.slice(5));
        }
      }
    }
    if(!svg.hasAttribute('viewBox'))return;
    svg.setAttribute('role','img');
    if(!svg.hasAttribute('aria-labelledby'))svg.setAttribute('aria-label',image.alt);
    const region=document.createElement('div');region.className='reader-vector';
    const open=document.createElement('button');open.type='button';open.className='reader-vector-zoom';open.textContent='放大';
    open.setAttribute('aria-label','放大图示：'+image.alt);
    open.addEventListener('click',()=>zoom(image));
    region.append(open,document.importNode(svg,true));
    image.after(region);
    image.hidden=true;
    image.tabIndex=-1;
  }
  function references() {
    if(!referenceIndex)return;
    const doc=referenceIndex.documents.find(d=>d.pages.includes(currentRoute()));
    if(!doc)return;
    const route=location.pathname.replace(/\/$/,'');
    if(referenceRoute!==route){
      for(const link of document.querySelectorAll('article a.spec-reference'))link.replaceWith(document.createTextNode(link.textContent));
      processed=new WeakMap();referenceRoute=route;
    }
    const roots=document.querySelectorAll('article .standard-paragraph, article .standard-list-block, article .standard-definitions, article table.standard-table');
    for(const root of roots){
      if(!hydrated(root))continue;
      const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);const nodes=[];let node;
      while(node=walker.nextNode())if(processed.get(node)!==node.nodeValue&&!node.parentElement.closest('a,.katex,code,pre,script,style'))nodes.push(node);
      for(const node of nodes){
        const value=node.nodeValue;processed.set(node,value);const fragments=[];let cursor=0;
        const pattern=/(?:表|图)\s*(?:[A-Z]\s*[.．]\s*)?\d+|公式\s*[（(]\s*\d+\s*[）)]|\d+(?:\.\d+){1,5}(?![.\d])/g;
        for(const match of value.matchAll(pattern)){
          const label=match[0];let key;
          if(/^[表图]/.test(label))key=(label[0]==='表'?'table:':'figure:')+label.slice(1).replace(/\s/g,'').replaceAll('．','.');
          else if(label.startsWith('公式'))key='equation:'+label.match(/\d+/)[0];
          else{
            const before=value.slice(Math.max(0,match.index-12),match.index),after=value.slice(match.index+label.length);
            if(!/(?:见|按|依据|参照|符合|按照|满足|遵循|和|与|、|及|至|到|或|～|—|中|在|于|第)\s*$/.test(before)||/^\s*(?:GHz|MHz|kHz|Hz|ms|us|μs|ns|dB|%|字节|比特|秒)/.test(after))continue;
            key='clause:'+label;
          }
          const context=node.parentElement.closest('p,li,td,th,dd')||root;
          const range=document.createRange();range.setStart(context,0);range.setEnd(node,match.index);
          const scoped=globalThis.SparkLinkReferences.scopeFor(referenceIndex.documents,doc,range.toString());
          const target=scoped?.targets[key];if(!target)continue;
          if(match.index>cursor)fragments.push(document.createTextNode(value.slice(cursor,match.index)));
          const a=document.createElement('a');a.className='spec-reference';a.href=basePath+target.url;a.textContent=label;
          a.dataset.referenceScope=scoped.code;
          fragments.push(a);cursor=match.index+label.length;
        }
        if(!fragments.length)continue;
        if(cursor<value.length)fragments.push(document.createTextNode(value.slice(cursor)));
        node.replaceWith(...fragments);
      }
    }
  }
  function readingLink(label,route,params={}) {
    const link=document.createElement('a');
    const url=new URL(route+'/',siteRoot);
    url.search=new URLSearchParams(params).toString();
    link.href=url.pathname+url.search;
    link.textContent=label;
    return link;
  }
  function readingContext(title,route) {
    if(!referenceIndex||!hydrated(title))return;
    const doc=referenceIndex.documents.find(item=>item.prefix===route||item.pages.includes(route));
    if(!doc)return;
    const article=title.closest('article');
    const standard=doc.code.replace(/^GBT-/,'GB/T ');
    if(route===doc.prefix){
      const link=article.querySelector('.reading-related a');
      if(link&&!link.dataset.standardFilter){
        link.href=readingLink('','technical-index',{standard:doc.code}).href;
        link.dataset.standardFilter='true';
      }
      return;
    }
    const old=article.querySelector('.reader-context');
    if(old?.dataset.route===route)return;
    old?.remove();
    const nav=document.createElement('nav');
    nav.dataset.route=route;
    nav.className='reader-context';
    nav.setAttribute('aria-label','规范版本和相关阅读');
    nav.append(readingLink(standard,doc.prefix),readingLink('检索本标准','technical-index',{standard:doc.code}));
    const configuration=route.match(/^gbt-48336-201-2026-clause-7-5-(2|3)(?:-(\d+))?$/);
    if(configuration){
      const messages=configuration[1]==='2';
      const parent=doc.prefix+'-clause-7-5-'+configuration[1];
      nav.append(readingLink(messages?'报文索引':'信元索引','technical-index',{standard:doc.code,kind:messages?'message':'element',scope:messages?'7.5.2':'7.5.3'}));
      if(configuration[2])nav.append(readingLink('上级条款',parent));
      if(messages&&['2','3'].includes(configuration[2]))nav.append(readingLink('合读查询与反馈','slb-link-status'));
    }else if(/^gbt-48336-202-2026-clause-8(?:-[12]-|$)/.test(route)){
      nav.append(readingLink('一致性测试指南','slb-test-guide'));
    }
    title.after(nav);
  }
  function mobileOutline(title,route) {
    if(!hydrated(title))return;
    const article=title.closest('article');
    const existing=article.querySelector('.reader-mobile-outline');
    if(existing?.dataset.route===route)return;
    existing?.remove();
    const headings=[...article.querySelectorAll('h2[id],h3[id]')];
    if(headings.length<2)return;
    const menu=document.createElement('details');
    menu.className='reader-mobile-outline';
    menu.dataset.route=route;
    const summary=document.createElement('summary');
    summary.textContent='本页目录';
    const list=document.createElement('ul');
    for(const heading of headings){
      const item=document.createElement('li');
      if(heading.tagName==='H3')item.className='reader-outline-subsection';
      const link=document.createElement('a');
      link.href='#'+encodeURIComponent(heading.id);
      link.textContent=heading.textContent.replace(/^¶\s*|\s*¶$/g,'').trim();
      link.addEventListener('click',()=>{
        menu.open=false;
        heading.tabIndex=-1;
        heading.focus({preventScroll:true});
      });
      item.append(link);list.append(item);
    }
    menu.append(summary,list);
    (article.querySelector('.reader-context')||title).after(menu);
  }
  function copyLinks() {
    if(!navigator.clipboard?.writeText)return;
    for(const target of document.querySelectorAll('article :is(.standard-caption[id],.standard-table-caption[id],div[id*="-equation-"])')){
      if(!hydrated(target)||target.querySelector('.reader-copy-link'))continue;
      const id=target.id;
      if(!/-(?:figure|table|equation)-/.test(id))continue;
      const button=document.createElement('button');
      button.type='button';
      button.className='reader-copy-link';
      button.title='复制本处链接';
      const [,kind,number]=/-(figure|table|equation)-(.+)$/.exec(id);
      button.setAttribute('aria-label','复制'+{figure:'图',table:'表',equation:'公式'}[kind]+' '+number.replace('-', '.')+' 的链接');
      button.addEventListener('click',async()=>{
        const url=new URL(location.href);
        url.hash=id;
        try{
          await navigator.clipboard.writeText(url.href);
          button.dataset.copied='true';
          button.title='链接已复制';
          setTimeout(()=>{delete button.dataset.copied;button.title='复制本处链接';},1800);
        }catch{
          button.title='复制失败';
        }
      });
      (target.querySelector('p')||target).append(button);
    }
  }
  function install() {
    document.documentElement.lang='zh-CN';
    // The theme renders the frontmatter title separately and drops its MyST
    // label. Preserve a stable title target in both SSR and SPA navigation.
    const route=currentRoute();
    const title=document.querySelector('article h1');if(route&&title)title.id=route;
    readingContext(title,route);
    mobileOutline(title,route);
    const index=document.querySelector('article .technical-index');
    if(hydrated(index))globalThis.SparkLinkTechnicalIndex.install(index,siteRoot);
    copyLinks();
    const outline=document.querySelector('.myst-outline');
    if(hydrated(outline)){
      outline.setAttribute('aria-label','本页目录');
      const outlineHeader=outline.querySelector('.myst-outline-header');
      for(const node of outlineHeader?.childNodes||[]){
        if(node.nodeType===Node.TEXT_NODE&&node.nodeValue.trim()==='Contents')node.nodeValue='本页目录';
      }
      outline.querySelector('.myst-outline-collapsible')?.setAttribute('aria-label','展开或收起本页目录');
    }
    for(const button of document.querySelectorAll('button.myst-search-bar'))button.setAttribute('aria-label','搜索标准正文');
    for(const button of document.querySelectorAll('button[aria-label]')){
      const labels={'Open Folder':'展开条款','Close Folder':'收起条款','Toggle theme between light and dark mode':'切换明暗主题'};
      const label=labels[button.getAttribute('aria-label')];if(label){button.setAttribute('aria-label',label);if(button.title)button.title=label;}
    }
    for(const input of document.querySelectorAll('input[type="search"]'))input.setAttribute('placeholder','搜索术语、字段或条款…');
    for(const link of document.querySelectorAll('.myst-primary-sidebar a[href]'))if(hydrated(link)&&link.textContent.trim()==='Made with MyST')link.remove();
    for(const link of document.querySelectorAll('article :is(h1,h2,h3,h4,h5,h6) > a[href^="#"]')){
      if(link.textContent!=='¶'||link.dataset.readerPermalink)continue;
      // The theme's zero-width translated pilcrow overflows narrow headings.
      // Reserve a real gutter for the control while retaining all title text.
      link.dataset.readerPermalink='true';link.parentElement.style.paddingInlineEnd='1.5rem';
      Object.assign(link.style,{position:'absolute',insetInlineEnd:'0',top:'0',transform:'none',width:'1rem',textAlign:'center'});
      link.title='本节链接';link.setAttribute('aria-label','本节固定链接');
    }
    const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let node;
    while(node=walker.nextNode()){
      if(node.parentElement.closest('article,script,style,textarea,code,pre')||!hydrated(node.parentElement))continue;
      const value=node.nodeValue.trim();if(translations.has(value))node.nodeValue=node.nodeValue.replace(value,translations.get(value));
    }
    for(const image of document.querySelectorAll('article img.source-code,article img.source-figure,article img.standard-vector-figure')){
      image.decoding='async';if(image.dataset.readerBound)continue;
      image.dataset.readerBound='true';image.tabIndex=0;image.setAttribute('role','button');image.setAttribute('aria-label','放大：'+image.alt);
      image.addEventListener('click',()=>zoom(image));image.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();zoom(image);}});
      if(image.classList.contains('standard-vector-figure')) {
        showVector(image).catch(()=>{ /* The original image remains available. */ });
      }
    }
    for(const diagram of document.querySelectorAll('article .standard-diagram')){
      const svg=diagram.querySelector('figure svg');
      const width=svg?.viewBox.baseVal.width;
      if(!width||svg.dataset.readerLayout)continue;
      svg.dataset.readerLayout='true';
      svg.style.setProperty('--standard-diagram-width',Math.ceil(width)+'px');
      const caption=diagram.nextElementSibling?.matches('.standard-caption') ? diagram.nextElementSibling : null;
      diagram.tabIndex=0;
      diagram.setAttribute('role','region');
      diagram.setAttribute('aria-label',caption?.textContent.trim()||'标准流程图，可横向滚动');
    }
    for(const scroller of document.querySelectorAll('.table-scroll')){
      const figure=scroller.querySelector('table.figure-table');
      const caption=figure && scroller.nextElementSibling?.matches('.standard-caption') ? scroller.nextElementSibling : null;
      const figureTableLabel=scroller.querySelector('.figure-table-label')?.textContent.trim();
      scroller.tabIndex=0;
      scroller.setAttribute('role','region');
      scroller.setAttribute('aria-label',figureTableLabel||scroller.querySelector('.standard-table-caption')?.textContent||caption?.textContent||'标准表格，可横向滚动');
      const table=scroller.querySelector('table.standard-table:not(.figure-table)');
      const header=table?.rows[0];
      if(table?.rows.length>=25&&header?.cells.length&&[...header.cells].every(cell=>cell.tagName==='TH'&&cell.rowSpan===1)){
        const scrollHost=table.closest('[aria-label="table content"]')||scroller;
        scrollHost.classList.add('reader-long-table');
        header.classList.add('reader-sticky-header');
      }
      if(figure){
        if(caption?.id)figure.setAttribute('aria-labelledby',caption.id);
        if(figureTableLabel)figure.setAttribute('aria-label',figureTableLabel);
        for(const scope of ['row','col','colgroup']){
          for(const cell of figure.querySelectorAll('th.figure-table-scope-'+scope))cell.setAttribute('scope',scope);
        }
      }
    }
    references();
    // Hash navigation can precede hydration after a search/cross-reference.
    const hash=decodeURIComponent(location.hash.slice(1));
    if(hash&&!document.getElementById(hash))return;
  }
  function start(){
    // Do not translate or reparent SSR text while React is reconciling it.
    if(!hydrated(document.querySelector('article h1'))){setTimeout(start,30);return;}
    install();fetch(new URL('reader-index.json',scriptUrl)).then(r=>{if(!r.ok)throw new Error('Reference index HTTP '+r.status);return r.json();}).then(value=>{referenceIndex=value;install();window.__sparklinkReaderReady=true;}).catch(error=>{window.__sparklinkReaderError=String(error);console.error(error);});
    let pending=false;new MutationObserver(()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;install();});}).observe(document.body,{subtree:true,childList:true});
  }
  if(document.readyState==='complete')setTimeout(start,100);else window.addEventListener('load',()=>setTimeout(start,100),{once:true});
})();
