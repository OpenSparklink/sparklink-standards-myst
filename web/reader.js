(() => {
  const scriptUrl=document.currentScript?.src||new URL('reader.js',location.href).href;
  const basePath=new URL('.',scriptUrl).pathname.replace(/\/$/,'');
  const currentRoute=()=>location.pathname.slice(basePath.length).split('/').filter(Boolean)[0];
  let dialog,referenceIndex;
  let processed=new WeakMap(),referenceRoute;
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
  function install() {
    document.documentElement.lang='zh-CN';
    // The theme renders the frontmatter title separately and drops its MyST
    // label. Preserve a stable title target in both SSR and SPA navigation.
    const route=currentRoute();
    const title=document.querySelector('article h1');if(route&&title)title.id=route;
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
