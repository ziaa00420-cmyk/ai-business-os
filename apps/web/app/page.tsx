"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorNote, Shell } from "@/components/ui";
import { api, Business, getEmail, json, Me, setEmail } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [email, setEmailInput] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  const load = async () => {
    setError(null);
    try {
      setMe(await api<Me>("/me"));
    } catch (e) {
      setMe(null);
      if (getEmail()) setError((e as Error).message);
    } finally {
      setReady(true);
    }
  };

  useEffect(() => {
    if (getEmail()) load();
    else setReady(true);
  }, []);

  if (!ready) return null;

  if (!me) {
    return (
      <div className="mx-auto mt-24 max-w-sm px-4">
        <h1 className="text-xl font-semibold">AI Business OS</h1>
        <p className="mt-1 text-sm text-muted">Sign in to set up your export assistant.</p>
        <form
          className="card mt-6 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            setEmail(email.trim());
            load();
          }}
        >
          <label className="block">
            <span className="label">Work email</span>
            <input
              className="input"
              type="email"
              required
              value={email}
              onChange={(e) => setEmailInput(e.target.value)}
            />
            <span className="hint block">Local development sign-in. Production uses Clerk.</span>
          </label>
          <ErrorNote message={error} />
          <button className="btn w-full">Continue</button>
        </form>
      </div>
    );
  }

  return (
    <Shell>
      <h1 className="text-xl font-semibold">Your businesses</h1>
      <p className="mt-1 text-sm text-muted">Signed in as {me.email}</p>
      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        {me.businesses.map((b) => (
          <Link
            key={b.id}
            href={b.onboarding_step === "done" ? `/b/${b.id}` : `/b/${b.id}/onboarding`}
            className="card block hover:border-brand"
          >
            <div className="font-medium">{b.name}</div>
            <div className="mt-1 text-sm text-muted">
              {b.onboarding_step === "done" ? "Profile approved" : `Onboarding: ${b.onboarding_step}`}
            </div>
          </Link>
        ))}
      </div>
      <form
        className="card mt-6 max-w-md space-y-3"
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          try {
            const b = await api<Business>("/businesses", { method: "POST", body: json({ name }) });
            router.push(`/b/${b.id}/onboarding`);
          } catch (err) {
            setError((err as Error).message);
          }
        }}
      >
        <h2 className="font-medium">Add a business</h2>
        <input
          className="input"
          placeholder="Company name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <ErrorNote message={error} />
        <button className="btn">Start onboarding</button>
      </form>
    </Shell>
  );
}
