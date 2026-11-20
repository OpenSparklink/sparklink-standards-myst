(() => {
  const kinds = new Map([
    ['standard','标准'], ['clause','条款'], ['message','报文'], ['element','信元和类型'],
    ['field','字段'], ['test','测试'], ['figure','图'], ['table','表'], ['equation','公式'],
  ]);
  const preferredKinds = ['standard','message','element','test','clause','field','figure','table','equation'];
  const pageSize = 30;
  const mounted = new WeakSet();
  let indexRequest;

  function element(tag, text, attributes = {}) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    for (const [name,value] of Object.entries(attributes)) node.setAttribute(name,value);
    return node;
  }

  function normalize(value) {
    return value.normalize('NFKC').toLowerCase().replace(/[§/]/g,'').replace(/\s+/g,'');
  }

  function select(label, options) {
    const input = element('select');
    for (const [value, text] of options) input.append(element('option',text,{value}));
    const wrapper = element('label',label);
    wrapper.append(input);
    return [wrapper,input];
  }

  function mount(root, data, siteRoot) {
    const standards = new Map(data.standards.map(standard => [standard.code,standard]));
    const entries = data.entries.map(entry => ({
      ...entry,
      terms: [entry.title,entry.number,kinds.get(entry.kind)+entry.number,entry.detail || '',entry.code,standards.get(entry.code).label]
        .map(normalize),
    }));
    const form = element('form','',{role:'search','aria-label':'查找技术条目'});
    form.className = 'technical-index-filters';
    const search = element('input','',{type:'search',placeholder:'如 requestType、CSI-RS4、7.5.2.2'});
    const searchLabel = element('label','搜索名称或编号');
    searchLabel.className = 'technical-index-query';
    searchLabel.append(search);
    const [kindLabel,kind] = select('类别',[['','全部类别'],...kinds]);
    const [standardLabel,standard] = select('规范版本',[['','全部标准'],...data.standards.map(item=>[item.code,item.label])]);
    const [roleLabel,role] = select('测试角色',[['','全部角色'],['G','G 节点'],['T','T 节点']]);
    standardLabel.className = 'technical-index-standard';
    form.append(searchLabel,standardLabel,kindLabel,roleLabel);
    const status = element('p','',{role:'status','aria-live':'polite'});
    status.className = 'technical-index-status';
    const list = element('ol');
    list.className = 'technical-index-results';
    const pagination = element('nav','',{'aria-label':'索引结果分页'});
    pagination.className = 'technical-index-pagination';
    const previous = element('button','上一页',{type:'button'});
    const next = element('button','下一页',{type:'button'});
    pagination.append(previous,next);
    const clearScope = element('button','',{type:'button'});
    clearScope.className = 'technical-index-scope';
    form.append(clearScope);
    let results = [];
    let page = 0;
    let scope = '';

    function render() {
      const from = page * pageSize;
      status.textContent = results.length ? `共 ${results.length} 项，显示 ${from+1}–${Math.min(from+pageSize,results.length)} 项`
        : '未找到匹配的条目。可以缩短关键词或调整筛选条件。';
      list.replaceChildren(...results.slice(from,from+pageSize).map(({entry})=>{
        const item = element('li');
        const category = kinds.get(entry.kind);
        const title = entry.kind === 'standard' ? entry.title : entry.title === category+' '+entry.number ? entry.title
          : ['clause','test','figure','table','equation'].includes(entry.kind)
            ? (entry.kind === 'test' || entry.kind === 'clause' ? '§'+entry.number : category+' '+entry.number)+' '+entry.title
            : entry.title;
        const target = new URL(entry.url.slice(1),siteRoot);
        const link = element('a',title,{href:target.pathname+target.hash});
        const meta = [category, standards.get(entry.code).label, entry.role ? entry.role+' 节点' : '', entry.detail || ''].filter(Boolean);
        item.append(link,element('p',meta.join(' · ')));
        return item;
      }));
      pagination.hidden = results.length <= pageSize;
      previous.disabled = page === 0;
      next.disabled = from+pageSize >= results.length;
    }

    function filter() {
      const keywords = search.value.trim().split(/\s+/).map(normalize).filter(Boolean);
      const category = kind.value;
      results = [];
      for (const entry of entries) {
        if ((category && category !== entry.kind)
          || (standard.value && standard.value !== entry.code)
          || (role.value && role.value !== entry.role)
          || (scope && !entry.number.startsWith(scope+'.'))) continue;
        let score = 0;
        for (const keyword of keywords) {
          const [title, number, ...metadata] = entry.terms;
          const match = title === keyword || number === keyword ? 8
            : title.startsWith(keyword) || number.startsWith(keyword) ? 5
            : title.includes(keyword) || number.includes(keyword) ? 3
            : metadata.some(value=>value.includes(keyword)) ? 1 : 0;
          if (!match) { score = -1; break; }
          score += match;
        }
        if (score >= 0) results.push({entry,score});
      }
      if (keywords.length) results.sort((a,b)=>b.score-a.score || preferredKinds.indexOf(a.entry.kind)-preferredKinds.indexOf(b.entry.kind));
      page = 0;
      render();
    }

    function restore() {
      const params = new URLSearchParams(location.search);
      const requestedScope = params.get('scope') || '';
      scope = /^\d+(?:\.\d+)*$/.test(requestedScope) ? requestedScope : '';
      clearScope.hidden = !scope;
      clearScope.textContent = scope ? '§'+scope+' · 清除条款范围' : '';
      for (const [name,control] of [['q',search],['kind',kind],['standard',standard],['role',role]]) {
        control.value = params.get(name) || '';
        if (control instanceof HTMLSelectElement && control.selectedIndex < 0) control.value = '';
      }
      filter();
    }

    function update() {
      filter();
      const url = new URL(location.href);
      for (const [name,control] of [['q',search],['kind',kind],['standard',standard],['role',role]]) {
        if (control.value.trim()) url.searchParams.set(name,control.value.trim());
        else url.searchParams.delete(name);
      }
      if (!scope) url.searchParams.delete('scope');
      history.replaceState(history.state,'',url);
    }
    form.addEventListener('submit',event=>{event.preventDefault();update();});
    search.addEventListener('input',update);
    for (const control of [kind,standard,role]) control.addEventListener('change',update);
    clearScope.addEventListener('click',()=>{scope='';clearScope.hidden=true;search.focus();update();});
    previous.addEventListener('click',()=>{page--;render();});
    next.addEventListener('click',()=>{page++;render();});
    const download = element('a','下载技术索引 JSON',{
      href:new URL('technical-index.json',siteRoot).pathname,download:'sparklink-technical-index.json',
    });
    const exportLink = element('p');
    exportLink.append(download);
    root.append(form,status,list,pagination,exportLink);
    // Hide MyST's fallback paragraph after the index is ready. React still owns it.
    const fallback=root.querySelector(':scope > p');
    if(fallback)fallback.hidden = true;
    restore();
  }

  globalThis.SparkLinkTechnicalIndex = {
    install(root, siteRoot) {
      if (!root || mounted.has(root)) return;
      mounted.add(root);
      indexRequest ??= fetch(new URL('technical-index.json',siteRoot)).then(response=>{
        if (!response.ok) throw new Error('Technical index HTTP '+response.status);
        return response.json();
      }).catch(error=>{indexRequest=undefined;throw error;});
      indexRequest.then(data=>{if(root.isConnected) mount(root,data,siteRoot);}).catch(()=>{
        const fallback=root.querySelector(':scope > p');
        if(fallback) fallback.textContent='技术索引暂时无法加载。可以使用站点搜索或下方的标准目录。';
      });
    },
  };
})();
