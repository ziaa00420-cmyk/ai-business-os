"use client";

import { useEffect, useRef, useState } from "react";
import { ErrorNote, StatusPill } from "@/components/ui";
import { api, CatalogueImport as Import, Doc, json, PRODUCT_FIELDS, ProductField } from "@/lib/api";

const FIELD_LABELS: Record<ProductField, string> = {
  sku: "SKU / item code",
  name: "Product name",
  description: "Description",
  category: "Category",
  material: "Material",
  unit_price: "Unit price",
  currency: "Currency",
  unit: "Unit",
  moq: "MOQ",
  hs_code: "HS code",
};

export function CatalogueImport({
  businessId,
  defaultCurrency,
  onCommitted,
}: {
  businessId: string;
  defaultCurrency?: string;
  onCommitted: (imp: Import) => void;
}) {
  const [imp, setImp] = useState<Import | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const base = `/businesses/${businessId}`;

  // Poll while the AI reads a PDF.
  useEffect(() => {
    if (imp?.status !== "extracting") return;
    const t = setInterval(async () => {
      try {
        setImp(await api<Import>(`${base}/catalogue-imports/${imp.id}`));
      } catch (e) {
        setError((e as Error).message);
      }
    }, 2000);
    return () => clearInterval(t);
  }, [imp?.id, imp?.status, base]);

  const start = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("kind", file.name.toLowerCase().endsWith(".pdf") ? "catalogue" : "price_list");
      const doc = await api<Doc>(`${base}/documents`, { method: "POST", body: form });
      setImp(
        await api<Import>(`${base}/catalogue-imports`, {
          method: "POST",
          body: json({ document_id: doc.id }),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const remap = async (field: ProductField, column: string | null) => {
    if (!imp) return;
    setError(null);
    // A column can only feed one field: clear it elsewhere.
    const mapping = Object.fromEntries(
      PRODUCT_FIELDS.map((f) => [f, f === field ? column : imp.mapping[f] === column ? null : imp.mapping[f]]),
    );
    try {
      setImp(
        await api<Import>(`${base}/catalogue-imports/${imp.id}/mapping`, {
          method: "PUT",
          body: json({ mapping }),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const commit = async () => {
    if (!imp) return;
    setBusy(true);
    setError(null);
    try {
      const done = await api<Import>(`${base}/catalogue-imports/${imp.id}/commit`, {
        method: "POST",
        body: json({ default_currency: defaultCurrency || null }),
      });
      setImp(done);
      onCommitted(done);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const problemsByRow = new Map(imp?.errors.map((e) => [e.row, e.problems]) ?? []);

  return (
    <div className="space-y-4">
      <div className="card">
        <p className="text-sm text-muted">
          Upload your price list or product catalogue. A spreadsheet (CSV or Excel) is the most accurate. A PDF
          catalogue is read by the AI, and you check every row before it is saved.
        </p>
        <div className="mt-3 flex items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.tsv,.xlsx,.xlsm,.pdf"
            disabled={busy}
            onChange={(e) => e.target.files?.[0] && start(e.target.files[0])}
            className="text-sm"
          />
          {busy && <span className="text-sm text-muted">Working…</span>}
        </div>
      </div>
      <ErrorNote message={error} />

      {imp?.status === "extracting" && (
        <div className="card text-sm">
          Reading products from the PDF. This usually takes under a minute.{" "}
          {imp.task && <StatusPill status={imp.task.status} />}
        </div>
      )}

      {imp?.status === "failed" && (
        <ErrorNote message={imp.task?.error ?? imp.errors[0]?.problems[0] ?? "Import failed"} />
      )}

      {imp && (imp.status === "mapping" || imp.status === "committed") && (
        <>
          {imp.method === "spreadsheet" && imp.status === "mapping" && (
            <div className="card">
              <h3 className="font-medium">Match your columns</h3>
              <p className="mt-1 text-sm text-muted">
                We guessed which column holds what. Fix anything that is wrong. Unmatched columns are kept as extra
                product details.
              </p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                {PRODUCT_FIELDS.map((f) => (
                  <label key={f} className="block">
                    <span className="label text-xs">{FIELD_LABELS[f]}</span>
                    <select
                      className="input"
                      value={imp.mapping[f] ?? ""}
                      onChange={(e) => remap(f, e.target.value || null)}
                    >
                      <option value="">Not in file</option>
                      {imp.columns.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="card overflow-hidden p-0">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
              <div className="text-sm">
                <strong>{imp.importable_rows}</strong> of {imp.total_rows} rows ready to import
                {imp.errors.length > 0 && (
                  <span className="text-warn"> · {imp.errors.length} rows need a look</span>
                )}
              </div>
              {imp.status === "mapping" ? (
                <button className="btn" disabled={busy || imp.importable_rows === 0} onClick={commit}>
                  Import {imp.importable_rows} products
                </button>
              ) : (
                <span className="text-sm text-good">
                  Imported: {imp.created_count} new
                  {imp.updated_count ? `, ${imp.updated_count} updated` : ""}
                </span>
              )}
            </div>
            <div className="max-h-[28rem] overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-canvas text-xs text-muted">
                  <tr>
                    <th className="px-3 py-2">Row</th>
                    {PRODUCT_FIELDS.map((f) => (
                      <th key={f} className="px-3 py-2 whitespace-nowrap">
                        {FIELD_LABELS[f]}
                      </th>
                    ))}
                    <th className="px-3 py-2">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {imp.preview.map((r) => (
                    <tr key={r._row} className={`border-t border-line ${r._skip ? "bg-bad/5 text-muted" : ""}`}>
                      <td className="px-3 py-2">{r._row}</td>
                      {PRODUCT_FIELDS.map((f) => (
                        <td key={f} className="max-w-56 truncate px-3 py-2" title={String(r[f] ?? "")}>
                          {r[f] ?? <span className="text-line">–</span>}
                        </td>
                      ))}
                      <td className="px-3 py-2 text-xs text-warn">
                        {r._skip && "Skipped. "}
                        {problemsByRow.get(r._row)?.join("; ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {imp.total_rows > imp.preview.length && (
              <p className="border-t border-line px-5 py-2 text-xs text-muted">
                Showing the first {imp.preview.length} rows.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
