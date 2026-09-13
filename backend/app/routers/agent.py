"""Agent 访问接口（REST 形态，W3 的 MCP Server 复用同一服务层）。

对应 MCP 工具：search_ideas / get_idea / list_recent_ideas /
find_related_ideas / capture_idea / mark_idea_as_used。
默认只读；写入（capture_idea / mark_idea_as_used）需 Key 显式带 write scope（AC-F008-03）。
所有调用（含越权尝试）写入 agent_call_logs（F-010）。
Agent 命中的灵感自动记 retrieved（复用追踪闭环）。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import settings
from ..db import get_pool
from ..schemas import IdeaOut
from ..services.keys import (
    Principal,
    check_project_access,
    get_principal,
    guard_scope,
)
from ..services.logs import log_call
from ..services.ratelimit import capture_limiter, search_limiter
from ..services.reuse import mark_retrieved, mark_used
from ..services.search import fetch_related_ideas, hybrid_search
from ..services.structuring import enqueue_ai_processing
from .ideas import _BASE_SELECT, _to_out

router = APIRouter(prefix="/agent", tags=["agent"])


async def _fetch_ideas_preserve_order(ids: list[UUID]) -> list[IdeaOut]:
    if not ids:
        return []
    pool = await get_pool()
    rows = await pool.fetch(
        f"{_BASE_SELECT} WHERE i.id = ANY($1) GROUP BY i.id, p.name", ids
    )
    by_id = {r["id"]: _to_out(r) for r in rows}
    return [by_id[i] for i in ids if i in by_id]


async def _scoped_idea_row(
    principal: Principal, idea_id: UUID, tool: str, args: dict
):
    """按授权范围读取灵感；失败按「越权/不存在」分别记日志并抛 404。

    对外统一「无权限或不存在」（AC-F009-02 不泄露存在性）；
    对内：越权记 denied，不存在记 error（审计精度）。
    """
    pool = await get_pool()
    row = await pool.fetchrow(
        f"{_BASE_SELECT} "
        "WHERE i.id = $1 "
        "  AND ($2::uuid[] IS NULL OR i.project_id IS NULL OR i.project_id = ANY($2)) "
        "GROUP BY i.id, p.name",
        idea_id,
        principal.project_ids,
    )
    if row is None:
        exists = await pool.fetchval("SELECT 1 FROM ideas WHERE id = $1", idea_id)
        if exists:
            await log_call(principal, tool, args, status="denied", error="越权访问")
        else:
            await log_call(principal, tool, args, status="error", error="不存在")
        raise HTTPException(404, "无权限或不存在")
    return row


async def _ensure_project_exists(project_id: UUID | None) -> None:
    """Agent 写入时校验项目存在性（FK 违约会是 500，先显式 404）。"""
    if project_id is None:
        return
    pool = await get_pool()
    if not await pool.fetchval("SELECT 1 FROM projects WHERE id = $1", project_id):
        raise HTTPException(404, "项目不存在")


class AgentCaptureIn(BaseModel):
    content: str = Field(min_length=1, max_length=settings.max_content_length)
    project_id: UUID | None = None


class AgentUsedIn(BaseModel):
    note: str = Field(default="", max_length=500)


@router.get("/ideas/search", response_model=list[IdeaOut])
async def agent_search(
    query: str,
    project_id: UUID | None = None,
    limit: int = Query(default=5, ge=1, le=50),
    principal: Principal = Depends(get_principal),
):
    args = {"query": query, "project_id": project_id, "limit": limit}
    await guard_scope(principal, "read", tool="rest:search_ideas", arguments=args)
    await check_project_access(
        principal, project_id, tool="rest:search_ideas", arguments=args
    )
    # 限流：每次检索触发一次 Embedding 调用（H1）
    if not search_limiter.allow(f"agent:{principal.key_id}"):
        raise HTTPException(429, "请求过于频繁，请稍后再试")
    ids = await hybrid_search(
        query,
        project_id=project_id,
        limit=limit,
        allowed_project_ids=principal.project_ids,
    )
    await mark_retrieved(ids)
    await log_call(principal, "rest:search_ideas", args, ids)
    return await _fetch_ideas_preserve_order(ids)


@router.get("/ideas/recent", response_model=list[IdeaOut])
async def agent_recent(
    project_id: UUID | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    principal: Principal = Depends(get_principal),
):
    args = {"project_id": project_id, "limit": limit}
    await guard_scope(principal, "read", tool="rest:list_recent_ideas", arguments=args)
    await check_project_access(
        principal, project_id, tool="rest:list_recent_ideas", arguments=args
    )
    pool = await get_pool()
    rows = await pool.fetch(
        f"{_BASE_SELECT} "
        "WHERE ($1::uuid IS NULL OR i.project_id = $1) "
        "  AND ($2::uuid[] IS NULL OR i.project_id IS NULL OR i.project_id = ANY($2)) "
        "GROUP BY i.id, p.name ORDER BY i.created_at DESC LIMIT $3",
        project_id,
        principal.project_ids,
        limit,
    )
    ideas = [_to_out(r) for r in rows]
    await mark_retrieved([i.id for i in ideas])
    await log_call(
        principal, "rest:list_recent_ideas", args, [i.id for i in ideas]
    )
    return ideas


@router.get("/ideas/{idea_id}", response_model=IdeaOut)
async def agent_get_idea(idea_id: UUID, principal: Principal = Depends(get_principal)):
    args = {"idea_id": idea_id}
    await guard_scope(principal, "read", tool="rest:get_idea", arguments=args)
    row = await _scoped_idea_row(principal, idea_id, "rest:get_idea", args)
    await mark_retrieved([idea_id])
    await log_call(principal, "rest:get_idea", args, [idea_id])
    return _to_out(row)


@router.get("/ideas/{idea_id}/related", response_model=list[IdeaOut])
async def agent_related_ideas(
    idea_id: UUID,
    limit: int = Query(default=5, ge=1, le=20),
    principal: Principal = Depends(get_principal),
):
    args = {"idea_id": idea_id, "limit": limit}
    await guard_scope(principal, "read", tool="rest:find_related_ideas", arguments=args)
    # 目标灵感本身的存在性与授权校验（与 get_idea 同语义，不泄露存在性）
    await _scoped_idea_row(principal, idea_id, "rest:find_related_ideas", args)

    rows = await fetch_related_ideas(idea_id, limit, principal.project_ids)
    ideas = [_to_out(r) for r in rows]
    await mark_retrieved([i.id for i in ideas])
    await log_call(
        principal, "rest:find_related_ideas", args, [i.id for i in ideas]
    )
    return ideas


@router.post("/ideas", status_code=201, response_model=IdeaOut)
async def agent_capture(
    body: AgentCaptureIn, principal: Principal = Depends(get_principal)
):
    args = {
        "content": body.content[:100] + ("..." if len(body.content) > 100 else ""),
        "project_id": body.project_id,
    }
    await guard_scope(principal, "write", tool="rest:capture_idea", arguments=args)
    await check_project_access(
        principal, body.project_id, tool="rest:capture_idea", arguments=args
    )
    await _ensure_project_exists(body.project_id)
    # 限流：每条记录触发 LLM/Embedding 计费调用（H1）
    if not capture_limiter.allow(f"agent:{principal.key_id}"):
        raise HTTPException(429, "请求过于频繁，请稍后再试")
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "内容不能为空")

    pool = await get_pool()
    row = await pool.fetchrow(
        "INSERT INTO ideas (raw_content, project_id, source) VALUES ($1, $2, 'mcp') RETURNING id",
        content,
        body.project_id,
    )
    enqueue_ai_processing(row["id"])
    await log_call(principal, "rest:capture_idea", args, [row["id"]])
    return await agent_get_idea(row["id"], principal)


@router.post("/ideas/{idea_id}/used")
async def agent_mark_used(
    idea_id: UUID, body: AgentUsedIn, principal: Principal = Depends(get_principal)
):
    """回写复用确认（F-018）：Agent 实际使用某条灵感后调用，用于复用率与归因统计。"""
    args = {"idea_id": idea_id, "note": body.note}
    await guard_scope(principal, "write", tool="rest:mark_idea_as_used", arguments=args)
    await _scoped_idea_row(principal, idea_id, "rest:mark_idea_as_used", args)

    status = await mark_used(idea_id)
    await log_call(principal, "rest:mark_idea_as_used", args, [idea_id])
    return {"idea_id": str(idea_id), "status": status, "message": "已记录复用"}
