"""面向 Web UI 的混合检索（F-005）。无授权限制（用户本人，经管理令牌认证）。"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from ..schemas import IdeaOut
from ..services.ratelimit import search_limiter
from ..services.search import hybrid_search
from .agent import _fetch_ideas_preserve_order

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/ideas", response_model=list[IdeaOut])
async def search_ideas(
    request: Request,
    q: str,
    project_id: UUID | None = None,
    tag: str | None = None,
    days: int | None = Query(default=None, ge=1, description="仅最近 N 天"),
    limit: int = Query(default=20, ge=1, le=100),
):
    # 限流：每次检索触发一次 Embedding 调用（H1）
    client = request.client.host if request.client else "unknown"
    if not search_limiter.allow(f"web:{client}"):
        raise HTTPException(429, "请求过于频繁，请稍后再试")

    ids = await hybrid_search(
        q, project_id=project_id, tag=tag, since_days=days, limit=limit
    )
    return await _fetch_ideas_preserve_order(ids)
