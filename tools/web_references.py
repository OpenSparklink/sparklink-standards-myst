"""Stable, document-scoped targets for technical cross-references."""
import html,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def reference_targets(documents):
    output=[]
    for doc in documents:
        prefix=re.sub('[^a-z0-9]+','-',doc['code'].lower()).strip('-');targets={};pages=[]
        for chapter in doc['chapters']:
            path=ROOT/chapter['path'];text=path.read_text();lines=text.splitlines(keepends=True);result=[];fence=None
            for line in lines:
                marker=re.match(r'^(`{3,}|~{3,})',line)
                if marker:
                    if fence is None:fence=marker[1]
                    elif marker[1][0]==fence[0] and len(marker[1])>=len(fence):fence=None
                heading=None if fence else re.match(r'^#{1,6}\s+(\d+(?:\.\d+)*|[A-Z](?:\.\d+)+)\b',line)
                if heading:
                    key='clause:'+heading[1];label=prefix+'-clause-'+heading[1].lower().replace('.','-')
                    if key not in targets:
                        targets[key]={'url':'/'+chapter['slug']+'/#'+label,'anchor':label,'route':chapter['slug']}
                        if not ''.join(result).rstrip().endswith('('+label+')='):result.append('('+label+')=\n')
                result.append(line)
            text=''.join(result)
            for kind,cls,word in [('table','standard-table-caption','表'),('figure','standard-caption','图')]:
                pattern=re.compile(r'(?P<block>:::\{div\}\n:class: '+cls+r'\s*\n\s*<p>\s*'+word+r'\s*(?P<number>(?:[A-Z]\s*[.．]\s*)?\d+).*?</p>)',re.S)
                def annotate(match):
                    number=re.sub(r'\s','',match['number']).replace('．','.')
                    key=kind+':'+number;label=prefix+'-'+kind+'-'+number.lower().replace('.','-')
                    if key in targets:return match[0]
                    targets[key]={'url':'/'+chapter['slug']+'/#'+label,'anchor':label,'route':chapter['slug']}
                    before=text[:match.start()].rstrip()
                    return ('' if before.endswith('('+label+')=') else '('+label+')=\n')+match[0]
                text=pattern.sub(annotate,text)
            pattern=re.compile(r'```\{math\}\n(?P<body>.*?)\n```',re.S)
            def equation(match):
                tag=re.search(r'\\tag\{(\d+)\}',match['body'])
                if not tag:return match[0]
                number=tag[1];key='equation:'+number;label=prefix+'-equation-'+number
                if key in targets:return match[0]
                targets[key]={'url':'/'+chapter['slug']+'/#'+label,'anchor':label,'route':chapter['slug']}
                before=text[:match.start()].rstrip()
                return ('' if before.endswith('('+label+')=') else '('+label+')=\n')+match[0]
            text=pattern.sub(equation,text);path.write_text(text)
            pages.append(chapter['slug'])
        output.append({'code':doc['code'],'prefix':prefix,'pages':pages,'targets':targets})
    (ROOT/'metadata/web-references.json').write_text(json.dumps({'documents':output},ensure_ascii=False,separators=(',',':'))+'\n')
