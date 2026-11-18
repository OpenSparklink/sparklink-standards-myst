#!/usr/bin/env python3
"""Compare every chapter heading and its level with the generated HTML."""
import hashlib
import html
import json
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class Headings(HTMLParser):
    def __init__(self):
        super().__init__();self.article=0;self.heading=None;self.text='';self.rows=[]

    def handle_starttag(self,tag,attrs):
        if tag=='article':self.article+=1
        if self.article and re.fullmatch(r'h[1-6]',tag):self.heading=tag;self.text=''

    def handle_data(self,data):
        if self.heading:self.text+=data

    def handle_endtag(self,tag):
        if tag==self.heading:self.rows.append((int(tag[1]),self.text.rstrip('¶')));self.heading=None
        if tag=='article':self.article-=1


def normalize(value):
    value=re.sub(r'\\([`*_{}\[\]()#+.!$<>-])',r'\1',value)
    return re.sub(r'\s','',unicodedata.normalize('NFKC',html.unescape(value)))


def main():
    path=ROOT/'metadata/reading-manifest.json';manifest=json.loads(path.read_text());issues=[];results=[];total=0
    for doc in manifest['documents']:
        for chapter in doc['chapters']:
            source=(ROOT/chapter['path']).read_text()
            expected=[(len(level),normalize(title)) for level,title in re.findall(r'^(#{1,6}) (.+)$',source,re.M)]
            parser=Headings();parser.feed((ROOT/'_build/html'/chapter['slug']/'index.html').read_text())
            actual=[(level,normalize(title)) for level,title in parser.rows];total+=len(actual)
            if expected!=actual:issues.append({'chapter':chapter['path'],'expected':expected,'actual':actual})
            results.append({'chapter':chapter['slug'],'headings':len(actual)})
    report={'manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'chapters':len(results),'headings':total,'issues':issues,'results':results}
    (ROOT/'metadata/heading-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('chapters','headings')}|{'issues':len(issues)}))
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
