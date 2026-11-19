"""The structured business profile.

This is what later agents (research, discovery, sales) read as business
memory, and it doubles as the output schema for the profile drafter. Only an
owner-approved version is ever used for outreach.
"""

from pydantic import BaseModel, Field


class Contact(BaseModel):
    name: str | None = None
    role: str | None = None
    email: str | None = None
    phone: str | None = None


class ExportExperience(BaseModel):
    currently_exports: bool | None = None
    markets: list[str] = Field(default_factory=list, description="Countries already sold to")
    years_exporting: int | None = None


class BusinessProfile(BaseModel):
    company_name: str
    country: str | None = None
    city: str | None = None
    website: str | None = None
    year_founded: int | None = None
    employees: str | None = Field(None, description="Range such as '50-200'")
    business_type: str | None = Field(
        None, description="manufacturer, trading company, or manufacturer and exporter"
    )
    summary: str | None = Field(None, description="Two or three plain sentences, no marketing")
    product_categories: list[str] = Field(default_factory=list)
    key_products: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    production_capacity: str | None = None
    minimum_order: str | None = None
    lead_time: str | None = None
    private_label: bool | None = None
    export_experience: ExportExperience = Field(default_factory=ExportExperience)
    target_markets: list[str] = Field(default_factory=list)
    target_buyer_types: list[str] = Field(
        default_factory=list, description="importers, wholesalers, distributors, retailers"
    )
    incoterms: list[str] = Field(default_factory=list)
    payment_terms: list[str] = Field(default_factory=list)
    selling_points: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    contact: Contact = Field(default_factory=Contact)


class FieldNote(BaseModel):
    field: str
    note: str = Field(description="Why this needs the owner's attention")
    kind: str = Field(description="missing, inferred, or conflicting")


class ProfileDraft(BaseModel):
    profile: BusinessProfile
    notes: list[FieldNote] = Field(default_factory=list)
