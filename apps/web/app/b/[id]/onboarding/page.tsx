"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CatalogueImport } from "@/components/CatalogueImport";
import { ProfileReview } from "@/components/ProfileReview";
import { ErrorNote, Field, Shell, TagInput, YesNo } from "@/components/ui";
import { Answers, api, Business, Doc, json } from "@/lib/api";

const STEPS = [
  { key: "company", title: "Company" },
  { key: "products", title: "Products" },
  { key: "markets", title: "Export markets" },
  { key: "documents", title: "Documents" },
  { key: "catalogue", title: "Catalogue" },
  { key: "review", title: "Review profile" },
] as const;
type StepKey = (typeof STEPS)[number]["key"];

const BUYER_TYPES = ["Importers", "Wholesalers", "Distributors", "Retail chains", "Online retailers"];
const INCOTERMS = ["EXW", "FOB", "CIF", "DAP", "DDP"];
const PAYMENT = ["T/T 30% advance", "L/C at sight", "Open account 30 days"];
const DOC_KINDS = [
  ["catalogue", "Catalogue or brochure"],
  ["certificate", "Certificate"],
  ["photo", "Product photo"],
  ["other", "Other"],
] as const;

export default function Onboarding() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [business, setBusiness] = useState<Business | null>(null);
  const [answers, setAnswers] = useState<Answers>({});
  const [step, setStep] = useState<StepKey>("company");
  const [docs, setDocs] = useState<Doc[]>([]);
  const [docKind, setDocKind] = useState<string>("catalogue");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const b = await api<Business>(`/businesses/${id}`);
        setBusiness(b);
        setAnswers(b.onboarding);
        const known = STEPS.find((s) => s.key === b.onboarding_step);
        setStep(known ? known.key : b.onboarding_step === "done" ? "review" : "company");
        setDocs(await api<Doc[]>(`/businesses/${id}/documents`));
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, [id]);

  const set = <K extends keyof Answers>(k: K, v: Answers[K]) => setAnswers((a) => ({ ...a, [k]: v }));
  const text = (k: keyof Answers) => ({
    value: (answers[k] as string | number | undefined) ?? "",
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      set(k, (e.target.value || undefined) as never),
  });
  const list = (k: keyof Answers) => ({
    value: (answers[k] as string[] | undefined) ?? [],
    onChange: (v: string[]) => set(k, v as never),
  });

  const save = async (next?: StepKey) => {
    setSaving(true);
    setError(null);
    try {
      const clean = Object.fromEntries(Object.entries(answers).filter(([, v]) => v !== "" && v !== undefined));
      const b = await api<Business>(`/businesses/${id}/onboarding`, {
        method: "PUT",
        body: json({ answers: clean, step: next ?? step }),
      });
      setBusiness(b);
      if (next) setStep(next);
      window.scrollTo({ top: 0 });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const uploadDoc = async (file: File) => {
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("kind", docKind);
    try {
      const d = await api<Doc>(`/businesses/${id}/documents`, { method: "POST", body: form });
      setDocs((ds) => [d, ...ds]);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const idx = STEPS.findIndex((s) => s.key === step);
  const next = STEPS[idx + 1]?.key;
  const prev = STEPS[idx - 1]?.key;

  if (!business) return <Shell>{error ? <ErrorNote message={error} /> : null}</Shell>;

  return (
    <Shell businessName={business.name} businessId={id}>
      <div className="grid gap-8 lg:grid-cols-[200px_1fr]">
        <ol className="space-y-1 text-sm">
          {STEPS.map((s, i) => (
            <li key={s.key}>
              <button
                onClick={() => (s.key === step ? null : save(s.key))}
                className={`w-full rounded-md px-3 py-2 text-left ${
                  s.key === step ? "bg-brand-soft font-medium" : "hover:bg-panel"
                }`}
              >
                <span className="mr-2 text-muted">{i + 1}</span>
                {s.title}
              </button>
            </li>
          ))}
        </ol>

        <section className="min-w-0 space-y-5">
          <h1 className="text-xl font-semibold">{STEPS[idx].title}</h1>
          <ErrorNote message={error} />

          {step === "company" && (
            <div className="card grid gap-4 sm:grid-cols-2">
              <Field label="Company name">
                <input className="input" {...text("company_name")} />
              </Field>
              <Field label="Website">
                <input className="input" placeholder="https://" {...text("website")} />
              </Field>
              <Field label="Country">
                <input className="input" {...text("country")} />
              </Field>
              <Field label="City">
                <input className="input" {...text("city")} />
              </Field>
              <Field label="Year founded">
                <input
                  className="input"
                  type="number"
                  value={answers.year_founded ?? ""}
                  onChange={(e) => set("year_founded", e.target.value ? Number(e.target.value) : undefined)}
                />
              </Field>
              <Field label="Employees">
                <select className="input" {...text("employees")}>
                  <option value="">Choose</option>
                  {["1-10", "11-50", "51-200", "201-500", "500+"].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </Field>
              <Field label="Business type">
                <select className="input" {...text("business_type")}>
                  <option value="">Choose</option>
                  <option value="manufacturer">Manufacturer</option>
                  <option value="manufacturer and exporter">Manufacturer and exporter</option>
                  <option value="trading company">Trading company</option>
                </select>
              </Field>
              <div className="sm:col-span-2">
                <Field label="What does your company make?" hint="A few plain sentences. The AI uses this as a starting point.">
                  <textarea className="input min-h-24" {...text("description")} />
                </Field>
              </div>
            </div>
          )}

          {step === "products" && (
            <div className="card grid gap-4 sm:grid-cols-2">
              <Field label="Product categories" hint="Press Enter after each one.">
                <TagInput {...list("product_categories")} placeholder="e.g. Cookware" />
              </Field>
              <Field label="Main materials">
                <TagInput {...list("materials")} placeholder="e.g. Cast iron" />
              </Field>
              <Field label="Certifications" hint="Only ones you hold now, such as ISO 9001, BSCI, OEKO-TEX.">
                <TagInput {...list("certifications")} />
              </Field>
              <Field label="Production capacity" hint="For example: 20,000 pieces per month.">
                <input className="input" {...text("production_capacity")} />
              </Field>
              <Field label="Minimum order">
                <input className="input" placeholder="e.g. 500 pieces per design" {...text("minimum_order")} />
              </Field>
              <Field label="Typical lead time">
                <input className="input" placeholder="e.g. 45 days after deposit" {...text("lead_time")} />
              </Field>
              <Field label="Do you make private label / OEM products?">
                <YesNo value={answers.private_label} onChange={(v) => set("private_label", v)} />
              </Field>
            </div>
          )}

          {step === "markets" && (
            <div className="card grid gap-4 sm:grid-cols-2">
              <Field label="Do you export today?">
                <YesNo value={answers.currently_exports} onChange={(v) => set("currently_exports", v)} />
              </Field>
              <Field label="Countries you already sell to">
                <TagInput {...list("export_markets")} />
              </Field>
              <Field label="Countries you want to reach" hint="Pick one or two to start. The first research run uses these.">
                <TagInput {...list("target_markets")} suggestions={["United Kingdom", "Germany", "Netherlands"]} />
              </Field>
              <Field label="Buyers you want">
                <TagInput {...list("target_buyer_types")} suggestions={BUYER_TYPES} />
              </Field>
              <Field label="Incoterms you offer">
                <TagInput {...list("incoterms")} suggestions={INCOTERMS} />
              </Field>
              <Field label="Payment terms you accept">
                <TagInput {...list("payment_terms")} suggestions={PAYMENT} />
              </Field>
              <Field label="Price list currency" hint="Used when a price has no currency symbol.">
                <select className="input" {...text("default_currency")}>
                  <option value="">Choose</option>
                  {["USD", "EUR", "GBP", "PKR", "INR", "CNY", "TRY"].map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </Field>
              <Field label="Languages your team handles">
                <TagInput {...list("languages")} suggestions={["English"]} />
              </Field>
              <div className="grid gap-4 sm:col-span-2 sm:grid-cols-4">
                <Field label="Export contact name">
                  <input className="input" {...text("contact_name")} />
                </Field>
                <Field label="Role">
                  <input className="input" {...text("contact_role")} />
                </Field>
                <Field label="Email">
                  <input className="input" type="email" {...text("contact_email")} />
                </Field>
                <Field label="Phone">
                  <input className="input" {...text("contact_phone")} />
                </Field>
              </div>
            </div>
          )}

          {step === "documents" && (
            <div className="space-y-4">
              <div className="card space-y-3">
                <p className="text-sm text-muted">
                  Upload your company brochure, catalogue PDF, certificates and product photos. The AI reads the text
                  in PDFs to fill gaps in your profile. Price lists go in the next step.
                </p>
                <div className="flex flex-wrap items-center gap-3">
                  <select className="input w-56" value={docKind} onChange={(e) => setDocKind(e.target.value)}>
                    {DOC_KINDS.map(([k, label]) => (
                      <option key={k} value={k}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <input
                    type="file"
                    accept=".pdf,.txt,.jpg,.jpeg,.png,.webp"
                    className="text-sm"
                    onChange={(e) => {
                      if (e.target.files?.[0]) uploadDoc(e.target.files[0]);
                      e.target.value = "";
                    }}
                  />
                </div>
              </div>
              {docs.length > 0 && (
                <ul className="card divide-y divide-line p-0 text-sm">
                  {docs.map((d) => (
                    <li key={d.id} className="flex items-center justify-between px-5 py-2.5">
                      <span>
                        {d.filename} <span className="text-muted">· {d.kind.replace("_", " ")}</span>
                      </span>
                      <span className="text-xs text-muted">
                        {d.page_count ? `${d.page_count} pages · ` : ""}
                        {d.filename.toLowerCase().endsWith(".pdf") && !d.has_text
                          ? "no readable text (scanned?)"
                          : `${Math.ceil(d.size_bytes / 1024)} KB`}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {step === "catalogue" && (
            <CatalogueImport
              businessId={id}
              defaultCurrency={answers.default_currency}
              onCommitted={() => undefined}
            />
          )}

          {step === "review" && <ProfileReview businessId={id} onApproved={() => router.push(`/b/${id}`)} />}

          {step !== "review" && (
            <div className="flex gap-3">
              {prev && (
                <button className="btn-quiet" disabled={saving} onClick={() => save(prev)}>
                  Back
                </button>
              )}
              <button className="btn" disabled={saving} onClick={() => save(next)}>
                {saving ? "Saving…" : step === "catalogue" ? "Continue to review" : "Save and continue"}
              </button>
            </div>
          )}
        </section>
      </div>
    </Shell>
  );
}
