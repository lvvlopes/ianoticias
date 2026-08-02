"""Faz UMA chamada real à OpenAI com o modelo configurado e mostra o resultado
ou o erro exato da API. Serve para validar OPENAI_MODEL / OPENAI_API_KEY.

Uso: python scripts/diag_llm.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ianoticias.config.settings import settings  # noqa: E402


async def main() -> None:
    print(f"OPENAI_MODEL = {settings.openai_model!r}")
    print(f"MOCK_LLM     = {settings.mock_llm}")
    print(f"API key      = {'(preenchida)' if settings.openai_api_key else '(VAZIA)'}")
    print("-" * 50)

    if settings.mock_llm:
        print("MOCK_LLM está LIGADO — o pipeline não chama a OpenAI (salva mock).")
        return
    if not settings.openai_api_key:
        print("OPENAI_API_KEY vazia — o pipeline cai no mock.")
        return

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Responda só JSON."},
                {"role": "user", "content": 'Devolva {"ok": true}'},
            ],
        )
        print("SUCESSO ✓  Resposta:", resp.choices[0].message.content)
        print("O modelo está válido. Se o ingest ainda não grava, o problema é outro.")
    except Exception as exc:  # noqa: BLE001
        print(f"ERRO DA API: {type(exc).__name__}")
        print(str(exc)[:500])
        print("-" * 50)
        print("Se citar 'model_not_found' ou 'invalid model', o OPENAI_MODEL está errado.")
        print("IDs válidos são minúsculos, com hífen e sem espaço. Ex.: gpt-4o-mini")


if __name__ == "__main__":
    asyncio.run(main())
