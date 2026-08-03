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
# https_only vira True automaticamente em produção HTTPS (Vercel define VERCEL_ENV).
import os as _os  # noqa: E402
_is_prod_https = _os.getenv("VERCEL_ENV") == "production"
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    https_only=_is_prod_https,
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


# ---------------------------------------------------------------------------
# Diagnóstico: quando DEBUG_ERRORS=1, mostra o traceback direto no navegador.
# É a forma mais rápida de descobrir o erro em produção sem caçar log.
# DESLIGUE em produção normal (traceback expõe caminhos internos).
# ---------------------------------------------------------------------------
if _os.getenv("DEBUG_ERRORS") == "1":
    import traceback as _tb
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import PlainTextResponse

    class _DebugErrorsMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            try:
                return await call_next(request)
            except Exception:  # noqa: BLE001
                return PlainTextResponse(_tb.format_exc(), status_code=500)

    app.add_middleware(_DebugErrorsMiddleware)


@app.get("/api/_diag")
async def _diag():
    """Health check completo: config, filesystem, DB. Sempre público, sem segredos."""
    from pathlib import Path as _P
    static_dir = BASE_DIR / "static"
    fonts_dir = static_dir / "fonts"
    hero_dir = static_dir / "hero"
    result = {
        "ok": True,
        "python_env": _os.getenv("VERCEL_ENV") or "local",
        "cwd": str(_P.cwd()),
        "base_dir": str(BASE_DIR),
        "static_exists": static_dir.exists(),
        "fonts_dir_exists": fonts_dir.exists(),
        "fonts": sorted(p.name for p in fonts_dir.iterdir()) if fonts_dir.exists() else [],
        "hero_dir_exists": hero_dir.exists(),
        "hero_files": sorted(p.name for p in hero_dir.iterdir()) if hero_dir.exists() else [],
        "has_database_url": bool(settings.database_url),
        "has_openai": settings.has_openai,
        "has_storage": settings.has_storage,
        "has_instagram": settings.has_instagram,
        "openai_model": settings.openai_model,
    }
    # Ping ao banco (não vaza credencial)
    try:
        from sqlalchemy import text
        from ianoticias.db.engine import SessionLocal
        async with SessionLocal() as s:
            v = await s.scalar(text("select 1"))
            result["db_ping"] = f"ok ({v})"
    except Exception as exc:  # noqa: BLE001
        result["ok"] = False
        result["db_ping"] = f"{type(exc).__name__}: {exc}"
    return result
