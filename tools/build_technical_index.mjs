import fs from 'node:fs/promises';
import path from 'node:path';

const clauseHeading = /^#{1,6} +(\d+(?:\.\d+)*|[A-Z](?:\.\d+)+)\s+(.+)$/;
const codeFence = /^ {0,3}(`{3,}|~{3,})([^\r\n]*)$/;
const assignment = /^\s*([A-Z][\w-]+)\s*::=/;
const component = /^\s*([a-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*)\s+(?=[A-Z[])/;

function plainTitle(value) {
  return value
    .replace(/<[^>]*>/g, '')
    .replace(/&(?:amp|lt|gt|quot|apos);/g, entity => ({
      '&amp;':'&', '&lt;':'<', '&gt;':'>', '&quot;':'"', '&apos;':"'",
    })[entity])
    .replace(/\\([*_{}\[\]$()<>])/g, '$1')
    .trim();
}

function scanSource(source) {
  const headings = new Map();
  const captions = new Map();
  const definitions = [];
  let fence, definition;
  let depth = 0;
  let clause;
  for (const line of source.split('\n')) {
    const marker = codeFence.exec(line);
    if (marker) {
      if (!fence) fence = { marker:marker[1], asn1:marker[2].trim() === 'asn1' };
      else if (marker[1][0] === fence.marker[0] && marker[1].length >= fence.marker.length && !marker[2].trim()) {
        fence = null;
        definition = null;
        depth = 0;
      }
      continue;
    }
    if (fence) {
      if (!fence.asn1) continue;
      const code = line.split('--', 1)[0];
      const name = assignment.exec(code)?.[1];
      if (name) {
        definition = { name, clause, fields:new Set() };
        definitions.push(definition);
        depth = 0;
      } else if (definition && depth > 0) {
        const field = component.exec(code)?.[1];
        if (field) definition.fields.add(field);
      }
      if (definition) depth += (code.match(/\{/g)||[]).length - (code.match(/\}/g)||[]).length;
      continue;
    }
    const heading = clauseHeading.exec(line);
    if (heading) {
      clause = heading[1];
      headings.set(clause, plainTitle(heading[2]));
    }
    const caption = /^\s*<p>\s*([图表])\s*((?:[A-Z]\s*[.．]\s*)?\d+)\s+[　 ]*(.+)<\/p>\s*$/.exec(line);
    if (caption) {
      const number = caption[2].replace(/\s/g, '').replace('．', '.');
      captions.set((caption[1] === '图' ? 'figure:' : 'table:') + number, plainTitle(caption[3]));
    }
  }
  return { headings, captions, definitions };
}

const labels = { clause:'条款', figure:'图', table:'表', equation:'公式' };
function testRole(doc, clause) {
  if (doc.part !== '202') return '';
  if (/^8\.1\.\d+\.\d+/.test(clause)) return 'G';
  if (/^8\.2\.\d+\.\d+/.test(clause)) return 'T';
  return '';
}

export async function buildTechnicalIndex(root, out, manifest) {
  const referenceIndex = JSON.parse(await fs.readFile(path.join(root,'metadata/web-references.json'),'utf8'));
  const standards = [];
  const entries = [];
  for (const doc of manifest.documents) {
    const reference = referenceIndex.documents.find(item => item.code === doc.code);
    if (!reference) throw new Error('Missing reference index for ' + doc.code);
    const standard = { code:doc.code, label:doc.standard, title:doc.display_title };
    standards.push(standard);
    entries.push({ kind:'standard', code:doc.code, title:doc.display_title, number:doc.standard, url:'/'+reference.prefix+'/' });
    const add = (kind, title, number, url, detail = '', role = '') =>
      entries.push({ kind, title, number, code:doc.code, url, ...(detail && { detail }), ...(role && { role }) });
    const chapters = new Map(await Promise.all(doc.chapters.map(async chapter => [
      chapter.slug,
      { chapter, ...scanSource(await fs.readFile(path.join(root,chapter.path),'utf8')) },
    ])));
    for (const [key, target] of Object.entries(reference.targets)) {
      const [kind, number] = key.split(':');
      const source = chapters.get(target.route);
      if (!source) throw new Error('Missing target chapter for ' + target.url);
      const title = kind === 'clause' ? source.headings.get(number) : source.captions.get(key);
      const role = kind === 'clause' ? testRole(doc,number) : '';
      const isTest = role || kind === 'clause' && /测试(?:方法|用例|目的|步骤)/.test(title || '');
      add(isTest ? 'test' : kind, title || labels[kind]+' '+number, number, target.url, '', role);
    }
    const indexed = new Set();
    for (const {chapter, definitions} of chapters.values()) {
      const primaryMessages = new Set();
      for (const {name, clause, fields} of definitions) {
        const target = reference.targets['clause:'+clause];
        const url = target?.route === chapter.slug ? target.url : '/'+chapter.slug+'/#'+chapter.slug;
        const id = url + ':' + name;
        if (!indexed.has(id)) {
          const isMessage = doc.part === '201' && /^7\.5\.2\.\d+$/.test(clause) && !primaryMessages.has(clause);
          if (isMessage) primaryMessages.add(clause);
          indexed.add(id);
          add(isMessage ? 'message' : 'element', name, clause || '', url, chapter.title);
        }
        for (const field of fields) {
          const fieldId = id+':'+field;
          if (indexed.has(fieldId)) continue;
          indexed.add(fieldId);
          add('field', field, clause || '', url, name);
        }
      }
    }
  }
  await fs.writeFile(path.join(out,'technical-index.json'),JSON.stringify({version:1,standards,entries}));
  console.log(`Indexed ${entries.length} technical references, ASN.1 symbols and tests from ${standards.length} standards.`);
}
