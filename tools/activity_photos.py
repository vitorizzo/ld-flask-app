"""Normalize lot photos and keep them outside publicly served static assets."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError


def photo_root():
    return (Path(current_app.instance_path)/'activity_photos').resolve()


def photo_path(name):
    root=photo_root();path=(root/name).resolve()
    if not path.is_relative_to(root) or path.parent!=root: raise ValueError('Foto non valida.')
    return path


def store_photo(upload):
    raw=upload.read(8*1024*1024+1)
    if not raw or len(raw)>8*1024*1024: raise ValueError('Scegli una foto JPEG, PNG o WebP di massimo 8 MB.')
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in ('JPEG','PNG','WEBP') or image.width*image.height>20000000:
                raise ValueError('Formato o dimensioni della foto non validi.')
            image=ImageOps.exif_transpose(image);image.thumbnail((2048,2048))
            image=image.convert('RGB');output=BytesIO();image.save(output,format='JPEG',quality=85)
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as exc:
        raise ValueError('Il file non è una foto valida.') from exc
    name=uuid4().hex+'.jpg';path=photo_path(name);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(output.getvalue())
    return name
