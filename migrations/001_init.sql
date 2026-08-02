-- ============================================================================
-- IANoticias — migration inicial
-- Rode no SQL Editor do Supabase (projeto > SQL Editor > New query).
-- ============================================================================

-- Extensão para gen_random_uuid() (já vem habilitada no Supabase, mas garantimos).
create extension if not exists "pgcrypto";

-- --- Enums ------------------------------------------------------------------
do $$
begin
    if not exists (select 1 from pg_type where typname = 'category') then
        create type category as enum ('ia', 'eng_dev_ia', 'gestao_ia');
    end if;
    if not exists (select 1 from pg_type where typname = 'ig_status') then
        create type ig_status as enum ('draft', 'posted');
    end if;
end$$;

-- --- Tabela articles --------------------------------------------------------
create table if not exists articles (
    id             uuid primary key default gen_random_uuid(),
    source_name    varchar(200) not null,
    source_url     text not null unique,          -- URL canônica = dedup
    title_original text not null,
    category       category not null,
    ig_title       text not null,
    ig_content     text not null,
    hashtags       text[] not null default '{}',
    image_url      text,                          -- URL pública do card (Supabase Storage)
    published_at   timestamptz not null,
    fetched_at     timestamptz not null,
    day            date not null,                 -- para agrupar na home (fuso America/Sao_Paulo)
    featured       boolean not null default false,
    ig_status      ig_status not null default 'draft',
    ig_post_id     text,
    created_at     timestamptz not null default now()
);

-- --- Índices ----------------------------------------------------------------
create index if not exists ix_articles_day on articles (day);
create index if not exists ix_articles_category on articles (category);
-- unique(source_url) já criado pela constraint da coluna.

-- Índice composto útil para a home (dia + featured).
create index if not exists ix_articles_day_featured on articles (day desc, featured desc);
