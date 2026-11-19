from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ONBOARDING_STEPS = ["company", "products", "markets", "documents", "catalogue", "review", "done"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OnboardingAnswers(BaseModel):
    """The guided form. Everything is optional so the owner can save as they go."""

    model_config = ConfigDict(extra="forbid")

    # Company
    company_name: str | None = Field(None, max_length=200)
    country: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    website: str | None = Field(None, max_length=300)
    year_founded: int | None = Field(None, ge=1800, le=2100)
    employees: str | None = Field(None, max_length=40)
    business_type: str | None = Field(None, max_length=60)
    description: str | None = Field(None, max_length=2000)
    # Products and production
    product_categories: list[str] = Field(default_factory=list, max_length=50)
    materials: list[str] = Field(default_factory=list, max_length=50)
    certifications: list[str] = Field(default_factory=list, max_length=50)
    production_capacity: str | None = Field(None, max_length=300)
    minimum_order: str | None = Field(None, max_length=300)
    lead_time: str | None = Field(None, max_length=300)
    private_label: bool | None = None
    # Export
    currently_exports: bool | None = None
    export_markets: list[str] = Field(default_factory=list, max_length=100)
    target_markets: list[str] = Field(default_factory=list, max_length=50)
    target_buyer_types: list[str] = Field(default_factory=list, max_length=20)
    incoterms: list[str] = Field(default_factory=list, max_length=20)
    payment_terms: list[str] = Field(default_factory=list, max_length=20)
    default_currency: str | None = Field(None, min_length=3, max_length=3)
    languages: list[str] = Field(default_factory=list, max_length=20)
    # Contact
    contact_name: str | None = Field(None, max_length=200)
    contact_role: str | None = Field(None, max_length=100)
    contact_email: str | None = Field(None, max_length=320)
    contact_phone: str | None = Field(None, max_length=50)

    @field_validator("default_currency")
    @classmethod
    def upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class BusinessOut(ORM):
    id: UUID
    name: str
    onboarding: dict[str, Any]
    onboarding_step: str
    created_at: datetime


class BusinessSummary(ORM):
    id: UUID
    name: str
    onboarding_step: str
    role: str


class MeOut(BaseModel):
    id: UUID
    email: str
    businesses: list[BusinessSummary]


class OnboardingUpdate(BaseModel):
    answers: OnboardingAnswers
    step: str | None = None

    @field_validator("step")
    @classmethod
    def known_step(cls, v: str | None) -> str | None:
        if v is not None and v not in ONBOARDING_STEPS:
            raise ValueError(f"step must be one of {ONBOARDING_STEPS}")
        return v


class DocumentOut(ORM):
    id: UUID
    kind: str
    filename: str
    content_type: str
    size_bytes: int
    page_count: int | None
    has_text: bool = False
    created_at: datetime


class TaskOut(ORM):
    id: UUID
    kind: str
    agent: str
    status: str
    output: dict[str, Any] | None
    error: str | None
    attempts: int
    created_at: datetime
    finished_at: datetime | None


class ImportCreate(BaseModel):
    document_id: UUID


class ImportMappingUpdate(BaseModel):
    mapping: dict[str, str | None]
    default_currency: str | None = Field(None, min_length=3, max_length=3)


class ImportCommit(BaseModel):
    default_currency: str | None = Field(None, min_length=3, max_length=3)
    update_existing: bool = True


class ImportOut(BaseModel):
    id: UUID
    document_id: UUID
    method: str
    status: str
    columns: list[str]
    mapping: dict[str, str | None]
    total_rows: int
    importable_rows: int
    preview: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    created_count: int
    updated_count: int | None = None
    task: TaskOut | None = None


class ProductOut(ORM):
    id: UUID
    sku: str | None
    name: str
    description: str | None
    category: str | None
    material: str | None
    unit_price: Decimal | None
    currency: str | None
    unit: str | None
    moq: int | None
    hs_code: str | None
    attributes: dict[str, Any]


class ProductPage(BaseModel):
    total: int
    items: list[ProductOut]


class ProfileVersionOut(ORM):
    id: UUID
    version: int
    status: str
    source: str
    profile: dict[str, Any]
    notes: list[dict[str, Any]]
    created_at: datetime
    approved_at: datetime | None


class ProfileState(BaseModel):
    draft: ProfileVersionOut | None
    approved: ProfileVersionOut | None
    pending_task: TaskOut | None
    model_enabled: bool


class AuditOut(ORM):
    id: int
    actor_type: str
    actor_id: str | None
    action: str
    target_type: str | None
    target_id: str | None
    detail: dict[str, Any]
    created_at: datetime
