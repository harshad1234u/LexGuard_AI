-- LexGuard AI - optional metadata persistence (Phase 23).
--
-- What this schema can hold: document metadata, analysis-job metadata,
-- RELEASED findings, and Q&A metadata. What it cannot hold, by construction:
-- PDFs, page text, raw filenames, questions, answers, withheld or unverified
-- model output, reasoning-note text, prompts or keys. There are no columns for
-- any of them.
--
-- Access: the browser never talks to Supabase. Row Level Security is enabled
-- on every table and NO policy is created, so the anon and authenticated
-- roles can read and write nothing. Only the backend's service role, which
-- bypasses RLS, writes here. Grants to anon/authenticated are revoked as a
-- second layer.
--
-- Not anonymous: rows are linked by document id, and a salted filename hash
-- still identifies a file to anyone holding both the file and the salt.

create table if not exists public.documents (
    id                text primary key,
    filename_sha256   text not null check (length(filename_sha256) = 64),
    file_extension    text not null check (length(file_extension) <= 10),
    page_count        integer not null check (page_count >= 0),
    detected_language text not null check (detected_language in ('en', 'ta', 'mixed', 'other')),
    created_at        timestamptz not null default now(),
    expires_at        timestamptz not null
);

create index if not exists documents_expires_at_idx on public.documents (expires_at);

create table if not exists public.analysis_jobs (
    id                          text primary key,
    document_id                 text not null references public.documents (id) on delete cascade,
    status                      text not null check (status in ('completed', 'failed')),
    provider                    text,
    model                       text,
    reasoning_provider          text,
    reasoning_model             text,
    verification_policy_version text,
    language                    text check (language in ('en', 'ta')),
    failure_kind                text,
    duration_ms                 integer,
    proposed_count              integer not null default 0,
    released_count              integer not null default 0,
    withheld_count              integer not null default 0,
    reasoning_status            text,
    notes_released_count        integer not null default 0,
    notes_withheld_count        integer not null default 0,
    created_at                  timestamptz not null default now()
);

create index if not exists analysis_jobs_document_idx on public.analysis_jobs (document_id);

create table if not exists public.released_findings (
    id                   bigserial primary key,
    analysis_job_id      text not null references public.analysis_jobs (id) on delete cascade,
    finding_id           text not null,
    type                 text not null,
    claim                text not null,
    quote                text not null,
    page_number          integer not null check (page_number >= 1),
    section_reference    text,
    verification_status  text not null check (verification_status = 'verified'),
    explanation_verified boolean not null,
    created_at           timestamptz not null default now(),
    unique (analysis_job_id, finding_id)
);

create table if not exists public.qa_events (
    id                          bigserial primary key,
    document_id                 text not null references public.documents (id) on delete cascade,
    provider                    text,
    model                       text,
    verification_policy_version text,
    answer_status               text not null check (answer_status in ('supported', 'partially_supported', 'not_found')),
    question_language           text not null check (question_language in ('en', 'ta')),
    evidence_count              integer not null default 0,
    claims_checked              integer not null default 0,
    claims_withheld             integer not null default 0,
    translation_released        boolean not null default false,
    created_at                  timestamptz not null default now()
);

create index if not exists qa_events_document_idx on public.qa_events (document_id);

-- Row Level Security: on, with no policies. Deliberately.
alter table public.documents          enable row level security;
alter table public.analysis_jobs      enable row level security;
alter table public.released_findings  enable row level security;
alter table public.qa_events          enable row level security;

revoke all on public.documents, public.analysis_jobs, public.released_findings, public.qa_events
    from anon, authenticated;
revoke all on sequence public.released_findings_id_seq, public.qa_events_id_seq
    from anon, authenticated;

-- The backend refuses to write unless this answers with the expected version,
-- so a project without this migration (and its RLS) is never written to.
create or replace function public.lexguard_schema_version()
returns text
language sql
stable
security invoker
set search_path = ''
as $$ select '1'::text $$;

revoke all on function public.lexguard_schema_version() from public, anon, authenticated;
grant execute on function public.lexguard_schema_version() to service_role;
