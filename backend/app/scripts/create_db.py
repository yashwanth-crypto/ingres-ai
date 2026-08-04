"""Create the database named in DATABASE_URL, if it does not already exist.

    python -m app.scripts.create_db

Postgres has no "CREATE DATABASE IF NOT EXISTS", and a database cannot be
created from inside a transaction or from a connection to itself. So this
connects to the built-in `postgres` maintenance database using the same
credentials, checks the catalog, and creates the target if it is missing.

Safe to run repeatedly. Never drops anything.
"""

from __future__ import annotations

import sys
from urllib.parse import urlparse

import psycopg
from psycopg import sql

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    parsed = urlparse(settings.database_url)
    target = (parsed.path or "").lstrip("/")

    if not target:
        sys.exit("ERROR: DATABASE_URL has no database name (expected .../dbname).")
    if parsed.hostname is None:
        sys.exit("ERROR: DATABASE_URL has no host.")

    # Same server and credentials, but the maintenance database.
    admin_url = parsed._replace(path="/postgres").geturl()

    try:
        with psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (target,)
            ).fetchone()
            if exists:
                print(f"Database {target!r} already exists on {parsed.hostname}.")
                return
            conn.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target))
            )
            print(f"Created database {target!r} on {parsed.hostname}.")
    except psycopg.OperationalError as exc:
        # The message can contain the connection string; report only the reason.
        reason = str(exc).strip().splitlines()[0] if str(exc).strip() else "unknown"
        sys.exit(
            f"ERROR: could not connect to Postgres at {parsed.hostname}:"
            f"{parsed.port or 5432} - {reason}\n"
            f"Check the password in backend/.env and that the postgresql service "
            f"is running."
        )


if __name__ == "__main__":
    main()
