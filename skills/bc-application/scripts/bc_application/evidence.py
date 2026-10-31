"""Private temporary PDF page previews for explicit manual evidence review."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

from .profile import ProfileError


def render_preview(profile: dict, source_id: str, *, page: int, output: Path, profile_path: Path) -> dict:
    source=profile["sources"].get(source_id)
    if not source or "path" not in source or type(page) is not int or not 1<=page<=source.get("page_count",0):
        raise ProfileError("registered_document_page_required")
    if output.is_symlink():
        raise ProfileError("preview_output_link_not_allowed")
    output=output.resolve()
    private=profile_path.resolve().parent
    skill=Path(__file__).resolve().parents[2]
    if output.parent!=private or output.suffix.lower()!='.png' or private.is_relative_to(skill):
        raise ProfileError("preview_requires_same_private_directory_and_png")
    if output.exists():
        raise ProfileError("preview_output_already_exists")
    try:
        data=Path(source["path"]).read_bytes()
    except OSError as exc:
        raise ProfileError("evidence_document_unavailable") from exc
    if hashlib.sha256(data).hexdigest()!=source["sha256"]:
        raise ProfileError("evidence_document_changed")
    document=document_page=bitmap=None
    created=False
    try:
        import pypdfium2 as pdfium
        document=pdfium.PdfDocument(data)
        document_page=document[page-1]
        width,height=document_page.get_size()
        if not all(math.isfinite(v) and v>0 for v in (width,height)) or width*height*4>20_000_000:
            raise ProfileError("evidence_preview_pixel_limit")
        bitmap=document_page.render(scale=2)
        with output.open('xb') as stream:
            created=True
            bitmap.to_pil().save(stream,format='PNG')
        return {"schema":"document-review-preview/1","source_id":source_id,"page":page,
            "document_sha256":source["sha256"],"width_points":width,"height_points":height,
            "coordinate_system":"pdf_points_top_origin","image_scale":2,"png":str(output),
            "temporary":True,"manual_review_required":True,"text_extraction_performed":False}
    except ProfileError:
        raise
    except Exception as exc:
        if created:
            output.unlink(missing_ok=True)
        raise ProfileError("evidence_preview_failed") from exc
    finally:
        for resource in (bitmap,document_page,document):
            if resource is not None:
                resource.close()
