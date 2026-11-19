"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorNote, Shell, StatusPill } from "@/components/ui";
import { api, Business, Product, ProfileState, Task } from "@/lib/api";

type Audit = { id: number; action: string; actor_type: string; created_at: string; detail: Record<string, unknown> };

export default function Dashboard() {
  const { id } = useParams<{ id: string }>();
  const [business, setBusiness] = useState<Business | null>(null);
  const [profile, setProfile] = useState<ProfileState | null>(null);
  const [products, setProducts] = useState<{ total: number; items: Product[] }>({ total: 0, items: [] });
  const [tasks, setTasks] = useState<Task[]>([]);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const base = `/businesses/${id}`;
        const [b, p, t, a] = await Promise.all([
          api<Business>(base),
          api<ProfileState>(`${base}/profile`),
          api<Task[]>(`${base}/tasks`),
          api<Audit[]>(`${base}/audit`),
        ]);
        setBusiness(b);
        setProfile(p);
        setTasks(t);
        setAudit(a);
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, [id]);

  useEffect(() => {
    const t = setTimeout(() => {
      api<{ total: number; items: Product[] }>(
        `/businesses/${id}/products?limit=100${q ? `&q=${encodeURIComponent(q)}` : ""}`,
      )
        .then(setProducts)
        .catch((e) => setError(e.message));
    }, 200);
    return () => clearTimeout(t);
  }, [id, q]);

  if (!business) return <Shell>{error && <ErrorNote message={error} />}</Shell>;
  const approved = profile?.approved?.profile;

  return (
    <Shell businessName={business.name} businessId={id}>
      <ErrorNote message={error} />
      {!approved && (
        <div className="card mb-6 flex items-center justify-between">
          <span className="text-sm">Finish onboarding and approve your profile so the agents can start.</span>
          <Link href={`/b/${id}/onboarding`} className="btn">
            Continue onboarding
          </Link>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="card lg:col-span-2">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Business profile</h2>
            {profile?.approved && (
              <span className="text-xs text-muted">
                Version {profile.approved.version} <StatusPill status="approved" />
              </span>
            )}
          </div>
          {approved ? (
            <div className="mt-3 space-y-3 text-sm">
              <p>{approved.summary}</p>
              <dl className="grid grid-cols-[10rem_1fr] gap-x-4 gap-y-1.5">
                {(
                  [
                    ["Location", [approved.city, approved.country].filter(Boolean).join(", ")],
                    ["Categories", approved.product_categories.join(", ")],
                    ["Certifications", approved.certifications.join(", ")],
                    ["Capacity", approved.production_capacity],
                    ["Minimum order", approved.minimum_order],
                    ["Lead time", approved.lead_time],
                    ["Target markets", approved.target_markets.join(", ")],
                    ["Target buyers", approved.target_buyer_types.join(", ")],
                    ["Contact", [approved.contact.name, approved.contact.email].filter(Boolean).join(" · ")],
                  ] as [string, string | null | undefined][]
                ).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-muted">{k}</dt>
                    <dd>{v || <span className="text-warn">not set</span>}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : (
            <p className="mt-3 text-sm text-muted">No approved profile yet.</p>
          )}
        </section>

        <section className="card">
          <h2 className="font-semibold">Recent work</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {tasks.slice(0, 6).map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-2">
                <span>{t.kind === "profile.draft" ? "Draft profile" : "Read PDF catalogue"}</span>
                <StatusPill status={t.status} />
              </li>
            ))}
            {tasks.length === 0 && <li className="text-muted">Nothing yet.</li>}
          </ul>
          <h3 className="mt-6 text-sm font-semibold">Activity</h3>
          <ul className="mt-2 space-y-1 text-xs text-muted">
            {audit.slice(0, 10).map((a) => (
              <li key={a.id}>
                {new Date(a.created_at).toLocaleString()} · {a.action}
              </li>
            ))}
          </ul>
        </section>

        <section className="card p-0 lg:col-span-3">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
            <h2 className="font-semibold">Products ({products.total})</h2>
            <input
              className="input w-64"
              placeholder="Search name, SKU or category"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <div className="overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-canvas text-xs text-muted">
                <tr>
                  {["SKU", "Name", "Category", "Material", "Price", "MOQ", "HS code"].map((h) => (
                    <th key={h} className="px-4 py-2">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {products.items.map((p) => (
                  <tr key={p.id} className="border-t border-line">
                    <td className="px-4 py-2 text-muted">{p.sku}</td>
                    <td className="px-4 py-2">{p.name}</td>
                    <td className="px-4 py-2">{p.category}</td>
                    <td className="px-4 py-2">{p.material}</td>
                    <td className="px-4 py-2 whitespace-nowrap">
                      {p.unit_price != null ? `${Number(p.unit_price).toFixed(2)} ${p.currency ?? ""}` : ""}
                    </td>
                    <td className="px-4 py-2">{p.moq}</td>
                    <td className="px-4 py-2">{p.hs_code}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {products.total === 0 && (
              <p className="px-5 py-4 text-sm text-muted">
                No products yet. Import your price list in the onboarding Catalogue step.
              </p>
            )}
          </div>
        </section>
      </div>
    </Shell>
  );
}
