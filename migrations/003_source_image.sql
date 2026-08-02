-- ============================================================================
-- IANoticias — migration 003: imagem original da matéria
-- Rode no SQL Editor do Supabase DEPOIS da 002_admin.sql.
-- (Local: python scripts/run_migration.py migrations/003_source_image.sql)
-- ============================================================================

-- URL da imagem de destaque da matéria (og:image), usada como fundo do card
-- do Instagram e como thumb na home. Pode ser nula (fallback: default.jpg).
alter table articles add column if not exists source_image_url text;
