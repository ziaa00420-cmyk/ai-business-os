from typing import Any

from sqlalchemy.orm import Session

from app.models import CatalogueImport, Document, Task
from app.services import catalogue
from app.services.model_gateway import structured_call
from app.services.tasks import FAILURE_HOOKS, handler


@handler("catalogue.extract_pdf")
def extract_pdf_products(session: Session, task: Task) -> dict[str, Any]:
    imp = session.get(CatalogueImport, task.input["import_id"])
    assert imp is not None
    doc = session.get(Document, imp.document_id)
    assert doc is not None
    if not doc.extracted_text:
        raise ValueError(
            "No text could be read from this PDF. It may be scanned images; "
            "upload a spreadsheet or a text-based PDF instead."
        )
    items: list[catalogue.ExtractedProduct] = []
    chunks = catalogue.chunk_text(doc.extracted_text)
    for n, chunk in enumerate(chunks, start=1):
        result = structured_call(
            session,
            business_id=task.business_id,
            task_id=task.id,
            purpose="catalogue.extract_pdf",
            system=catalogue.PDF_EXTRACT_SYSTEM,
            user_content=f"<catalogue part={n} of={len(chunks)}>\n{chunk}\n</catalogue>",
            output_type=catalogue.ExtractedProducts,
        )
        items.extend(result.products)
    rows = catalogue.extracted_to_rows(items)
    columns = list(catalogue.PRODUCT_FIELDS) + (["page"] if any("page" in r for r in rows) else [])
    imp.columns = columns
    imp.rows = rows
    imp.mapping = dict(catalogue.IDENTITY_MAPPING)
    imp.status = "mapping"
    return {"import_id": str(imp.id), "products_found": len(rows), "chunks": len(chunks)}


def _mark_import_failed(session: Session, task: Task) -> None:
    imp = session.get(CatalogueImport, task.input["import_id"])
    if imp is not None:
        imp.status = "failed"
        imp.errors = [{"row": None, "problems": [task.error or "extraction failed"]}]


FAILURE_HOOKS["catalogue.extract_pdf"] = _mark_import_failed
