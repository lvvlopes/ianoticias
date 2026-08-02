"""Ponte entre as configurações editáveis (banco) e os defaults do código.

- Feeds: lê `feed_sources`; se vazia, semeia com `config/feeds.py:FEEDS`.
- Prompts do LLM: lê `app_settings`; se ausentes, semeia com os defaults de
  `services/llm.py`.

Assim o comportamento é idêntico ao anterior enquanto o admin não mexer em nada,
e passa a refletir o banco assim que ele salvar algo.
"""
from __future__ import annotations

from dataclasses import dataclass

from ianoticias.config.feeds import FEEDS as DEFAULT_FEEDS
from ianoticias.config.feeds import Feed
from ianoticias.db.engine import SessionLocal
from ianoticias.repositories import feeds_repo, settings_repo
from ianoticias.services.llm import DEFAULT_SYSTEM_PROMPT, DEFAULT_USER_TEMPLATE

KEY_SYSTEM_PROMPT = "llm.system_prompt"
KEY_USER_TEMPLATE = "llm.user_template"


@dataclass(frozen=True)
class LLMConfig:
    system_prompt: str
    user_template: str


async def load_active_feeds() -> list[Feed]:
    """Fontes ativas como dataclass Feed (compatível com o pipeline).

    Semeia a tabela na primeira execução (se estiver vazia).
    """
    async with SessionLocal() as session:
        if await feeds_repo.count(session) == 0:
            await feeds_repo.bulk_insert_defaults(session, DEFAULT_FEEDS)
            await session.commit()
        rows = await feeds_repo.list_enabled(session)

    return [
        Feed(name=r.name, url=r.url, region=r.region, hint=r.hint.value)  # type: ignore[arg-type]
        for r in rows
    ]


async def ensure_llm_defaults(session) -> None:
    """Garante que as chaves de prompt existam no banco (semeia se faltar)."""
    existing = await settings_repo.get_many(session, [KEY_SYSTEM_PROMPT, KEY_USER_TEMPLATE])
    if KEY_SYSTEM_PROMPT not in existing:
        await settings_repo.set(session, KEY_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT)
    if KEY_USER_TEMPLATE not in existing:
        await settings_repo.set(session, KEY_USER_TEMPLATE, DEFAULT_USER_TEMPLATE)


async def load_llm_config(session) -> LLMConfig:
    """Prompts atuais do banco, com fallback para os defaults do código."""
    values = await settings_repo.get_many(session, [KEY_SYSTEM_PROMPT, KEY_USER_TEMPLATE])
    return LLMConfig(
        system_prompt=values.get(KEY_SYSTEM_PROMPT) or DEFAULT_SYSTEM_PROMPT,
        user_template=values.get(KEY_USER_TEMPLATE) or DEFAULT_USER_TEMPLATE,
    )
