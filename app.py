"""Entrypoint da aplicação — a Vercel detecta a instância `app = FastAPI()`.

Também serve para rodar localmente:  uvicorn app:app --reload
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from ianoticias.config.settings import settings
from ianoticias.routers import admin, home, ingest, instagram

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="IANoticias", docs_url=None, redoc_url=None)

# Sessão assinada em cookie (usada para o login de admin).
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    https_only=False,  # em produção (HTTPS) pode ser True
)

# Arquivos estáticos (fontes do card, favicon, etc.).
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Rotas
app.include_router(home.router)
app.include_router(ingest.router)
app.include_router(instagram.router)
app.include_router(admin.router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
