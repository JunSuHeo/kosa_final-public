from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from .config import settings


def connect():
    url = settings().database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url, row_factory=dict_row)


def initialize(database_url=None):
    with psycopg.connect(database_url, row_factory=dict_row) if database_url else connect() as c:
        c.execute("SELECT pg_advisory_xact_lock(247315)")
        c.execute('CREATE TABLE IF NOT EXISTS studio_schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())')
        for migration in sorted((Path(__file__).parent.parent / "migrations").glob("*.sql")):
            if not c.execute('SELECT 1 FROM studio_schema_migrations WHERE name=%s', (migration.name,)).fetchone():
                c.execute(migration.read_text())
                c.execute('INSERT INTO studio_schema_migrations(name) VALUES (%s)', (migration.name,))
        from .accounts import seed_policy
        seed_policy(c)


if __name__ == '__main__':
    initialize()
