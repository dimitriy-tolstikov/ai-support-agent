"""демонстрирует: пул asyncpg и включение RLS на каждом запросе через SET LOCAL app.user_id."""
from contextlib import asynccontextmanager

import asyncpg

from .config import settings

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)


async def close_pool() -> None:
    if _pool:
        await _pool.close()


def pool() -> asyncpg.Pool:
    assert _pool is not None, "db pool not initialized"
    return _pool


@asynccontextmanager
async def user_conn(user_id: str | None = None):
    """Соединение в транзакции с установленным app.user_id — RLS-политики видят только его строки."""
    async with pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.user_id', $1, true)", user_id or settings.demo_user_id
            )
            yield conn
