import re


class SqlValidationError(ValueError):
    pass


_DANGEROUS_KEYWORDS = [
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "replace",
    "truncate",
    "attach",
    "detach",
    "pragma",
    "vacuum",
    "reindex",
    "grant",
    "revoke",
    "shutdown",
    "exec",
    "execute",
    "xp_",
    "sp_",
]

_SYSTEM_TABLES = [
    "sqlite_master",
    "sqlite_temp_master",
]


def validate_sql(sql: str) -> str:
    """
    Very conservative guardrail:
    - single statement
    - SELECT/CTE-only
    - blocks common dangerous keywords + sqlite system catalogs
    """
    if not sql or not sql.strip():
        raise SqlValidationError("Empty SQL.")

    s = sql.strip().strip(";").strip()
    lower = s.lower()

    # Reject multiple statements.
    if ";" in lower:
        raise SqlValidationError("Only single-statement queries are allowed.")

    # Must be SELECT or WITH (CTE).
    if not (lower.startswith("select") or lower.startswith("with")):
        raise SqlValidationError("Only SELECT queries are allowed.")

    # Block dangerous keywords (word-boundary where possible).
    for kw in _DANGEROUS_KEYWORDS:
        if kw.endswith("_"):
            if kw in lower:
                raise SqlValidationError(f"Disallowed keyword: {kw}")
        else:
            if re.search(rf"\b{re.escape(kw)}\b", lower):
                raise SqlValidationError(f"Disallowed keyword: {kw}")

    # Block sqlite system tables.
    for t in _SYSTEM_TABLES:
        if re.search(rf"\b{re.escape(t)}\b", lower):
            raise SqlValidationError("Access to system tables is not allowed.")

    return s
