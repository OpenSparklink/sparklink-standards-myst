"""Decode printed construction glyphs from legacy Symbol-encoded fonts.

These Unicode letters are the Adobe Symbol codes of bracket pieces, not
letters in the standard. Preserve pieces explicitly for source accounting.
"""
CONSTRUCTION={'æ':'⎛','ç':'⎜','è':'⎝','ö':'⎞','÷':'⎟','ø':'⎠',
              'é':'⎡','ê':'⎢','ë':'⎣','ù':'⎤','ú':'⎥','û':'⎦',
              'ì':'⎧','í':'⎨','î':'⎩','ï':'⎪'}


def decode(font,text):
    if font in ('SymbolMT','FZS_Extra_S92'):return text.translate(str.maketrans(CONSTRUCTION))
    return text
