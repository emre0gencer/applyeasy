"""Per-browser ownership binding to mitigate IDOR on /status and /download.

There is no login. Instead, on upload we mint an opaque owner token and store it
in an HttpOnly cookie. Sessions and the runs derived from them are tagged with
that token, and read endpoints verify the caller's cookie matches the run's
owner before returning anyone's resume PDF / change summary.

Backward-compatible: records created before this feature have ``owner_id=None``
and are not subject to the check (they were already public and have since been
untracked from git).
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Request, Response

COOKIE_NAME = "ae_owner"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def get_owner_id(request: Request) -> Optional[str]:
    """Return the caller's owner token from the cookie, if present."""
    return request.cookies.get(COOKIE_NAME)


def ensure_owner_cookie(request: Request, response: Response) -> str:
    """Return the caller's owner token, minting + setting one if absent."""
    owner_id = get_owner_id(request)
    if not owner_id:
        owner_id = str(uuid.uuid4())
        response.set_cookie(
            key=COOKIE_NAME,
            value=owner_id,
            max_age=_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",   # dev is same-origin via the Vite proxy; prod cross-origin needs SameSite=None; Secure
        )
    return owner_id


def owns(record_owner_id: Optional[str], request: Request) -> bool:
    """True if the caller may access a record with the given owner.

    Records with no owner (legacy) are treated as public for backward compat.
    """
    if record_owner_id is None:
        return True
    return get_owner_id(request) == record_owner_id
