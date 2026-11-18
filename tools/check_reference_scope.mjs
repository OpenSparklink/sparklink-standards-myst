import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
await import('../web/reference_scope.js');
const documents=JSON.parse(await fs.readFile('metadata/web-references.json','utf8')).documents;
const current=documents.find(d=>d.code==='GBT-48336.101-2026');
const cases=[
 ['见',current.code],
 ['见 GB/T 48336.201—2026 中的','GBT-48336.201-2026'],
 ['GB/T48336.202中的','GBT-48336.202-2026'],
 ['GB/T 1.1—2020 中的',null],
 ['GB/T 48336.201—2025 中的',null],
 ['符合 GB/T 48336.201—2026，且按本文件',current.code],
 ['GB/T 1.1—2020。参见',current.code],
 ['见 3GPP TS 38.211 中的',null],
 ['见 ISO/IEC 18000 中的',null],
];
for(const [text,expected] of cases)assert.equal(globalThis.SparkLinkReferences.scopeFor(documents,current,text)?.code||null,expected,text);
const report={manifest_sha256:createHash('sha256').update(await fs.readFile('metadata/reading-manifest.json')).digest('hex'),cases:cases.length,issues:[]};
await fs.writeFile('metadata/reference-scope-check.json',JSON.stringify(report,null,2)+'\n');
console.log('Reference scope: '+cases.length+' cases passed');
