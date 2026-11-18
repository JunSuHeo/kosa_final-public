from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from .config import settings


def connect():
    url = settings().database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url, row_factory=dict_row)


def initialize():
    with connect() as c:
        c.execute("SELECT pg_advisory_xact_lock(247315)")
        for migration in sorted((Path(__file__).parent.parent / "migrations").glob("*.sql")):
            c.execute(migration.read_text())
