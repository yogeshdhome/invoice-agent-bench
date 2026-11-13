"""Synthetic JWT auth. HS256 with a test-only secret (deviation from RS256 in the ADR: fewer moving
parts for a laptop benchmark; the principal model is what matters)."""
from __future__ import annotations

import os
import time

import jwt
from pydantic import BaseModel, ConfigDict

from ..domain.models import Role

ISSUER = "invoice-bench-synthetic"
DEFAULT_SECRET = "synthetic-test-secret-do-not-use"
ALL_TENANTS = "*"


class AuthError(Exception):
    pass


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True)
    user_id: str
    tenant_id: str
    bu_ids: tuple[str, ...] = ()
    roles: tuple[Role, ...] = ()

    @property
    def is_service_account(self) -> bool:
        return Role.SERVICE_ACCOUNT in self.roles

    def has_any_role(self, roles: list[str] | tuple[str, ...]) -> bool:
        return any(r in roles for r in self.roles)


# The broad credential the BASELINE uses (confused-deputy pattern, decision D4).
SERVICE_PRINCIPAL = Principal(user_id="svc-invoice-agent", tenant_id=ALL_TENANTS, roles=(Role.SERVICE_ACCOUNT,))


def secret() -> str:
    return os.environ.get("INVOICE_BENCH_JWT_SECRET", DEFAULT_SECRET)


def issue_token(p: Principal, key: str | None = None, ttl_s: int = 3600, now: int | None = None) -> str:
    now = int(now if now is not None else time.time())
    claims = {"iss": ISSUER, "sub": p.user_id, "tid": p.tenant_id, "bus": list(p.bu_ids),
              "roles": [str(r) for r in p.roles], "iat": now, "exp": now + ttl_s}
    return jwt.encode(claims, key or secret(), algorithm="HS256")


def verify_token(token: str, key: str | None = None) -> Principal:
    try:
        c = jwt.decode(token, key or secret(), algorithms=["HS256"], issuer=ISSUER,
                       options={"require": ["exp", "iat", "sub", "iss"]})
    except jwt.PyJWTError as e:
        raise AuthError(str(e)) from e
    return Principal(user_id=c["sub"], tenant_id=c["tid"], bu_ids=tuple(c.get("bus", [])),
                     roles=tuple(Role(r) for r in c.get("roles", [])))
