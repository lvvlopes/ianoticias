"""POST /api/ingest — protegido por sessão de admin."""
from __future__ import annotations

from fastapi import APIRouter, Request

from ianoticias.security.auth import AdminRequired
from ianoticias.services.pipeline import run_ingest
from ianoticias.templating import templates

router = APIRouter(prefix="/api", tags=["ingest"])


@router.post("/ingest")
async def ingest(request: Request, _: None = AdminRequired):
    summary = await run_ingest()

    # HTMX espera fragmento HTML; clientes normais recebem JSON.
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            "partials/ingest_result.html",
            {"request": request, "summary": summary.to_dict()},
        )
    return summary.to_dict()
