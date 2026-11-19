# AI Business OS

An AI export assistant for manufacturers. Version 1 takes a manufacturer from a product catalogue to a verified sales pipeline, with the owner approving every external action.

This repository holds **stage 1 (Foundation)** of the build plan: accounts, a tenant-safe database, business onboarding, catalogue import, AI profile drafting, the task table that the Central AI Manager will grow from, and per-call model tracing.

Stage 1 gate: *a design partner's catalogue becomes an approved business profile in under one hour.*

## What works

| Area | What it does |
| --- | --- |
| Onboarding | A six-step wizard: company, products, export markets, documents, catalogue, review. Answers save at every step. |
| Documents | Upload catalogue PDFs, certificates, photos (25 MB cap, type allow-list). Text is extracted from PDFs for the profile drafter. |
| Catalogue import | **Spreadsheets** (CSV, Excel): finds the header row, guesses the column mapping, the owner corrects it, previews every row with problems flagged (bad prices, duplicate SKUs, missing names), then imports. Re-importing updates products by SKU. **PDF catalogues**: the AI extracts product rows, which go through the same preview before anything is saved. |
| Profile drafting | Turns the owner's answers, the imported catalogue and uploaded documents into a structured profile, with notes on what is missing, inferred or conflicting. Without an API key it builds the draft from the owner's answers. |
| Approval | The owner edits and approves the draft. Only one approved version exists at a time; later agents read only that. |
| Tasks | AI work runs as rows in a `tasks` table, retried once on failure and then handed to the owner (`needs_owner`). |
| Tracing | Every model call is stored in `model_calls` with model, tokens, latency and stop reason. |
| Audit log | Append-only record of every action (the API role cannot update or delete it). |
| Tenant isolation | Every business table carries `business_id`, and Postgres row-level security blocks reads and writes across businesses even if application code forgets a filter. Tested in `tests/test_tenant_isolation.py`. |

## Layout

```
apps/web          Next.js 15 (App Router, TypeScript, Tailwind)
services/api      FastAPI, SQLAlchemy, Alembic, Anthropic SDK
  app/routers     HTTP endpoints
  app/services    catalogue parsing, profile drafter, task runner, model gateway, storage
  migrations      schema and RLS policies
  tests           pytest against a real Postgres
infra/postgres    role setup for local Postgres
```

## Run it locally

With Docker:

```bash
cp .env.example .env          # add ANTHROPIC_API_KEY to enable AI drafting and PDF import
docker compose up --build
open http://localhost:3000
```

Without Docker (Postgres 16 running locally, `uv` and Node 22 installed):

```bash
# once: roles and databases
psql -U postgres -c "create role aibos login password 'aibos' createdb"
psql -U postgres -c "create database aibos owner aibos"
psql -U postgres -c "create database aibos_test owner aibos"
psql -U postgres -c "create role aibos_app login password 'aibos_app' nosuperuser nobypassrls"

cd services/api
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload        # http://localhost:8000/docs

cd apps/web
npm install
npm run dev                                 # http://localhost:3000
```

Tests: `cd services/api && uv run pytest`.

## Database roles

The API connects as `aibos_app`, which is neither the table owner nor a superuser, so every RLS policy applies to it. Migrations run as `aibos`. Never point `DATABASE_URL` at a superuser: Postgres superusers bypass row-level security.

Each request sets `app.user_id` and `app.business_id` for its transaction (`app/db.py`); the policies in `migrations/versions/0001_stage1_foundation.py` read them.

## Sign-in

`AUTH_MODE=dev` (the default) trusts an `X-User-Email` header so the stack runs without an identity provider. **Do not deploy it.** `AUTH_MODE=clerk` verifies Clerk session tokens against your Clerk JWKS URL. The Clerk sign-in UI on the web app is not wired yet (see below).

## AI model

All model calls go through `app/services/model_gateway.py` using structured outputs validated by Pydantic. The default model is `claude-sonnet-5-5`, per the plan's tiering for agent work; set `AGENT_MODEL` to change it. Document text is treated as untrusted data: the drafter and the PDF extractor have no tools and can only return structured fields.

## Not in stage 1 yet

- Clerk sign-in screens in the web app (the API side is done).
- S3 storage (local disk behind the `Storage` interface for now).
- Procrastinate worker processes. Tasks run in-process after the request; the handler signature is what a worker will call.
- Embeddings and `document_chunks` with pgvector (needed for stage 2 research).
- Langfuse and Sentry. Model calls are already recorded in `model_calls`.
- Scanned (image-only) PDFs. They are detected and the owner is asked for a spreadsheet instead.
