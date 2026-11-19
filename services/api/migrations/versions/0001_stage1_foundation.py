"""Stage 1 foundation: accounts, business memory, catalogue import, tasks, audit, RLS.

Revision ID: 0001
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = "aibos_app"

TENANT_TABLES = [
    "documents",
    "tasks",
    "catalogue_imports",
    "products",
    "profile_versions",
    "model_calls",
]


def upgrade() -> None:
    op.execute(
        """
        create extension if not exists pgcrypto;

        -- Request context, set per transaction by the API (see app/db.py).
        create or replace function app_user_id() returns uuid
          language sql stable as
          $$ select nullif(current_setting('app.user_id', true), '')::uuid $$;

        create or replace function app_business_id() returns uuid
          language sql stable as
          $$ select nullif(current_setting('app.business_id', true), '')::uuid $$;

        create table users (
          id uuid primary key default gen_random_uuid(),
          email varchar(320) not null unique,
          external_id varchar(200) unique,
          name varchar(200),
          created_at timestamptz not null default now()
        );

        create table businesses (
          id uuid primary key default gen_random_uuid(),
          name varchar(200) not null,
          onboarding jsonb not null default '{}',
          onboarding_step varchar(40) not null default 'company',
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        );

        create table memberships (
          business_id uuid not null references businesses(id) on delete cascade,
          user_id uuid not null references users(id) on delete cascade,
          role varchar(20) not null default 'owner' check (role in ('owner', 'member')),
          created_at timestamptz not null default now(),
          primary key (business_id, user_id)
        );
        create index memberships_user_idx on memberships(user_id);

        -- True when the current user belongs to the current business.
        create or replace function app_is_member() returns boolean
          language sql stable as
          $$ select exists (
               select 1 from memberships m
               where m.business_id = app_business_id() and m.user_id = app_user_id()
             ) $$;

        create table documents (
          id uuid primary key default gen_random_uuid(),
          business_id uuid not null references businesses(id) on delete cascade,
          kind varchar(30) not null
            check (kind in ('catalogue', 'price_list', 'photo', 'certificate', 'other')),
          filename varchar(300) not null,
          content_type varchar(120) not null,
          size_bytes integer not null,
          storage_key varchar(500) not null,
          extracted_text text,
          page_count integer,
          uploaded_by uuid references users(id),
          created_at timestamptz not null default now()
        );
        create index documents_business_idx on documents(business_id);

        create table tasks (
          id uuid primary key default gen_random_uuid(),
          business_id uuid not null references businesses(id) on delete cascade,
          kind varchar(40) not null,
          agent varchar(40) not null,
          status varchar(20) not null default 'queued'
            check (status in ('queued', 'running', 'succeeded', 'failed', 'needs_owner')),
          input jsonb not null default '{}',
          output jsonb,
          error text,
          attempts integer not null default 0,
          created_by uuid references users(id),
          created_at timestamptz not null default now(),
          started_at timestamptz,
          finished_at timestamptz
        );
        create index tasks_business_idx on tasks(business_id, created_at desc);

        create table catalogue_imports (
          id uuid primary key default gen_random_uuid(),
          business_id uuid not null references businesses(id) on delete cascade,
          document_id uuid not null references documents(id) on delete cascade,
          method varchar(20) not null check (method in ('spreadsheet', 'ai_pdf')),
          status varchar(20) not null default 'mapping'
            check (status in ('extracting', 'mapping', 'committed', 'failed')),
          columns jsonb not null default '[]',
          mapping jsonb not null default '{}',
          rows jsonb not null default '[]',
          errors jsonb not null default '[]',
          created_count integer not null default 0,
          task_id uuid references tasks(id),
          created_at timestamptz not null default now(),
          committed_at timestamptz
        );
        create index catalogue_imports_business_idx on catalogue_imports(business_id);

        create table products (
          id uuid primary key default gen_random_uuid(),
          business_id uuid not null references businesses(id) on delete cascade,
          sku varchar(120),
          name varchar(300) not null,
          description text,
          category varchar(200),
          material varchar(200),
          unit_price numeric(14, 4),
          currency char(3),
          unit varchar(40),
          moq integer,
          hs_code varchar(20),
          attributes jsonb not null default '{}',
          source_document_id uuid references documents(id) on delete set null,
          import_id uuid references catalogue_imports(id) on delete set null,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        );
        create index products_business_idx on products(business_id);
        create unique index products_business_sku_uniq on products(business_id, sku)
          where sku is not null;

        create table profile_versions (
          id uuid primary key default gen_random_uuid(),
          business_id uuid not null references businesses(id) on delete cascade,
          version integer not null,
          status varchar(20) not null default 'draft'
            check (status in ('draft', 'approved', 'superseded')),
          source varchar(20) not null check (source in ('ai', 'fallback', 'owner')),
          profile jsonb not null default '{}',
          notes jsonb not null default '[]',
          task_id uuid references tasks(id),
          created_by uuid references users(id),
          approved_by uuid references users(id),
          approved_at timestamptz,
          created_at timestamptz not null default now(),
          unique (business_id, version)
        );
        -- At most one approved profile per business: agents read only this one.
        create unique index profile_versions_one_approved
          on profile_versions(business_id) where status = 'approved';

        create table model_calls (
          id uuid primary key default gen_random_uuid(),
          business_id uuid not null references businesses(id) on delete cascade,
          task_id uuid references tasks(id) on delete set null,
          model varchar(80) not null,
          purpose varchar(80) not null,
          input_tokens integer,
          output_tokens integer,
          latency_ms integer,
          stop_reason varchar(40),
          error text,
          created_at timestamptz not null default now()
        );
        create index model_calls_business_idx on model_calls(business_id, created_at desc);

        create table audit_log (
          id bigserial primary key,
          business_id uuid not null references businesses(id) on delete cascade,
          actor_type varchar(20) not null check (actor_type in ('user', 'system', 'agent')),
          actor_id varchar(120),
          action varchar(80) not null,
          target_type varchar(40),
          target_id varchar(80),
          detail jsonb not null default '{}',
          created_at timestamptz not null default now()
        );
        create index audit_log_business_idx on audit_log(business_id, created_at desc);

        -- Creating a business is the one write that happens before the user has a
        -- membership, so it goes through a definer function that adds the owner in
        -- the same statement. It only acts for the user in the request context.
        create or replace function create_business(p_name text, p_onboarding jsonb)
          returns uuid
          language plpgsql security definer set search_path = public as
          $$
          declare
            v_user uuid := app_user_id();
            v_id uuid;
          begin
            if v_user is null then
              raise exception 'no user in request context';
            end if;
            insert into businesses (name, onboarding) values (p_name, coalesce(p_onboarding, '{}'))
              returning id into v_id;
            insert into memberships (business_id, user_id, role) values (v_id, v_user, 'owner');
            insert into audit_log (business_id, actor_type, actor_id, action, target_type, target_id)
              values (v_id, 'user', v_user::text, 'business.created', 'business', v_id::text);
            return v_id;
          end
          $$;
        """
    )

    # Row-level security. The API's role is not the table owner, so every policy
    # applies to it (superusers bypass RLS, so never run the API as one). Tenant
    # tables also FORCE RLS for the owner. businesses, memberships and audit_log
    # do not, because create_business() runs as the owner to add the first
    # membership.
    op.execute(
        """
        alter table businesses enable row level security;
        create policy businesses_select on businesses for select
          using (exists (select 1 from memberships m
                         where m.business_id = businesses.id and m.user_id = app_user_id()));
        create policy businesses_update on businesses for update
          using (id = app_business_id() and app_is_member())
          with check (id = app_business_id());

        alter table memberships enable row level security;
        create policy memberships_select on memberships for select
          using (user_id = app_user_id() or (business_id = app_business_id() and app_is_member()));

        alter table audit_log enable row level security;
        create policy audit_select on audit_log for select
          using (business_id = app_business_id() and app_is_member());
        create policy audit_insert on audit_log for insert
          with check (business_id = app_business_id() and app_is_member());
        """
    )
    for table in TENANT_TABLES:
        op.execute(
            f"""
            alter table {table} enable row level security;
            alter table {table} force row level security;
            create policy {table}_tenant on {table} for all
              using (business_id = app_business_id() and app_is_member())
              with check (business_id = app_business_id() and app_is_member());
            """
        )

    # Grants for the API role, if it exists (created by infra/postgres/init.sql).
    tenant_list = ", ".join(TENANT_TABLES)
    op.execute(
        f"""
        do $$
        begin
          if exists (select 1 from pg_roles where rolname = '{APP_ROLE}') then
            grant usage on schema public to {APP_ROLE};
            grant select, insert, update on users to {APP_ROLE};
            grant select, update on businesses to {APP_ROLE};
            grant select on memberships to {APP_ROLE};
            grant select, insert, update, delete on {tenant_list} to {APP_ROLE};
            -- Append-only: no update or delete on the audit log.
            grant select, insert on audit_log to {APP_ROLE};
            grant usage on sequence audit_log_id_seq to {APP_ROLE};
            grant execute on function create_business(text, jsonb) to {APP_ROLE};
          end if;
        end
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        drop function if exists create_business(text, jsonb);
        drop table if exists audit_log, model_calls, profile_versions, products,
          catalogue_imports, tasks, documents, memberships, businesses, users cascade;
        drop function if exists app_is_member();
        drop function if exists app_business_id();
        drop function if exists app_user_id();
        """
    )
