import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import katex from 'katex';
const manifest=JSON.parse(await fs.readFile('metadata/reading-manifest.json','utf8'));
const issues=[],results=[];
for (const doc of manifest.documents) {
  let count=0;
  for (const chapter of doc.chapters) {
    const source=await fs.readFile(chapter.path,'utf8');
    const math=[...source.matchAll(/\$([^$\n]+)\$/g)].map(m=>({value:m[1],displayMode:false}));
    math.push(...[...source.matchAll(/^```\{math\}\n([\s\S]*?)\n```/gm)].map(m=>({value:m[1],displayMode:true})));
    for (const expression of math) {
      count++;
      try {katex.renderToString(expression.value,{displayMode:expression.displayMode,throwOnError:true});}
      catch(error){issues.push({file:chapter.path,value:expression.value,error:String(error)});}
    }
  }
  results.push({code:doc.code,expressions:count});
}
const report={manifest_sha256:createHash('sha256').update(await fs.readFile('metadata/reading-manifest.json')).digest('hex'),documents:results.length,expressions:results.reduce((n,r)=>n+r.expressions,0),issues,results};
await fs.writeFile('metadata/native-math-check.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report));
if (issues.length) process.exitCode=1;
