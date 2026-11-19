"use client";

import Link from "next/link";
import { useState } from "react";
import { setEmail } from "@/lib/api";

export function Shell({
  children,
  businessName,
  businessId,
}: {
  children: React.ReactNode;
  businessName?: string;
  businessId?: string;
}) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-3">
            <Link href="/" className="font-semibold">
              AI Business OS
            </Link>
            {businessName && <span className="text-sm text-muted">/ {businessName}</span>}
          </div>
          <nav className="flex items-center gap-4 text-sm">
            {businessId && (
              <>
                <Link href={`/b/${businessId}`} className="hover:underline">
                  Dashboard
                </Link>
                <Link href={`/b/${businessId}/onboarding`} className="hover:underline">
                  Onboarding
                </Link>
              </>
            )}
            <button
              className="text-muted hover:underline"
              onClick={() => {
                setEmail(null);
                window.location.href = "/";
              }}
            >
              Sign out
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
    </div>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="hint block">{hint}</span>}
    </label>
  );
}

/** A comma-or-enter separated list input. */
export function TagInput({
  value,
  onChange,
  placeholder,
  suggestions = [],
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  suggestions?: string[];
}) {
  const [draft, setDraft] = useState("");
  const add = (raw: string) => {
    const items = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .filter((s) => !value.includes(s));
    if (items.length) onChange([...value, ...items]);
    setDraft("");
  };
  const unused = suggestions.filter((s) => !value.includes(s));
  return (
    <div>
      <div className="input flex min-h-10 flex-wrap items-center gap-1.5">
        {value.map((v) => (
          <span key={v} className="inline-flex items-center gap-1 rounded bg-brand-soft px-2 py-0.5 text-xs">
            {v}
            <button
              type="button"
              aria-label={`Remove ${v}`}
              className="text-muted hover:text-ink"
              onClick={() => onChange(value.filter((x) => x !== v))}
            >
              ×
            </button>
          </span>
        ))}
        <input
          className="min-w-32 flex-1 bg-transparent outline-none"
          value={draft}
          placeholder={value.length ? "" : placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              add(draft);
            } else if (e.key === "Backspace" && !draft && value.length) {
              onChange(value.slice(0, -1));
            }
          }}
          onBlur={() => draft && add(draft)}
        />
      </div>
      {unused.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {unused.map((s) => (
            <button
              key={s}
              type="button"
              className="rounded border border-line px-2 py-0.5 text-xs text-muted hover:bg-canvas"
              onClick={() => onChange([...value, s])}
            >
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function YesNo({
  value,
  onChange,
}: {
  value: boolean | undefined;
  onChange: (v: boolean | undefined) => void;
}) {
  return (
    <div className="flex gap-2">
      {[
        ["Yes", true],
        ["No", false],
      ].map(([label, v]) => (
        <button
          key={String(label)}
          type="button"
          onClick={() => onChange(value === v ? undefined : (v as boolean))}
          className={`rounded-md border px-3 py-1.5 text-sm ${value === v ? "border-brand bg-brand-soft" : "border-line bg-white"}`}
        >
          {label as string}
        </button>
      ))}
    </div>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-md border border-bad/30 bg-bad/5 px-3 py-2 text-sm text-bad">
      {message}
    </p>
  );
}

export function StatusPill({ status }: { status: string }) {
  const tone =
    status === "succeeded" || status === "approved" || status === "committed"
      ? "bg-good/10 text-good"
      : status === "needs_owner" || status === "failed"
        ? "bg-bad/10 text-bad"
        : "bg-warn-soft text-warn";
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${tone}`}>{status.replace("_", " ")}</span>;
}
