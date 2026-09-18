"""面向 Web UI 的混合检索（F-005）。无授权限制（用户本人，经管理令牌认证）。"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from ..schemas import IdeaOut, SearchIdeaListOut
from ..services.ratelimit import search_limiter
from ..services.search import fetch_near_miss, hybrid_search
from .agent import _fetch_ideas_preserve_order
from .ideas import _to_out

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/ideas", response_model=SearchIdeaListOut)
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
    items = await _fetch_ideas_preserve_order(ids)
    # E7：零结果时补一个无阈值向量近邻，把死路变成活路；
    # Embedding 未配置/失败时 near_miss 为 None，前端退回原零结果态
    near_miss: IdeaOut | None = None
    if not items:
        rows = await fetch_near_miss(q)
        if rows:
            near_miss = _to_out(rows[0])
    return SearchIdeaListOut(items=items, near_miss=near_miss)
