"""Modelos SQLAlchemy 2.0 (async) para o IANoticias.

A tabela `articles` é a única entidade. Os enums são espelhados no
migrations/001_init.sql para o Postgres do Supabase.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Category(str, enum.Enum):
    ia = "ia"
    eng_dev_ia = "eng_dev_ia"
    gestao_ia = "gestao_ia"


class IgStatus(str, enum.Enum):
    draft = "draft"
    posted = "posted"


# Enums nomeados no Postgres (mesmos nomes usados na migration).
category_enum = Enum(
    Category,
    name="category",
    values_callable=lambda e: [m.value for m in e],
    create_type=False,  # o tipo é criado pela migration SQL, não pelo SQLAlchemy
)
ig_status_enum = Enum(
    IgStatus,
    name="ig_status",
    values_callable=lambda e: [m.value for m in e],
    create_type=False,
)


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # URL canônica — chave de deduplicação (unique).
    source_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    title_original: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Category] = mapped_column(category_enum, nullable=False)

    ig_title: Mapped[str] = mapped_column(Text, nullable=False)
    ig_content: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Imagem original da matéria (og:image) — fundo do card + thumb na home.
    source_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)

    featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    ig_status: Mapped[IgStatus] = mapped_column(
        ig_status_enum, nullable=False, default=IgStatus.draft
    )
    ig_post_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_articles_day", "day"),
        Index("ix_articles_category", "category"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Article {self.id} {self.category} {self.ig_title!r}>"


class FeedSource(Base):
    """Fonte de RSS/Atom editável pela tela /admin (substitui config/feeds.py)."""

    __tablename__ = "feed_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    region: Mapped[str] = mapped_column(String(8), nullable=False, default="world")
    hint: Mapped[Category] = mapped_column(category_enum, nullable=False, default=Category.ia)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<FeedSource {self.name!r} {self.hint} enabled={self.enabled}>"


class AppSetting(Base):
    """Par chave/valor para configs editáveis (ex.: prompts do LLM)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AppSetting {self.key!r}>"
