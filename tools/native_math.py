"""Recover simple PDF math as editable LaTeX, preserving source baselines."""
import re
import statistics
from functools import lru_cache
from recover_201 import load_map

# Glyphs checked directly in the source, not inferred from OCR text.
ITALIC={
    '!':'b','"':'f','#':'T','$':'N','%':'L','&':'p',"'":'k','(':'l',')':'a',
    '*':'d','+':'n',',':'j','-':'u','.':'=','/':'r','0':'+','1':'×','2':'M','3':'c',
    '4':'i','5':'D','6':'K','7':'S','8':'t','9':'P',':':'X',';':'e','=':'g',
    '>':'C','?':'G','@':'Y','A':'v','B':'E','C':'Q','D':'R','E':'A','F':'B',
    'G':'x','H':'V','I':'y','K':'s','L':'W','M':'I','N':'F','O':'w','P':'m',
    'Q':'h','S':'o','T':'Z','V':'z','<':'-','J':"'",'R':'.','U':'-',' ':' '}
BOLD={'!':'N','"':'L','#':'X','$':'a','%':'Q','&':'G',"'":'g','(':'d',')':'u',
      '*':'T','+':'p',',':'w','-':'x','.':'y','/':'H','0':'n',' ':' '}
GREEK={'!':'ρ','"':'φ','#':'θ','$':'ν','%':'α','&':'β',"'":'τ','(':'δ',')':'Φ',
       '*':'λ','+':'ψ',',':'π','-':'~','.':'ϕ',' ':' '}
SYMBOL={'!':'Ⅲ','"':'Ⅴ','#':'Ⅰ','$':'Ⅱ','%':'Ⅳ','&':'Ⅵ',"'":'Ⅶ','(':'Ⅷ',
        ')':'Δ','*':'#','+':'π',',':'~','-':'φ','.':'μ','/':'a',' ':' '}
PUNCT={'!':':','"':'(', '#':')','$':'…','%':'/','&':'—',"'":'《','(':'》',')':'。',
       '*':';','+':'、',',':',','-':'[','.':']','/':'“','0':'”','1':'·','2':'{',
       '3':'⋮','4':'}','5':'-','6':'!','7':'‘','8':'’','9':'?',':':'<',';':'>',' ':' '}
SPECIAL={'×':r'\times ','·':r'\cdot ','−':'-','—':'-', '≤':r'\leq ','≥':r'\geq ',
         '≠':r'\ne ','≈':r'\approx ','∞':r'\infty ','∑':r'\sum ','∏':r'\prod ',
         '√':r'\sqrt{}','…':r'\ldots ','⋯':r'\cdots ','⋮':r'\vdots ',
         'α':r'\alpha ','β':r'\beta ','γ':r'\gamma ','δ':r'\delta ','Δ':r'\Delta ',
         'ε':r'\epsilon ','θ':r'\theta ','λ':r'\lambda ','μ':r'\mu ','ν':r'\nu ',
         'ρ':r'\rho ','π':r'\pi ','φ':r'\phi ','Φ':r'\Phi ','ψ':r'\psi ','τ':r'\tau ',
         'σ':r'\sigma ','ω':r'\omega ','Ω':r'\Omega ','ϕ':r'\varphi ',
         '±':r'\pm ','∈':r'\in ','∉':r'\notin ','⊕':r'\oplus ','⊗':r'\otimes ',
         '∥':r'\parallel ','∪':r'\cup ','∶':':','≡':r'\equiv ','∫':r'\int ',
         '。':r'\text{。}','；':r'\text{；}','、':r'\text{、}','，':',','ˆ':'^','’':"'",'“':r'\text{“}','”':r'\text{”}',
         '⌈':r'\lceil ','⌉':r'\rceil ','⌊':r'\lfloor ','⌋':r'\rfloor ',
         '′':"'",'″':"''",'~':r'\sim ','#':r'\#','∖':r'\setminus ',
         '{':r'\{','}':r'\}','Ⅲ':r'\mathrm{III}','Ⅴ':r'\mathrm{V}',
         'Ⅰ':r'\mathrm{I}','Ⅱ':r'\mathrm{II}','Ⅳ':r'\mathrm{IV}',
         'Ⅵ':r'\mathrm{VI}','Ⅶ':r'\mathrm{VII}','Ⅷ':r'\mathrm{VIII}'}
MATH_FONT=re.compile(r'^FzBookMaker(?:9Dl|13Dl|14Dl|15Dl)|Italic|Math|Symbol|^E-BX$',re.I)


@lru_cache(maxsize=1)
def glyph_map():return load_map()


def source_text(span):
    font=span.get('font','');raw=span.get('source_text',span['text'])
    fixed={'FzBookMaker13DlFont13':ITALIC,'FzBookMaker14DlFont14':BOLD,
           'FzBookMaker15DlFont15':GREEK,'FzBookMaker9DlFont9':SYMBOL,
           'FzBookMaker7DlFont705368':PUNCT}.get(font)
    if fixed is not None:return ''.join(glyph_map().get(font+'\t'+c,fixed.get(c,'□')) for c in raw)
    if font=='FzBookMaker2DlFont2':
        return ''.join('×' if c=='b' else glyph_map().get(font+'\t'+c,c if c.isspace() else '□') for c in raw)
    if font=='FzBookMaker6DlFont6':return ''.join(glyph_map().get(font+'\t'+c,'□') for c in raw)
    return span['text'].replace('\U00100ba8','˜').replace('\U00100c4b','⊗')


def is_math(span):
    return bool(MATH_FONT.search(span.get('font','')) or re.search(r'[×·≤≥≠∑∏√α-ωΑ-Ωϕ∈∥∪≡±∞˜¯∖]',source_text(span)))


def atom(span,script=False):
    if span.get('_latex'):return span['_latex']
    text=source_text(span).strip().translate(str.maketrans('（）［］，：','()[],:'))
    if not text:return ''
    if '√' in text:return None
    if re.search(r'[\u3400-\u9fff□\x00-\x1f]',text):return None
    font=span.get('font','')
    if font=='FzBookMaker0DlFont0' and re.fullmatch('[A-Za-z0-9]+',text):return r'\mathbf{'+text+'}'
    if re.search(r'FzBookMaker13DlFont13|Italic|^E-BX$',font):
        return ''.join(SPECIAL.get(c,c) for c in text)
    if font=='FzBookMaker14DlFont14':return r'\mathbf{'+text+'}'
    parts=[]
    for token in re.findall(r'[A-Za-z]+|\d+(?:\.\d+)?|.',text):
        if token.isspace():continue
        if token.isalpha() and token.isascii():
            parts.append(r'\mathrm{'+token+'}' if len(token)>1 or script else token)
        elif token in SPECIAL:parts.append(SPECIAL[token])
        elif re.fullmatch(r"[0-9.+\-*/=<>(),\[\]:;!|%'′]+",token):parts.append(token.replace('%',r'\%'))
        elif token=='_':parts.append(r'\_')
        else:return None
    return ''.join(parts)


def spatial_scripts(spans,accents,script_context=False):
    """Retain nested scripts using the source font sizes and baselines.

    In the damaged PDF a third-level script is about 87% of a second-level
    script. Flattening all small text into one pending string loses N_max
    inside Q's exponent and mixes simultaneous upper/lower indices.
    """
    ordinary=[s for s in spans if not re.fullmatch(r'[()\[\]{}⎧⎩⎫⎭∑∏∫⌈⌉⌊⌋√˜¯\s]+',source_text(s))]
    base=max(s['size'] for s in ordinary or spans)
    main=[s for s in ordinary or spans if s['size']>=base*.94]
    baseline=statistics.median(s['origin'][1] for s in main)
    damaged=any(s['font'].startswith('FzBookMaker') for s in spans)
    offset=1 if damaged else max(.15,base*.035)
    output=[];pending=[]
    def finish():
        for kind,children in pending:
            value=spatial_scripts(children,accents,True)
            if value is None:return False
            output[-1]+=kind+'{'+value+'}'
        pending.clear();return True
    for span in sorted(spans,key=lambda s:s['bbox'][0]):
        if source_text(span).strip() in ('˜','¯'):continue
        if source_text(span).strip() in ("'",'′','″') and output:
            output[-1]+=SPECIAL.get(source_text(span).strip(),"'")
            continue
        if span['size']<base*.94 and (damaged or abs(span['origin'][1]-baseline)>offset or span.get('flags',0)&1):
            if not output:return None
            kind='^' if span['origin'][1]<baseline-offset else '_'
            entry=next((p for p in pending if p[0]==kind),None)
            if entry:entry[1].append(span)
            else:pending.append([kind,[span]])
            continue
        if pending and not finish():return None
        value=atom(span,script_context)
        if value is None:return None
        if id(span) in accents:value=accents[id(span)]+'{'+value+'}'
        output.append(value)
    if pending and not finish():return None
    return ''.join(output)


def to_latex(spans,force=False):
    spans=[dict(s) for s in spans if source_text(s).strip()]
    if not spans:return None
    plain=''.join(source_text(s) for s in spans)
    ordinary=[s for s in spans if not re.fullmatch(r'[()\[\]{}⎧⎩⎫⎭∑∏∫⌈⌉⌊⌋√˜¯\s]+',source_text(s))]
    base=max(s['size'] for s in ordinary or spans)
    main=[s for s in ordinary or spans if s['size']>=base*.85]
    main_text=''.join(source_text(s) for s in main)
    scalar_assignment=bool(re.search('=',main_text)) and not re.search(r'[\u3400-\u9fff]',plain)
    reference_y=statistics.median(s['origin'][1] for s in main)
    has_scripts=any(s['size']<base*.94 and abs(s['origin'][1]-reference_y)>1 for s in spans)
    if not force and not any(is_math(s) for s in spans) and not scalar_assignment and not has_scripts:return None
    if re.search(r'[A-Za-z]{4,}\s+[A-Za-z]{4,}',plain) and not re.search(r'[=×·≤≥≠∑∏√]',plain):return None
    baseline=statistics.median(s['origin'][1] for s in main)
    # Stacked full-size terms require a fraction/matrix transcription, not a
    # guessed flattened expression. Leave them to the explicit review list.
    if max(s['origin'][1] for s in main)-min(s['origin'][1] for s in main)>base*.6:return None
    accents={}
    for accent in spans:
        a=source_text(accent).strip()
        if a not in ('˜','¯'):continue
        candidates=[s for s in spans if s is not accent and source_text(s).strip() not in ('˜','¯') and s['bbox'][0]-2<accent['bbox'][0]<s['bbox'][2]+2 and s['origin'][1]>accent['origin'][1]]
        if not candidates:return None
        target=min(candidates,key=lambda s:abs(s['bbox'][0]-accent['bbox'][0])+abs(s['origin'][1]-accent['origin'][1]))
        accents[id(target)]=r'\widetilde' if a=='˜' else r'\overline'
    output=[];pending=[]
    encoded=spatial_scripts(spans,accents)
    for span in ([] if encoded is not None else sorted(spans,key=lambda s:s['bbox'][0])):
        if source_text(span).strip() in ('˜','¯'):continue
        script=span['size']<base*.8
        value=atom(span,script)
        if value is None:return None
        if not value:continue
        if id(span) in accents:value=accents[id(span)]+'{'+value+'}'
        if script:
            if not output:return None
            kind='^' if span['origin'][1]<baseline-1 else '_'
            existing=next((entry for entry in pending if entry[0]==kind),None)
            if existing:existing[1]+=value
            else:pending.append([kind,value])
        else:
            for kind,val in pending:output[-1]+=kind+'{'+val+'}'
            pending=[];output.append(value)
    for kind,val in pending:output[-1]+=kind+'{'+val+'}'
    value=encoded.strip() if encoded is not None else ''.join(output).strip()
    value=re.sub(r'\^(\([^)]*\)|[A-Za-z0-9])',lambda m:'^{'+m[1]+'}',value)
    value=value.replace('<',r'\lt ').replace('>',r'\gt ')
    for token in ('to','endif','endfor','endwhile'):
        word='end '+token[3:] if token.startswith('end') else token
        value=value.replace(r'\mathrm{'+token+'}',r'\;\text{'+word+r'}\;')
    if not value or len(value)>2000:return None
    # Inline runs can end at prose embedded inside parentheses. Literal
    # delimiters are legal TeX and must not force a bitmap fallback.
    return value


def is_separator(span,group):
    text=source_text(span).strip()
    if re.fullmatch('—+',text):return True
    if re.fullmatch(r'[。；、：“”‘’《》]+',text):return True
    if text not in (',',':',';') or not group:return False
    if span['size']<max(s['size'] for s in group)*.85:return False
    prior=''.join(source_text(s) for s in group)
    return all(prior.count(a)==prior.count(b) for a,b in [('(',')'),('[',']'),('{','}')])


def mark_runs(spans):
    """Add native dollar math to recoverable mathematical runs in rich text."""
    group=[];converted=0
    prose=any(re.search(r'[\u3400-\u9fff]',source_text(s)) for s in spans)
    def flush():
        nonlocal group,converted
        value=to_latex(group)
        if value:
            group[0]['_html']='$'+value+'$';group[0]['_native_math']=value
            for s in group:s['_math_handled']=True
            for s in group[1:]:s['_html']=''
            converted+=1
        group=[]
    for span in sorted(spans,key=lambda s:s['bbox'][0]):
        text=source_text(span)
        chinese=re.search(r'[\u3400-\u9fff]',text) and not MATH_FONT.search(span.get('font',''))
        sentence_punctuation=is_separator(span,group) or prose and text.strip() in ('（','）')
        if chinese or sentence_punctuation:flush()
        else:group.append(span)
    flush()
    return converted
