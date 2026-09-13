"""灵感 API：记录 / 列表 / 详情 / 修改 / 删除 / AI 重试 / 相关灵感 / 复用档案。

检索（混合搜索）在 W2 实现；MCP 只读访问在 W3 实现。
"""

from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request

from ..config import settings
from ..db import get_pool
from ..schemas import (
    IdeaCreate,
    IdeaListOut,
    IdeaOut,
    IdeaUpdate,
    ReuseTraceEvent,
    ReuseTraceOut,
)
from ..services.ratelimit import capture_limiter, search_limiter
from ..services.search import fetch_related_ideas
from ..services.structuring import enqueue_ai_processing

router = APIRouter(prefix="/ideas", tags=["ideas"])

_BASE_SELECT = """
    SELECT i.*, p.name AS project_name,
           COALESCE(array_agg(t.name) FILTER (WHERE t.name IS NOT NULL), '{}') AS tags
    FROM ideas i
    LEFT JOIN projects p ON p.id = i.project_id
    LEFT JOIN idea_tags it ON it.idea_id = i.id
    LEFT JOIN tags t ON t.id = it.tag_id
"""


def _to_out(row: asyncpg.Record) -> IdeaOut:
    data = dict(row)
    data["tags"] = sorted(data["tags"])
    return IdeaOut.model_validate(data)


@router.post("", status_code=201, response_model=IdeaOut)
async def create_idea(body: IdeaCreate, request: Request):
    # 限流：每条记录都会触发 LLM/Embedding 计费调用（H1）
    client = request.client.host if request.client else "unknown"
    if not capture_limiter.allow(f"web:{client}"):
        raise HTTPException(429, "请求过于频繁，请稍后再试")

    content = body.content.strip()
    if not content:
        raise HTTPException(400, "内容不能为空")
    if len(content) > settings.max_content_length:
        raise HTTPException(400, f"内容超过 {settings.max_content_length} 字符上限，请精简后再保存")

    pool = await get_pool()
    if body.project_id is not None:
        exists = await pool.fetchval("SELECT 1 FROM projects WHERE id = $1", body.project_id)
        if not exists:
            raise HTTPException(404, "项目不存在")

    row = await pool.fetchrow(
        "INSERT INTO ideas (raw_content, project_id, source, created_at) "
        "VALUES ($1, $2, 'web', COALESCE($3, now())) RETURNING id",
        content,
        body.project_id,
        body.captured_at,
    )
    enqueue_ai_processing(row["id"])
    return await get_idea(row["id"])


@router.get("", response_model=IdeaListOut)
async def list_ideas(
    project_id: UUID | None = None,
    tag: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    filters: list[str] = []
    args: list = []
    if project_id is not None:
        args.append(project_id)
        filters.append(f"i.project_id = ${len(args)}")
    if tag:
        args.append(tag)
        filters.append(
            f"EXISTS (SELECT 1 FROM idea_tags it2 JOIN tags t2 ON t2.id = it2.tag_id "
            f"WHERE it2.idea_id = i.id AND t2.name = ${len(args)})"
        )
    if status:
        args.append(status)
        filters.append(f"i.status = ${len(args)}")
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    pool = await get_pool()
    total = await pool.fetchval(f"SELECT COUNT(*) FROM ideas i {where}", *args)

    args.extend([limit, offset])
    rows = await pool.fetch(
        f"{_BASE_SELECT} {where} GROUP BY i.id, p.name "
        f"ORDER BY i.created_at DESC LIMIT ${len(args) - 1} OFFSET ${len(args)}",
        *args,
    )
    return IdeaListOut(items=[_to_out(r) for r in rows], total=total)


@router.get("/{idea_id}", response_model=IdeaOut)
async def get_idea(idea_id: UUID):
    pool = await get_pool()
    row = await pool.fetchrow(f"{_BASE_SELECT} WHERE i.id = $1 GROUP BY i.id, p.name", idea_id)
    if row is None:
        raise HTTPException(404, "灵感不存在")
    return _to_out(row)


@router.patch("/{idea_id}", response_model=IdeaOut)
async def update_idea(idea_id: UUID, body: IdeaUpdate):
    pool = await get_pool()
    exists = await pool.fetchval("SELECT 1 FROM ideas WHERE id = $1", idea_id)
    if not exists:
        raise HTTPException(404, "灵感不存在")

    sets: list[str] = []
    args: list = []
    # model_fields_set 区分「未传」与「显式传 null」（用于清除项目归属）
    fields = body.model_fields_set
    if "project_id" in fields:
        if body.project_id is not None:
            proj = await pool.fetchval("SELECT 1 FROM projects WHERE id = $1", body.project_id)
            if not proj:
                raise HTTPException(404, "项目不存在")
        args.append(body.project_id)
        sets.append(f"project_id = ${len(args)}")
    if "status" in fields and body.status is not None:
        args.append(body.status)
        sets.append(f"status = ${len(args)}")
    if "importance" in fields and body.importance is not None:
        args.append(body.importance)
        sets.append(f"importance = ${len(args)}")
    if "ai_title" in fields and body.ai_title is not None:
        args.append(body.ai_title)
        sets.append(f"ai_title = ${len(args)}")
    if "ai_summary" in fields and body.ai_summary is not None:
        args.append(body.ai_summary)
        sets.append(f"ai_summary = ${len(args)}")

    if sets:
        args.append(idea_id)
        await pool.execute(
            f"UPDATE ideas SET {', '.join(sets)} WHERE id = ${len(args)}", *args
        )
    return await get_idea(idea_id)


@router.delete("/{idea_id}", status_code=204)
async def delete_idea(idea_id: UUID):
    pool = await get_pool()
    result = await pool.execute("DELETE FROM ideas WHERE id = $1", idea_id)
    if result == "DELETE 0":
        raise HTTPException(404, "灵感不存在")


@router.post("/{idea_id}/retry-ai", response_model=IdeaOut)
async def retry_ai(idea_id: UUID):
    pool = await get_pool()
    status = await pool.fetchval("SELECT ai_status FROM ideas WHERE id = $1", idea_id)
    if status is None:
        raise HTTPException(404, "灵感不存在")
    if status not in ("failed", "done"):
        raise HTTPException(409, "AI 正在处理中，请稍候")
    await pool.execute(
        "UPDATE ideas SET ai_status = 'pending', ai_error = NULL WHERE id = $1", idea_id
    )
    enqueue_ai_processing(idea_id)
    return await get_idea(idea_id)


@router.get("/{idea_id}/related", response_model=list[IdeaOut])
async def related_ideas(
    idea_id: UUID, request: Request, limit: int = Query(default=5, ge=1, le=20)
):
    """相关灵感（T1.3，管理面）：向量重查询，目标无 embedding 时返回空列表。

    红线：Web UI 检索不算被 Agent 复用——不得调用 mark_retrieved（会污染复用率
    分子）；日志表只记录 Agent 调用——不得调用 log_call。
    """
    # 限流：向量重查询，与 Web 混合检索共用滑窗（H1）
    client = request.client.host if request.client else "unknown"
    if not search_limiter.allow(f"web:{client}"):
        raise HTTPException(429, "请求过于频繁，请稍后再试")

    pool = await get_pool()
    if not await pool.fetchval("SELECT 1 FROM ideas WHERE id = $1", idea_id):
        raise HTTPException(404, "灵感不存在")
    rows = await fetch_related_ideas(idea_id, limit)
    return [_to_out(r) for r in rows]


@router.get("/{idea_id}/reuse-trace", response_model=ReuseTraceOut)
async def reuse_trace(idea_id: UUID):
    """复用档案（T1.1，管理面）：累计计数 + 命中明细时间线。

    累计值取自 ideas 冗余列（不随日志保留期清理缩水）；
    明细走 agent_call_logs_returned_ids_idx，最多 50 条。
    只读：不写调用日志、不改复用状态。
    """
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT status, retrieved_count, last_retrieved_at FROM ideas WHERE id = $1",
        idea_id,
    )
    if row is None:
        raise HTTPException(404, "灵感不存在")
    events = await pool.fetch(
        "SELECT created_at AS at, agent_name, tool_name "
        "FROM agent_call_logs "
        "WHERE $1 = ANY(returned_idea_ids) "
        "ORDER BY created_at DESC LIMIT 50",
        idea_id,
    )
    return ReuseTraceOut(
        status=row["status"],
        retrieved_count=row["retrieved_count"],
        last_retrieved_at=row["last_retrieved_at"],
        events=[
            ReuseTraceEvent(
                at=e["at"], agent_name=e["agent_name"], tool_name=e["tool_name"]
            )
            for e in events
        ],
    )
