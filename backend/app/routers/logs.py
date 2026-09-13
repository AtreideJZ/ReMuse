"""Agent 调用日志查询（F-010）。面向用户 Web 界面。"""

import json
from datetime import timedelta

from fastapi import APIRouter, Query

from ..db import get_pool

router = APIRouter(prefix="/agent-logs", tags=["agent-logs"])


@router.get("")
async def list_logs(
    agent_name: str | None = None,
    tool_name: str | None = None,
    days: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    filters: list[str] = []
    args: list = []
    if agent_name:
        args.append(agent_name)
        filters.append(f"agent_name = ${len(args)}")
    if tool_name:
        args.append(tool_name)
        filters.append(f"tool_name = ${len(args)}")
    if days:
        args.append(timedelta(days=days))
        filters.append(f"created_at >= now() - ${len(args)}::interval")
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    pool = await get_pool()
    total = await pool.fetchval(f"SELECT COUNT(*) FROM agent_call_logs {where}", *args)
    args.extend([limit, offset])
    rows = await pool.fetch(
        f"SELECT * FROM agent_call_logs {where} "
        f"ORDER BY created_at DESC LIMIT ${len(args) - 1} OFFSET ${len(args)}",
        *args,
    )
    items = [
        {
            "id": str(r["id"]),
            "agent_name": r["agent_name"],
            "tool_name": r["tool_name"],
            # asyncpg 对 jsonb 默认返回 str，解析为对象返回给前端
            "arguments": json.loads(r["arguments"])
            if isinstance(r["arguments"], str)
            else r["arguments"],
            "returned_idea_ids": [str(i) for i in r["returned_idea_ids"]],
            "status": r["status"],
            "error": r["error"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]
    return {"items": items, "total": total}


@router.get("/agents")
async def list_agents():
    """出现过的 agent 名（密钥名），供筛选下拉。"""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT DISTINCT agent_name FROM agent_call_logs ORDER BY agent_name"
    )
    return {"items": [r["agent_name"] for r in rows]}
