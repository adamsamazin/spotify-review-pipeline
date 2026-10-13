"""Create the read-only Postgres login used by the deployed dashboard backend (run once, offline).

    .venv/Scripts/python -m dashboard.create_reader

Uses DATABASE_URL (owner) from .env, creates or resets role `dashboard_reader` with a random password,
grants SELECT only, forces read-only transactions, and appends DASHBOARD_DATABASE_URL to .env (not printed).
Put that value into Vercel as the project's DATABASE_URL environment variable.
"""
import os, re, secrets
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent


def main():
    env_path = ROOT / ".env"
    load_dotenv(env_path)
    owner = os.environ["DATABASE_URL"]
    pw = secrets.token_urlsafe(24)
    with psycopg.connect(owner, autocommit=True) as c:
        exists = c.execute("SELECT 1 FROM pg_roles WHERE rolname='dashboard_reader'").fetchone()
        stmt = "ALTER ROLE dashboard_reader PASSWORD {}" if exists else "CREATE ROLE dashboard_reader LOGIN PASSWORD {}"
        c.execute(sql.SQL(stmt).format(sql.Literal(pw)))
        c.execute("GRANT USAGE ON SCHEMA public TO dashboard_reader")
        c.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO dashboard_reader")
        c.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO dashboard_reader")
        c.execute("ALTER ROLE dashboard_reader SET default_transaction_read_only = on")
    reader = re.sub(r"^(postgres(?:ql)?://)[^:]+:[^@]+@", lambda m: m.group(1) + "dashboard_reader:" + pw + "@", owner)
    lines = [l for l in env_path.read_text(encoding="utf-8").splitlines() if not l.startswith("DASHBOARD_DATABASE_URL=")]
    env_path.write_text("\n".join(lines) + "\nDASHBOARD_DATABASE_URL=" + reader + "\n", encoding="utf-8")
    print("dashboard_reader ready; DASHBOARD_DATABASE_URL written to .env (not displayed)")


if __name__ == "__main__":
    main()
