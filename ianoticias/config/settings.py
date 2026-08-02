"""Carregamento e validação das configurações via variáveis de ambiente.

Usa apenas python-dotenv + os.getenv (sem pydantic-settings) para manter as
dependências enxutas. As settings são expostas como um singleton `settings`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

# Carrega .env quando presente (local). Na Vercel as envs vêm do painel.
load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw is not None and raw.strip() != "" else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Banco
    database_url: str = os.getenv("DATABASE_URL", "")

    # Supabase Storage
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    supabase_storage_bucket: str = os.getenv("SUPABASE_STORAGE_BUCKET", "ianoticias-cards")

    # OpenAI
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Instagram / Meta
    ig_user_id: str = os.getenv("IG_USER_ID", "")
    ig_access_token: str = os.getenv("IG_ACCESS_TOKEN", "")
    meta_app_id: str = os.getenv("META_APP_ID", "")
    meta_app_secret: str = os.getenv("META_APP_SECRET", "")
    graph_api_version: str = os.getenv("GRAPH_API_VERSION", "v21.0")

    # Legenda / crescimento
    ig_handle: str = os.getenv("IG_HANDLE", "")                 # ex.: ianoticiaslv (sem @)
    ig_brand_hashtag: str = os.getenv("IG_BRAND_HASHTAG", "IANoticias")  # sem #
    ig_hashtags_in_comment: bool = field(
        default_factory=lambda: _bool("IG_HASHTAGS_IN_COMMENT", True)
    )

    # App
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    session_secret: str = os.getenv("SESSION_SECRET", "dev-insecure-secret-change-me")
    public_site_url: str = os.getenv("PUBLIC_SITE_URL", "http://localhost:8000")

    # Pipeline
    ingest_max_items: int = field(default_factory=lambda: _int("INGEST_MAX_ITEMS", 12))
    ingest_feed_timeout: int = field(default_factory=lambda: _int("INGEST_FEED_TIMEOUT", 8))
    featured_per_category: int = field(default_factory=lambda: _int("FEATURED_PER_CATEGORY", 4))
    # Valida se o link responde 2xx antes de salvar (evita links quebrados no portal).
    validate_links: bool = field(default_factory=lambda: _bool("INGEST_VALIDATE_LINKS", True))
    # Pré-filtro por palavra-chave antes do cap/LLM (remove ruído de feeds gerais).
    prefilter_relevance: bool = field(default_factory=lambda: _bool("INGEST_PREFILTER", True))

    # Mocks
    mock_llm: bool = field(default_factory=lambda: _bool("MOCK_LLM"))
    mock_ig: bool = field(default_factory=lambda: _bool("MOCK_IG"))
    mock_storage: bool = field(default_factory=lambda: _bool("MOCK_STORAGE"))

    # Fuso de referência para agrupar por dia (horário de Brasília)
    timezone: str = "America/Sao_Paulo"

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key) and not self.mock_llm

    @property
    def has_storage(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key) and not self.mock_storage

    @property
    def has_instagram(self) -> bool:
        return bool(self.ig_user_id and self.ig_access_token) and not self.mock_ig


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
