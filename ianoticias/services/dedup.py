"""Canonicalização de URL para deduplicação.

Regras:
- lowercase de scheme/host,
- remove fragment (#...),
- remove query params de tracking comuns (utm_*, fbclid, gclid, ref, ...).
- Se a URL for inválida, retorna a original.

O hash SHA-256 fica exposto caso queira usar em outro contexto, mas a dedup no
banco é pela coluna `source_url` (unique).
"""
from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {"fbclid", "gclid", "gclsrc", "mc_cid", "mc_eid", "ref", "ref_src", "igshid"}


def canonical_url(raw: str) -> str:
    if not raw:
        return raw
    try:
        parts = urlsplit(raw.strip())
    except ValueError:
        return raw

    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()

    # Filtra query params de tracking.
    cleaned = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.startswith(_TRACKING_PREFIXES) and k.lower() not in _TRACKING_KEYS
    ]
    query = urlencode(cleaned, doseq=True)

    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, query, ""))


def url_hash(raw: str) -> str:
    return hashlib.sha256(canonical_url(raw).encode("utf-8")).hexdigest()
