from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select

from app.auth import BusinessContext, business_context, require_owner
from app.config import get_settings
from app.db import scoped_session
from app.models import Document
from app.schemas import DocumentOut
from app.services import audit
from app.services.catalogue import extract_pdf_text
from app.services.storage import get_storage

router = APIRouter(tags=["documents"])

ALLOWED = {
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
KINDS = {"catalogue", "price_list", "photo", "certificate", "other"}


def to_out(doc: Document) -> DocumentOut:
    out = DocumentOut.model_validate(doc)
    out.has_text = bool(doc.extracted_text)
    return out


@router.post("/businesses/{business_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    kind: str = Form("other"),
    ctx: BusinessContext = Depends(require_owner),
):
    if kind not in KINDS:
        raise HTTPException(422, f"kind must be one of {sorted(KINDS)}")
    filename = Path(file.filename or "upload").name[:300]
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(415, f"Unsupported file type {suffix or '(none)'}")
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File is larger than {get_settings().max_upload_mb} MB")
    if not data:
        raise HTTPException(422, "File is empty")

    extracted, pages = None, None
    if suffix == ".pdf":
        try:
            extracted, pages = extract_pdf_text(data)
        except Exception as exc:  # noqa: BLE001 - a broken PDF is a user error
            raise HTTPException(422, "Could not read this PDF") from exc
    elif suffix == ".txt":
        extracted = data.decode("utf-8", errors="replace")

    key = get_storage().put(ctx.business_id, filename, data)
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        doc = Document(
            business_id=ctx.business_id,
            kind=kind,
            filename=filename,
            content_type=ALLOWED[suffix],
            size_bytes=len(data),
            storage_key=key,
            extracted_text=extracted or None,
            page_count=pages,
            uploaded_by=ctx.user.id,
        )
        session.add(doc)
        session.flush()
        audit.record(
            session,
            ctx.business_id,
            "document.uploaded",
            actor_id=ctx.user.id,
            target_type="document",
            target_id=doc.id,
            detail={"filename": filename, "kind": kind, "bytes": len(data)},
        )
        session.refresh(doc)
        return to_out(doc)


@router.get("/businesses/{business_id}/documents", response_model=list[DocumentOut])
def list_documents(ctx: BusinessContext = Depends(business_context)):
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        docs = session.scalars(select(Document).order_by(Document.created_at.desc())).all()
        return [to_out(d) for d in docs]
