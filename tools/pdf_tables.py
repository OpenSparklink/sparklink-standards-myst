"""Drawn table grids, plus explicit source-reviewed grids without dividers."""
import json
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]

@lru_cache(maxsize=1)
def reviews():
    return json.loads((ROOT/'metadata/reviewed-tables.json').read_text())['tables']

def find_tables(page,code):
    tables=list(page.find_tables(strategy='lines_strict',use_layout=False).tables)
    for item in reviews():
        if item['code']!=code or item['page']!=page.number+1:continue
        if any(max(abs(a-b) for a,b in zip(t.bbox,item['bbox']))<1 for t in tables):
            raise ValueError('Reviewed grid duplicates a drawn table: '+item['id'])
        tables.append(SimpleNamespace(bbox=tuple(item['bbox']),cells=[tuple(c) for c in item['cells']],row_count=item['rows'],col_count=item['columns'],geometry_review=item['id']))
    return sorted(tables,key=lambda t:(t.bbox[1],t.bbox[0]))
