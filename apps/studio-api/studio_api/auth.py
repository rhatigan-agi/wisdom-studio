"""Identity seam for inbound requests.

Studio's documented posture is single-user/local. Most forks will keep the
default ``User(id="local")`` and never touch this module. Forks that deploy
behind real auth have two opt-in paths:

1. **Trust an upstream header.** Configure
   ``WISDOM_STUDIO_TRUST_USER_HEADER`` (e.g. ``X-Authenticated-User``) and
   put the app behind a reverse proxy that strips client-supplied copies of
   that header and writes the authenticated identity into it. The
   ``WISDOM_STUDIO_TRUSTED_PROXY_CIDRS`` allowlist defaults to loopback —
   the dependency refuses requests from any other peer, fail-closed, so a
   misconfigured deploy can never accept attacker-supplied identities.

2. **Override the dependency.** ``app.dependency_overrides[get_current_user]
   = your_resolver`` is the canonical FastAPI pattern for swapping in a JWT
   / OAuth / session resolver of your own. Studio doesn't ship a JWT
   verifier on purpose — that surface area belongs in the fork, not in the
   reference UI.

Routes that want a user attached should depend on :data:`CurrentUser`:

.. code-block:: python

    from studio_api.auth import CurrentUser

    @app.get("/api/me")
    async def me(user: CurrentUser) -> dict[str, str]:
        return {"id": user.id}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from ipaddress import ip_address, ip_network
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from studio_api.settings import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class User:
    """Identity attached to an inbound request."""

    id: str


_LOCAL_USER = User(id="local")


def _peer_ip(request: Request) -> str | None:
    client = request.client
    return client.host if client else None


def _peer_is_trusted(peer_ip: str | None, allowlist: tuple[str, ...]) -> bool:
    if not allowlist or not peer_ip:
        return False
    try:
        addr = ip_address(peer_ip)
    except ValueError:
        return False
    for cidr in allowlist:
        try:
            if addr in ip_network(cidr, strict=False):
                return True
        except ValueError:
            # Misconfigured CIDR entry — log once at request time, skip.
            logger.warning("studio.auth.invalid_cidr", extra={"cidr": cidr})
    return False


async def get_current_user(request: Request) -> User:
    """Resolve the identity attached to ``request``.

    Default behavior: every request maps to ``User(id="local")``.

    When ``WISDOM_STUDIO_TRUST_USER_HEADER`` is set, the named header is read
    *only when the immediate peer is in the trusted-proxy CIDR allowlist*
    (default loopback). Untrusted peers are refused with 503; missing
    headers from trusted peers are refused with 401. Both responses are
    fail-closed — a header-trust deploy that loses its proxy goes dark
    rather than open.
    """
    header_name = settings.trust_user_header
    if not header_name:
        return _LOCAL_USER

    allowlist = settings.trusted_proxy_cidrs_list
    if not _peer_is_trusted(_peer_ip(request), allowlist):
        logger.warning(
            "studio.auth.untrusted_peer",
            extra={"peer_ip": _peer_ip(request), "header": header_name},
        )
        raise HTTPException(status_code=503, detail="auth_proxy_misconfigured")

    raw = request.headers.get(header_name, "").strip()
    if not raw:
        raise HTTPException(status_code=401, detail="missing_user_header")
    return User(id=raw)


CurrentUser = Annotated[User, Depends(get_current_user)]
