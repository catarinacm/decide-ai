"""Gera as migrations SQL versionadas a partir dos modelos e do seed (rodar só quando o esquema mudar).

    python backend/scripts/build_migrations.py

001_schema.sql            DDL das 9 tabelas no dialeto do Postgres + RLS + gatilho de updated_at
002_seed_restaurants.sql  os 50 restaurantes fictícios de data/restaurants_seed.json (idempotente)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import tables  # noqa: E402,F401

OUT = ROOT / "backend" / "migrations"
DIALECT = postgresql.dialect()


def schema_sql() -> str:
    parts = ["-- 001_schema.sql: esquema do iFood Match (gerado por backend/scripts/build_migrations.py)",
             "-- Tabelas do docx: restaurants, groups, participants, preferences, recommendations, votes,",
             "-- reservations, reviews; mais events para as métricas do funil.", "",
             "CREATE EXTENSION IF NOT EXISTS pgcrypto;", ""]
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=DIALECT)).strip()
        ddl = ddl.replace(f"CREATE TABLE {table.name}", f"CREATE TABLE IF NOT EXISTS {table.name}", 1)
        ddl = ddl.replace("id UUID NOT NULL,", "id UUID DEFAULT gen_random_uuid() NOT NULL,", 1)
        parts.append(ddl + ";\n")
        for idx in table.indexes:
            sql = str(CreateIndex(idx).compile(dialect=DIALECT)).strip()
            sql = sql.replace("CREATE UNIQUE INDEX", "CREATE UNIQUE INDEX IF NOT EXISTS", 1)
            sql = sql.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS", 1)
            parts.append(sql + ";\n")
    fks = ["participants (group_id)", "preferences (participant_id)", "recommendations (group_id, round_number)",
           "votes (group_id, round_number)", "reservations (group_id)", "reviews (reservation_id)"]
    for i, fk in enumerate(fks, start=1):
        parts.append(f"CREATE INDEX IF NOT EXISTS ix_fk_{i} ON {fk};")
    parts += ["",
              "-- groups.winner_recommendation_id -> recommendations.id (referência circular, criada depois).",
              "DO $$ BEGIN",
              "  ALTER TABLE groups ADD CONSTRAINT fk_groups_winner FOREIGN KEY (winner_recommendation_id)",
              "    REFERENCES recommendations (id) ON DELETE SET NULL;",
              "EXCEPTION WHEN duplicate_object THEN NULL; END $$;",
              "",
              "-- updated_at mantido pelo banco em qualquer UPDATE.",
              "CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$",
              "BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;", ""]
    for table in Base.metadata.sorted_tables:
        if "updated_at" in table.c:
            parts.append(f"DROP TRIGGER IF EXISTS trg_{table.name}_updated_at ON {table.name};")
            parts.append(f"CREATE TRIGGER trg_{table.name}_updated_at BEFORE UPDATE ON {table.name} "
                         f"FOR EACH ROW EXECUTE FUNCTION set_updated_at();")
    parts += ["",
              "-- Segurança: o Supabase expõe o schema public pela Data API com a chave anon. O app não usa essa",
              "-- API (só o backend acessa o banco, com o usuário postgres, que ignora RLS). Ativar RLS sem",
              "-- nenhuma policy bloqueia qualquer acesso pela chave anon ou authenticated.", ""]
    for table in Base.metadata.sorted_tables:
        parts.append(f"ALTER TABLE {table.name} ENABLE ROW LEVEL SECURITY;")
    return "\n".join(parts) + "\n"


def lit(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, dict)):
        return "'" + json.dumps(v, ensure_ascii=False).replace("'", "''") + "'::jsonb"
    return "'" + str(v).replace("'", "''") + "'"


def seed_sql() -> str:
    seed = json.loads((ROOT / "data" / "restaurants_seed.json").read_text(encoding="utf-8"))
    cols = ["id", "slug", "name", "cuisine_type", "description", "neighborhood", "city", "latitude", "longitude",
            "avg_price", "dietary_options", "capacity", "ambiences", "opening_hours", "availability_rate", "rating",
            "rating_count", "simulated_benefit", "accepts_reservation", "is_fictional"]
    rows = []
    for r in seed:
        vals = {**r, "cuisine_type": r["cuisine"]}
        rows.append("  (" + ", ".join(lit(vals[c]) if c != "id" else f"'{r['id']}'::uuid" for c in cols) + ")")
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id")
    return ("-- 002_seed_restaurants.sql: 50 restaurantes 100% fictícios (gerado de data/restaurants_seed.json)\n"
            f"INSERT INTO restaurants ({', '.join(cols)}) VALUES\n" + ",\n".join(rows)
            + f"\nON CONFLICT (id) DO UPDATE SET {updates};\n")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    (OUT / "001_schema.sql").write_text(schema_sql(), encoding="utf-8")
    (OUT / "002_seed_restaurants.sql").write_text(seed_sql(), encoding="utf-8")
    print("migrations geradas em", OUT)
