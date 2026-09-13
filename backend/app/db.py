import asyncio

import asyncpg

from .config import settings

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def create_pool() -> asyncpg.Pool:
    """加锁双重检查，避免并发首请求创建多个连接池。"""
    global _pool
    async with _pool_lock:
        if _pool is None:
            _pool = await asyncpg.create_pool(
                dsn=settings.database_url, min_size=1, max_size=10
            )
    return _pool


async def close_pool() -> None:
    global _pool
    async with _pool_lock:
        if _pool is not None:
            await _pool.close()
            _pool = None


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        await create_pool()
    assert _pool is not None
    return _pool
