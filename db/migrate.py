"""демонстрирует: версионируемый идемпотентный раннер SQL-миграций (up/down).

Использование:
    python migrate.py up      # применить все неприменённые *.up.sql по порядку
    python migrate.py down    # откатить последнюю применённую миграцию (*.down.sql)

Подключение — от имени суперпользователя (DATABASE_URL), т.к. миграции создают роль и включают RLS.
"""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DATABASE_URL = os.environ["DATABASE_URL"]          # postgresql://postgres:...@db:5432/ai_support
APP_PASSWORD = os.environ.get("POSTGRES_APP_PASSWORD", "app_secret")


def render(sql: str) -> str:
    """Подстановка секретов в миграции (сейчас — только пароль роли приложения)."""
    return sql.replace("__APP_PASSWORD__", APP_PASSWORD)


async def main() -> None:
    direction = sys.argv[1] if len(sys.argv) > 1 else "up"
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz DEFAULT now())"
        )
        applied = {r["name"] for r in await conn.fetch("SELECT name FROM schema_migrations")}

        if direction == "up":
            files = sorted(p for p in MIGRATIONS_DIR.glob("*.sql") if not p.name.endswith(".down.sql"))
            for path in files:
                if path.name in applied:
                    continue
                print(f"applying {path.name} ...")
                await conn.execute(render(path.read_text(encoding="utf-8")))
                await conn.execute("INSERT INTO schema_migrations (name) VALUES ($1)", path.name)
                print(f"applied  {path.name}")
        elif direction == "down":
            downs = {p.name.removesuffix(".down.sql"): p for p in MIGRATIONS_DIR.glob("*.down.sql")}
            last = sorted(n for n in applied if n in [f"{b}.up.sql" for b in downs])
            if not last:
                print("nothing to roll back")
                return
            name = last[-1]
            base = name.removesuffix(".up.sql")
            print(f"rolling back {name} ...")
            await conn.execute(render(downs[base].read_text(encoding="utf-8")))
            await conn.execute("DELETE FROM schema_migrations WHERE name = $1", name)
            print(f"rolled back {name}")
        else:
            sys.exit(f"unknown direction: {direction}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
