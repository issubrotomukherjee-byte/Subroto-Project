"""
Role-based access control via dependency injection.

Current implementation: reads role from ``X-User-Role`` HTTP header.
Replace this module with JWT / OAuth later — route signatures stay the same.
"""

from fastapi import Header, HTTPException


def get_current_user(x_user_role: str = Header(default="worker")) -> dict:
    """Return a lightweight user dict derived from the request header.

    Accepted roles: ``admin``, ``worker``.
    Defaults to ``worker`` when the header is missing (safe default —
    purchase_price is never exposed accidentally).
    """
    role = x_user_role.lower().strip()
    if role not in ("admin", "worker"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{x_user_role}'. Must be 'admin' or 'worker'.",
        )
    return {"role": role}


def require_admin(user: dict) -> dict:
    """Raise 403 if the current user is not an admin."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
