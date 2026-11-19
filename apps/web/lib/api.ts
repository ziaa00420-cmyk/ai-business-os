// Thin client for the FastAPI service. In dev auth mode the signed-in email is
// sent as X-User-Email; with Clerk this becomes the session token instead.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const EMAIL_KEY = "aibos.devEmail";

export function getEmail(): string | null {
  try {
    return localStorage.getItem(EMAIL_KEY);
  } catch {
    return null;
  }
}

export function setEmail(email: string | null) {
  try {
    if (email) localStorage.setItem(EMAIL_KEY, email);
    else localStorage.removeItem(EMAIL_KEY);
  } catch {
    /* storage unavailable */
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function detailMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) =>
        [d.loc?.slice(1).join("."), d.msg].filter(Boolean).join(": "),
      )
      .join("; ");
  return "Something went wrong";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const email = getEmail();
  if (email) headers.set("X-User-Email", email);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const res = await fetch(`${API_URL}/api${path}`, { ...init, headers });
  if (!res.ok) {
    let message = res.statusText;
    try {
      message = detailMessage((await res.json()).detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const json = (body: unknown) => JSON.stringify(body);

// ---- Types mirroring app/schemas.py ----------------------------------------------

export type Answers = {
  company_name?: string;
  country?: string;
  city?: string;
  website?: string;
  year_founded?: number;
  employees?: string;
  business_type?: string;
  description?: string;
  product_categories?: string[];
  materials?: string[];
  certifications?: string[];
  production_capacity?: string;
  minimum_order?: string;
  lead_time?: string;
  private_label?: boolean;
  currently_exports?: boolean;
  export_markets?: string[];
  target_markets?: string[];
  target_buyer_types?: string[];
  incoterms?: string[];
  payment_terms?: string[];
  default_currency?: string;
  languages?: string[];
  contact_name?: string;
  contact_role?: string;
  contact_email?: string;
  contact_phone?: string;
};

export type Business = {
  id: string;
  name: string;
  onboarding: Answers;
  onboarding_step: string;
};

export type Me = {
  id: string;
  email: string;
  businesses: { id: string; name: string; onboarding_step: string; role: string }[];
};

export type Doc = {
  id: string;
  kind: string;
  filename: string;
  size_bytes: number;
  page_count: number | null;
  has_text: boolean;
  created_at: string;
};

export type Task = {
  id: string;
  kind: string;
  agent: string;
  status: "queued" | "running" | "succeeded" | "failed" | "needs_owner";
  output: Record<string, unknown> | null;
  error: string | null;
  attempts: number;
  created_at: string;
  finished_at: string | null;
};

export const PRODUCT_FIELDS = [
  "sku",
  "name",
  "description",
  "category",
  "material",
  "unit_price",
  "currency",
  "unit",
  "moq",
  "hs_code",
] as const;
export type ProductField = (typeof PRODUCT_FIELDS)[number];

export type PreviewRow = Record<ProductField, string | number | null> & {
  attributes: Record<string, unknown>;
  _row: number;
  _skip: boolean;
};

export type CatalogueImport = {
  id: string;
  document_id: string;
  method: "spreadsheet" | "ai_pdf";
  status: "extracting" | "mapping" | "committed" | "failed";
  columns: string[];
  mapping: Record<ProductField, string | null>;
  total_rows: number;
  importable_rows: number;
  preview: PreviewRow[];
  errors: { row: number | null; problems: string[] }[];
  created_count: number;
  updated_count: number | null;
  task: Task | null;
};

export type Product = Record<ProductField, string | number | null> & {
  id: string;
  name: string;
  attributes: Record<string, unknown>;
};

export type Profile = {
  company_name: string;
  country?: string | null;
  city?: string | null;
  website?: string | null;
  year_founded?: number | null;
  employees?: string | null;
  business_type?: string | null;
  summary?: string | null;
  product_categories: string[];
  key_products: string[];
  materials: string[];
  certifications: string[];
  production_capacity?: string | null;
  minimum_order?: string | null;
  lead_time?: string | null;
  private_label?: boolean | null;
  export_experience: { currently_exports?: boolean | null; markets: string[]; years_exporting?: number | null };
  target_markets: string[];
  target_buyer_types: string[];
  incoterms: string[];
  payment_terms: string[];
  selling_points: string[];
  languages: string[];
  contact: { name?: string | null; role?: string | null; email?: string | null; phone?: string | null };
};

export type ProfileVersion = {
  id: string;
  version: number;
  status: "draft" | "approved" | "superseded";
  source: "ai" | "fallback" | "owner";
  profile: Profile;
  notes: { field: string; note: string; kind: string }[];
  created_at: string;
  approved_at: string | null;
};

export type ProfileState = {
  draft: ProfileVersion | null;
  approved: ProfileVersion | null;
  pending_task: Task | null;
  model_enabled: boolean;
};
