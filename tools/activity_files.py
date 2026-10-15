"""Private activity attachments using the existing supplier upload validators."""
import hashlib
from pathlib import PurePath
from tools.supplier_card_files import TYPES, MAX_FILE, MAX_TOTAL, _validate_content
from models import ActivityAttachment


def prepare_files(uploads):
    if len(uploads)>10: raise ValueError('Massimo 10 allegati per caricamento.')
    files=[];total=0
    for upload in uploads:
        name=PurePath((upload.filename or '').replace('\\','/')).name
        extension=PurePath(name).suffix.lower()
        if not name or len(name)>200 or any(ord(c)<32 for c in name) or extension not in TYPES:
            raise ValueError('Sono ammessi PDF, Word, Excel e foto JPEG, PNG, WebP.')
        raw=upload.read(MAX_FILE+1);total+=len(raw)
        if not raw or len(raw)>MAX_FILE or total>MAX_TOTAL: raise ValueError('Massimo 10 MB per file e 50 MB totali.')
        _validate_content(raw,extension)
        files.append(dict(filename=name,mimetype=TYPES[extension],size=len(raw),content=raw))
    return files


def files_digest(files):
    if not files: return None
    digest=hashlib.sha256()
    for item in files:
        digest.update(item['filename'].encode());digest.update(b'\0');digest.update(hashlib.sha256(item['content']).digest())
    return digest.hexdigest()


def attach_files(row, files, purpose):
    retained=[item for item in row.attachments if item.cycle==row.cycle and item.purpose==purpose]
    if len(retained)+len(files)>10 or sum(item.size for item in retained)+sum(item['size'] for item in files)>MAX_TOTAL:
        raise ValueError('Massimo 10 allegati e 50 MB per fase dell’attività.')
    row.attachments.extend(ActivityAttachment(cycle=row.cycle or 1,purpose=purpose,**item) for item in files)
