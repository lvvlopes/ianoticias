"""Autenticação simples de admin via cookie de sessão assinado.

O login é um form com senha (ADMIN_PASSWORD). Ao acertar, marca
`request.session["is_admin"] = True`. Rotas protegidas usam `require_admin`
como dependency.
"""
from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request, status

from ianoticias.config.settings import settings


def is_admin(request: Request) -> bool:
    return bool(request.session.get("is_admin"))


def login(request: Request, password: str) -> bool:
    """Valida a senha com compare_digest (evita timing attacks) e marca sessão."""
    if not settings.admin_password:
        # Sem senha configurada = nunca autentica (evita expor endpoints por acidente).
        return False
    if hmac.compare_digest(password.encode("utf-8"), settings.admin_password.encode("utf-8")):
        request.session["is_admin"] = True
        return True
    return False


def logout(request: Request) -> None:
    request.session.pop("is_admin", None)


def require_admin(request: Request) -> None:
    """Dependency FastAPI: bloqueia com 401 se não estiver logado."""
    if not is_admin(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação de admin necessária.",
        )


AdminRequired = Depends(require_admin)
