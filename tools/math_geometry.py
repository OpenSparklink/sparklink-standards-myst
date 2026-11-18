"""Recover stacked fractions inside table cells from PDF fraction bars."""
import statistics
import re
from native_math import to_latex,source_text,atom


def overlines(page,spans):
    """Recover vector overbars drawn as rules above mathematical letters."""
    rules=[]
    for drawing in page.get_drawings():
        for item in drawing['items']:
            if item[0]=='l':
                a,b=item[1:3]
                if abs(a.y-b.y)<.1 and 2<abs(a.x-b.x)<35:rules.append((min(a.x,b.x),a.y,max(a.x,b.x)))
    used=[]
    for span in spans:
        text=source_text(span).strip()
        if not re.fullmatch('[A-Za-z]',text) or not span['font'].startswith('FzBookMaker'):continue
        size=span['size'];x=span['origin'][0];y=span['origin'][1]
        choices=[r for r in rules if .65*size<y-r[1]<1.4*size and x-1<r[0]<x+size*.25 and .3*size<r[2]-r[0]<1.1*size and r[2]<x+size*1.15]
        if not choices:continue
        rule=min(choices,key=lambda r:abs(r[0]-x));value=atom(span)
        if value:
            span['_latex']=r'\overline{'+value+'}';span['_source_overline']=rule;used.append({'text':text,'origin':span['origin'],'rule':rule})
    return used


def fractions(page,spans,cell):
    if not hasattr(page,'_fraction_rules'):
        rules=[]
        for drawing in page.get_drawings():
            for item in drawing['items']:
                if item[0]=='l':
                    a,b=item[1:3]
                    if abs(a.y-b.y)<.15 and abs(a.x-b.x)>4:rules.append((min(a.x,b.x),a.y,max(a.x,b.x)))
                elif item[0]=='re':
                    r=item[1]
                    if r.height<.7 and r.width>4:rules.append((r.x0,(r.y0+r.y1)/2,r.x1))
        page._fraction_rules=sorted(set(rules),key=lambda r:r[2]-r[0])
    active=list(spans)
    for x0,y,x1 in page._fraction_rules:
        if not(cell[0]+2<x0<x1<cell[2]-2 and cell[1]+2<y<cell[3]-2):continue
        selected=[s for s in active if x0-.8<=(s['bbox'][0]+s['bbox'][2])/2<=x1+.8 and abs(s['origin'][1]-y)<22 and not re.fullmatch(r'[\[\]()⌈⌉⌊⌋]',source_text(s).strip())]
        above=[s for s in selected if s['origin'][1]<y+1]
        below=[s for s in selected if s['origin'][1]>y+2]
        if not above or not below:continue
        numerator=to_latex(above,force=True);denominator=to_latex(below,force=True)
        if not numerator or not denominator:continue
        ids={id(s) for s in above+below}
        active=[s for s in active if id(s) not in ids]
        size=max(s['size'] for s in above+below)
        active.append({'font':'NativeMath','text':'fraction','source_text':'fraction','size':size,
                       'flags':0,'origin':(x0,y+size*.35),'bbox':(x0,y-size,x1,y+size),
                       '_latex':r'\frac{'+numerator+'}{'+denominator+'}'})
    return active
