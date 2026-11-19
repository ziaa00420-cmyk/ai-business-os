from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select

from app.auth import BusinessContext, business_context, require_owner
from app.db import scoped_session
from app.models import Business, CatalogueImport, Document, Product, Task
from app.schemas import (
    ImportCommit,
    ImportCreate,
    ImportMappingUpdate,
    ImportOut,
    ProductOut,
    ProductPage,
    TaskOut,
)
from app.services import audit, catalogue
from app.services.model_gateway import model_available
from app.services.storage import get_storage
from app.services.tasks import create_task, run_task

router = APIRouter(tags=["catalogue"])

PREVIEW_ROWS = 50
SPREADSHEET_SUFFIXES = (".csv", ".tsv", ".txt", ".xlsx", ".xlsm")


def _default_currency(session, business_id: UUID, override: str | None) -> str | None:
    if override:
        return override.upper()
    business = session.get(Business, business_id)
    return (business.onboarding or {}).get("default_currency") if business else None


def _to_out(session, imp: CatalogueImport, default_currency: str | None) -> ImportOut:
    products, errors = catalogue.apply_mapping(imp.rows, imp.mapping, default_currency)
    task = session.get(Task, imp.task_id) if imp.task_id else None
    return ImportOut(
        id=imp.id,
        document_id=imp.document_id,
        method=imp.method,
        status=imp.status,
        columns=imp.columns,
        mapping=imp.mapping,
        total_rows=len(products),
        importable_rows=sum(1 for p in products if not p["_skip"]),
        preview=products[:PREVIEW_ROWS],
        errors=(imp.errors if imp.status in ("failed", "committed") and imp.errors else errors)[
            :200
        ],
        created_count=imp.created_count,
        task=TaskOut.model_validate(task) if task else None,
    )


def _get_import(session, import_id: UUID) -> CatalogueImport:
    imp = session.get(CatalogueImport, import_id)
    if imp is None:
        raise HTTPException(404, "Import not found")
    return imp


@router.post(
    "/businesses/{business_id}/catalogue-imports", response_model=ImportOut, status_code=201
)
def start_import(
    body: ImportCreate,
    background: BackgroundTasks,
    ctx: BusinessContext = Depends(require_owner),
):
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        doc = session.get(Document, body.document_id)
        if doc is None:
            raise HTTPException(404, "Document not found")
        name = doc.filename.lower()
        if name.endswith(SPREADSHEET_SUFFIXES):
            try:
                sheet = catalogue.parse_spreadsheet(
                    get_storage().get(doc.storage_key), doc.filename
                )
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            imp = CatalogueImport(
                business_id=ctx.business_id,
                document_id=doc.id,
                method="spreadsheet",
                status="mapping",
                columns=sheet.columns,
                rows=sheet.rows,
                mapping=catalogue.guess_mapping(sheet.columns),
            )
            session.add(imp)
            session.flush()
            task_id = None
        elif name.endswith(".pdf"):
            if not model_available():
                raise HTTPException(
                    409,
                    "Reading products from a PDF needs the AI model, which is not configured. "
                    "Upload the catalogue as a spreadsheet (CSV or Excel) instead.",
                )
            if not doc.extracted_text:
                raise HTTPException(
                    422, "No text could be read from this PDF (it may be scanned images)."
                )
            imp = CatalogueImport(
                business_id=ctx.business_id,
                document_id=doc.id,
                method="ai_pdf",
                status="extracting",
            )
            session.add(imp)
            session.flush()
            task = create_task(
                session,
                ctx.business_id,
                "catalogue.extract_pdf",
                "catalogue",
                {"import_id": str(imp.id)},
                ctx.user.id,
            )
            imp.task_id = task.id
            task_id = task.id
        else:
            raise HTTPException(422, "Catalogue import accepts CSV, Excel or PDF files")
        audit.record(
            session,
            ctx.business_id,
            "catalogue.import_started",
            actor_id=ctx.user.id,
            target_type="catalogue_import",
            target_id=imp.id,
            detail={"method": imp.method, "document": doc.filename},
        )
        out = _to_out(session, imp, _default_currency(session, ctx.business_id, None))
    if task_id:
        background.add_task(run_task, task_id, ctx.business_id, ctx.user.id)
    return out


@router.get("/businesses/{business_id}/catalogue-imports/{import_id}", response_model=ImportOut)
def get_import(
    import_id: UUID,
    default_currency: str | None = None,
    ctx: BusinessContext = Depends(business_context),
):
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        imp = _get_import(session, import_id)
        return _to_out(session, imp, _default_currency(session, ctx.business_id, default_currency))


@router.put(
    "/businesses/{business_id}/catalogue-imports/{import_id}/mapping", response_model=ImportOut
)
def update_mapping(
    import_id: UUID, body: ImportMappingUpdate, ctx: BusinessContext = Depends(require_owner)
):
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        imp = _get_import(session, import_id)
        if imp.status != "mapping":
            raise HTTPException(409, f"Import is {imp.status}, not open for mapping")
        unknown_fields = set(body.mapping) - set(catalogue.PRODUCT_FIELDS)
        unknown_cols = {c for c in body.mapping.values() if c} - set(imp.columns)
        if unknown_fields or unknown_cols:
            raise HTTPException(
                422, f"Unknown fields {sorted(unknown_fields)} or columns {sorted(unknown_cols)}"
            )
        cols = [c for c in body.mapping.values() if c]
        if len(cols) != len(set(cols)):
            raise HTTPException(422, "Each column can map to one field only")
        if not body.mapping.get("name") and not body.mapping.get("sku"):
            raise HTTPException(422, "Map at least the product name or SKU")
        imp.mapping = {f: body.mapping.get(f) for f in catalogue.PRODUCT_FIELDS}
        return _to_out(
            session, imp, _default_currency(session, ctx.business_id, body.default_currency)
        )


@router.post(
    "/businesses/{business_id}/catalogue-imports/{import_id}/commit", response_model=ImportOut
)
def commit_import(
    import_id: UUID, body: ImportCommit, ctx: BusinessContext = Depends(require_owner)
):
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        imp = _get_import(session, import_id)
        if imp.status != "mapping":
            raise HTTPException(
                409, f"Import is {imp.status}; only a mapped import can be committed"
            )
        currency = _default_currency(session, ctx.business_id, body.default_currency)
        products, errors = catalogue.apply_mapping(imp.rows, imp.mapping, currency)
        existing = {
            p.sku: p for p in session.scalars(select(Product).where(Product.sku.is_not(None))).all()
        }
        created = updated = skipped = 0
        for row in products:
            if row["_skip"]:
                skipped += 1
                continue
            fields = {f: row[f] for f in catalogue.PRODUCT_FIELDS}
            fields["unit_price"] = Decimal(fields["unit_price"]) if fields["unit_price"] else None
            current = existing.get(fields["sku"]) if fields["sku"] else None
            if current is not None:
                if not body.update_existing:
                    skipped += 1
                    continue
                for k, v in fields.items():
                    if v is not None:
                        setattr(current, k, v)
                current.attributes = {**(current.attributes or {}), **row["attributes"]}
                current.import_id = imp.id
                updated += 1
            else:
                product = Product(
                    business_id=ctx.business_id,
                    attributes=row["attributes"],
                    source_document_id=imp.document_id,
                    import_id=imp.id,
                    **fields,
                )
                session.add(product)
                if fields["sku"]:
                    existing[fields["sku"]] = product
                created += 1
        imp.status = "committed"
        imp.created_count = created
        imp.errors = errors
        imp.committed_at = datetime.now(UTC)
        business = session.get(Business, ctx.business_id)
        if business and business.onboarding_step in (
            "company",
            "products",
            "markets",
            "documents",
            "catalogue",
        ):
            business.onboarding_step = "review"
        audit.record(
            session,
            ctx.business_id,
            "catalogue.import_committed",
            actor_id=ctx.user.id,
            target_type="catalogue_import",
            target_id=imp.id,
            detail={"created": created, "updated": updated, "skipped": skipped},
        )
        session.flush()
        out = _to_out(session, imp, currency)
        out.updated_count = updated
        return out


@router.get("/businesses/{business_id}/products", response_model=ProductPage)
def list_products(
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    ctx: BusinessContext = Depends(business_context),
):
    limit = max(1, min(limit, 200))
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        query = select(Product)
        if q:
            like = f"%{q}%"
            query = query.where(
                Product.name.ilike(like) | Product.sku.ilike(like) | Product.category.ilike(like)
            )
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = session.scalars(
            query.order_by(Product.category.nulls_last(), Product.name).limit(limit).offset(offset)
        ).all()
        return ProductPage(total=total, items=[ProductOut.model_validate(p) for p in items])


@router.delete("/businesses/{business_id}/products/{product_id}", status_code=204)
def delete_product(product_id: UUID, ctx: BusinessContext = Depends(require_owner)):
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        product = session.get(Product, product_id)
        if product is None:
            raise HTTPException(404, "Product not found")
        session.delete(product)
        audit.record(
            session,
            ctx.business_id,
            "product.deleted",
            actor_id=ctx.user.id,
            target_type="product",
            target_id=product_id,
            detail={"name": product.name},
        )
