"use client";

import { useEffect, useState } from "react";
import { ErrorNote, Field, StatusPill, TagInput, YesNo } from "@/components/ui";
import { api, json, Profile, ProfileState, ProfileVersion, Task } from "@/lib/api";

type ListKey =
  | "product_categories"
  | "key_products"
  | "materials"
  | "certifications"
  | "target_markets"
  | "target_buyer_types"
  | "incoterms"
  | "payment_terms"
  | "selling_points"
  | "languages";

const LISTS: [ListKey, string][] = [
  ["product_categories", "Product categories"],
  ["key_products", "Key products"],
  ["materials", "Materials"],
  ["certifications", "Certifications"],
  ["target_markets", "Target markets"],
  ["target_buyer_types", "Target buyers"],
  ["incoterms", "Incoterms"],
  ["payment_terms", "Payment terms"],
  ["selling_points", "Selling points"],
  ["languages", "Languages"],
];

const TEXTS: [keyof Profile, string][] = [
  ["company_name", "Company name"],
  ["country", "Country"],
  ["city", "City"],
  ["website", "Website"],
  ["business_type", "Business type"],
  ["employees", "Employees"],
  ["production_capacity", "Production capacity"],
  ["minimum_order", "Minimum order"],
  ["lead_time", "Lead time"],
];

export function ProfileReview({ businessId, onApproved }: { businessId: string; onApproved: () => void }) {
  const base = `/businesses/${businessId}`;
  const [state, setState] = useState<ProfileState | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [task, setTask] = useState<Task | null>(null);

  const load = async () => {
    const s = await api<ProfileState>(`${base}/profile`);
    setState(s);
    setTask(s.pending_task);
    if (s.draft) {
      setProfile(s.draft.profile);
      setDirty(false);
    }
  };

  useEffect(() => {
    load().catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [businessId]);

  useEffect(() => {
    if (!task || task.status === "succeeded" || task.status === "needs_owner") return;
    const t = setInterval(async () => {
      const latest = await api<Task>(`${base}/tasks/${task.id}`);
      setTask(latest);
      if (latest.status === "succeeded") load();
    }, 2000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task?.id, task?.status]);

  const requestDraft = async () => {
    setError(null);
    setBusy(true);
    try {
      const t = await api<Task>(`${base}/profile/draft`, { method: "POST" });
      setTask(t);
      if (t.status === "succeeded") await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const save = async (): Promise<ProfileVersion | null> => {
    if (!state?.draft || !profile) return null;
    const v = await api<ProfileVersion>(`${base}/profile/${state.draft.id}`, {
      method: "PUT",
      body: json(profile),
    });
    setDirty(false);
    return v;
  };

  const approve = async () => {
    if (!state?.draft) return;
    setBusy(true);
    setError(null);
    try {
      if (dirty) await save();
      await api(`${base}/profile/${state.draft.id}/approve`, { method: "POST" });
      await load();
      onApproved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => {
    setProfile((p) => (p ? { ...p, [k]: v } : p));
    setDirty(true);
  };

  if (!state) return <ErrorNote message={error} />;

  const working = task && (task.status === "queued" || task.status === "running");
  const draft = state.draft;
  const notesFor = (field: string) => draft?.notes.filter((n) => n.field === field || n.field.startsWith(`${field}.`)) ?? [];

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm">
          {state.approved ? (
            <>
              Approved profile: version {state.approved.version}. <StatusPill status="approved" />
            </>
          ) : (
            "No approved profile yet. Agents only use a profile after you approve it."
          )}
          {!state.model_enabled && (
            <p className="mt-1 text-xs text-warn">
              The AI model is not configured, so the draft is built from your answers only.
            </p>
          )}
        </div>
        <button className="btn-quiet" disabled={busy || !!working} onClick={requestDraft}>
          {working ? "Drafting…" : draft ? "Redraft from my answers and files" : "Draft my profile"}
        </button>
      </div>
      {task?.status === "needs_owner" && (
        <ErrorNote message={`Drafting failed twice: ${task.error}. Try again, or fill the profile in by hand.`} />
      )}
      <ErrorNote message={error} />

      {draft && profile && (
        <div className="card space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-medium">
              Draft version {draft.version}{" "}
              <span className="text-sm font-normal text-muted">
                ({draft.source === "ai" ? "drafted by AI from your answers and documents" : "built from your answers"})
              </span>
            </h3>
            {dirty && <span className="text-xs text-warn">Unsaved changes</span>}
          </div>

          {draft.notes.length > 0 && (
            <div className="rounded-md border border-warn/30 bg-warn-soft p-3 text-sm">
              <div className="font-medium text-warn">{draft.notes.length} things to check</div>
              <ul className="mt-1 list-disc pl-5 text-ink">
                {draft.notes.map((n, i) => (
                  <li key={i}>
                    <span className="font-medium">{n.field.replaceAll("_", " ")}</span> ({n.kind}): {n.note}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <Field label="Summary" hint="What a foreign buyer reads first. Plain facts, two or three sentences.">
            <textarea
              className="input min-h-24"
              value={profile.summary ?? ""}
              onChange={(e) => set("summary", e.target.value)}
            />
          </Field>

          <div className="grid gap-4 sm:grid-cols-3">
            {TEXTS.map(([k, label]) => (
              <Field key={k} label={label} hint={notesFor(k)[0]?.note}>
                <input
                  className={`input ${notesFor(k).length ? "border-warn" : ""}`}
                  value={(profile[k] as string | null) ?? ""}
                  onChange={(e) => set(k, e.target.value as never)}
                />
              </Field>
            ))}
            <Field label="Year founded">
              <input
                className="input"
                type="number"
                value={profile.year_founded ?? ""}
                onChange={(e) => set("year_founded", e.target.value ? Number(e.target.value) : null)}
              />
            </Field>
            <Field label="Private label / OEM">
              <YesNo value={profile.private_label ?? undefined} onChange={(v) => set("private_label", v ?? null)} />
            </Field>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {LISTS.map(([k, label]) => (
              <Field key={k} label={label} hint={notesFor(k)[0]?.note}>
                <TagInput value={profile[k]} onChange={(v) => set(k, v)} />
              </Field>
            ))}
            <Field label="Already exporting to">
              <TagInput
                value={profile.export_experience.markets}
                onChange={(v) => set("export_experience", { ...profile.export_experience, markets: v })}
              />
            </Field>
          </div>

          <div className="grid gap-4 sm:grid-cols-4">
            {(["name", "role", "email", "phone"] as const).map((k) => (
              <Field key={k} label={`Contact ${k}`}>
                <input
                  className="input"
                  value={profile.contact[k] ?? ""}
                  onChange={(e) => set("contact", { ...profile.contact, [k]: e.target.value })}
                />
              </Field>
            ))}
          </div>

          <div className="flex flex-wrap gap-3 border-t border-line pt-4">
            <button
              className="btn-quiet"
              disabled={!dirty || busy}
              onClick={() => save().catch((e) => setError(e.message))}
            >
              Save draft
            </button>
            <button className="btn" disabled={busy} onClick={approve}>
              Approve profile
            </button>
            <p className="self-center text-xs text-muted">
              Approving makes this the version every agent reads. You can redraft and approve a new version later.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
