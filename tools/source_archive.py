"""Find private PDF verification assets without including them in the site."""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def source_path(relative):
    path=ROOT/relative
    if path.is_file():return path
    archive=Path(os.environ.get('SPARKLINK_AUDIT_ARCHIVE',ROOT/'.local-archive'))
    path=archive/relative
    if path.is_file():return path
    raise FileNotFoundError(f'{relative}: regenerate from the source PDF or set SPARKLINK_AUDIT_ARCHIVE')
