"""Aplica as migrations SQL de backend/migrations/ no Postgres de DATABASE_URL, em ordem e uma vez só.

    python backend/scripts/migrate.py            aplica o que falta
    python backend/scripts/migrate.py --status   mostra o que já foi aplicado e as contagens

Cada arquivo roda numa transação; a tabela schema_migrations guarda o que já foi aplicado.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import psycopg  # noqa: E402

from app.config import settings  # noqa: E402

MIGRATIONS = ROOT / "backend" / "migrations"
TABLES = ["restaurants", "groups", "participants", "preferences", "recommendations", "votes", "reservations",
          "reviews", "events"]


def conninfo() -> str:
    return settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not settings.database_url.startswith("postgresql"):
        print("DATABASE_URL não aponta para um Postgres; nada a fazer (SQLite cria as tabelas sozinho).")
        return 0
    with psycopg.connect(conninfo(), connect_timeout=15) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
                     "filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        conn.execute("ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY")
        conn.commit()
        applied = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations")}

        if "--status" not in sys.argv:
            for f in sorted(MIGRATIONS.glob("*.sql")):
                if f.name in applied:
                    print(f"= {f.name} (já aplicada)")
                    continue
                with conn.transaction():
                    conn.execute(f.read_text(encoding="utf-8"))  # sem parâmetros: aceita vários comandos
                    conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (f.name,))
                print(f"+ {f.name} aplicada")

        for t in TABLES:
            n = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            rls = conn.execute("SELECT relrowsecurity FROM pg_class WHERE relname = %s", (t,)).fetchone()[0]
            print(f"  {t:<16} {n:>5} linha(s)   RLS {'ativo' if rls else 'DESATIVADO'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
