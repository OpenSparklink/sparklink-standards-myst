// HTML tables preserve spans; recover their dollar math as native MyST AST.
// Render every math node with the same version as the bundled math CSS.
import katex from 'katex';
export function renderMath(value,displayMode){
  if(!displayMode)return katex.renderToString(value,{displayMode:false,throwOnError:true});
  const tag=value.match(/\\tag\{([A-Za-z0-9. -]+)\}/);
  const body=tag?value.replace(tag[0],''):value;
  const rendered=katex.renderToString(body,{displayMode:true,throwOnError:true});
  return `<span class="standard-equation-row"><span class="standard-equation-math">${rendered}</span>${tag?`<span class="standard-equation-number">(${tag[1]})</span>`:''}</span>`;
}
export default {
  name:'Native mathematics in structured HTML',
  transforms:[{
    name:'math-in-html',stage:'document',
    plugin:()=>tree=>{
      function walk(node){
        if (!Array.isArray(node.children)) return;
        node.children=node.children.flatMap(child=>{
          if (child.type==='inlineMath' || child.type==='math') {
            child.html=renderMath(child.value,child.type==='math');return [child];
          }
          if (child.type!=='text') {walk(child);return [child];}
          const text=child.value || '';const parts=[];let cursor=0;
          for (const match of text.matchAll(/(?<!\\)\$([^$\n]+)\$/g)) {
            if (match.index>cursor) parts.push({type:'text',value:text.slice(cursor,match.index)});
            const value=match[1];
            parts.push({type:'inlineMath',value,html:katex.renderToString(value,{displayMode:false,throwOnError:true})});
            cursor=match.index+match[0].length;
          }
          if (!parts.length) return [child];
          if (cursor<text.length) parts.push({type:'text',value:text.slice(cursor)});
          return parts;
        });
      }
      walk(tree);
    }
  }]
};
