-- ============================================================================
-- IANoticias — migration 002: fontes de feed e configurações editáveis
-- Rode no SQL Editor do Supabase DEPOIS da 001_init.sql.
-- ============================================================================

-- --- Fontes de RSS/Atom (editáveis pela tela /admin) ------------------------
-- Substitui a lista hardcoded de ianoticias/config/feeds.py. Na primeira
-- execução, o app semeia esta tabela com os defaults do código se ela estiver
-- vazia (ver ianoticias/services/feeds.py).
create table if not exists feed_sources (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    url         text not null unique,          -- endpoint do RSS/Atom
    region      text not null default 'world', -- 'br' | 'world'
    hint        category not null default 'ia',-- categoria provável (dica ao LLM)
    enabled     boolean not null default true, -- desativar sem excluir
    position    integer not null default 0,    -- ordenação na tela admin
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index if not exists ix_feed_sources_enabled on feed_sources (enabled);
create index if not exists ix_feed_sources_position on feed_sources (position);

-- --- Configurações chave/valor (prompt do LLM, etc.) ------------------------
-- Guardamos os textos de prompt aqui para permitir edição sem redeploy.
-- Chaves usadas hoje: 'llm.system_prompt', 'llm.user_template'.
create table if not exists app_settings (
    key         text primary key,
    value       text not null,
    updated_at  timestamptz not null default now()
);
