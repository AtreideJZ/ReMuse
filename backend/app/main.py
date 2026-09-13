import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .db import close_pool, create_pool, get_pool
from .routers import agent, export, ideas, keys, logs, projects, search, stats, tags
from .services.admin_auth import AdminAuthMiddleware
from .services.structuring import backfill_embeddings, requeue_unfinished

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()
    # 重启后把卡在 pending/processing 的灵感重新入队
    await requeue_unfinished()
    # 调用日志超期清理（AC-F010-03）
    from .config import settings
    from .services.logs import purge_old_logs

    purged = await purge_old_logs(settings.agent_log_retention_days)
    if purged:
        logger.info("清理超期调用日志：%d 条", purged)
    # 缺失向量后台回填（W2；未配置 Embedding 时自动跳过）
    async def _backfill():
        n = await backfill_embeddings()
        if n:
            logger.info("回填 embedding 完成：%d 条", n)

    task = asyncio.create_task(_backfill())
    try:
        yield
    finally:
        # 取消后必须等任务真正结束再关连接池，否则连接可能未归还
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        await close_pool()


app = FastAPI(title="ReMuse 溯游 API", lifespan=lifespan)


@app.exception_handler(PermissionError)
async def _permission_error_handler(request, exc):
    """services.keys 的授权校验抛 PermissionError，REST 侧统一映射为 403。"""
    from fastapi.responses import JSONResponse

    return JSONResponse({"detail": str(exc)}, status_code=403)

# 中间件（Starlette 后添加者先执行 = 越靠下越外层）：
# CORS 最外层（预检不带凭据，需先于认证处理）→ 管理面认证 → 安全响应头
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全响应头（H2，API 侧）。Web UI 的同类头由 frontend/next.config.ts 输出。"""

    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        from .config import settings

        if settings.enable_hsts:
            resp.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains; preload",
            )
        return resp


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AdminAuthMiddleware)

# 生产环境前端经 Next.js rewrite 同源访问；CORS 仅为本地开发便利（收紧到实际需要的方法与头）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
)

app.include_router(agent.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(ideas.router, prefix="/api")
app.include_router(keys.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(tags.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
