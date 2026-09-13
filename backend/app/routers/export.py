"""全量数据导出（路线图阶段一 P0）：一键导出全部灵感与项目，含原文与向量。

数据主权是产品底线：导出必须完整、机器可读、可随时带走。
格式：单个 JSON 文档（meta + projects + ideas），浏览器直接下载。
流式分批输出，避免全量数据驻留内存（M3）。
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..db import get_pool
from ..services.ratelimit import export_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["export"])

_BATCH = 200

_IDEAS_SQL = """
    SELECT i.*, p.name AS project_name,
           COALESCE(array_agg(t.name) FILTER (WHERE t.name IS NOT NULL), '{}') AS tags
    FROM ideas i
    LEFT JOIN projects p ON p.id = i.project_id
    LEFT JOIN idea_tags it ON it.idea_id = i.id
    LEFT JOIN tags t ON t.id = it.tag_id
    GROUP BY i.id, p.name
    ORDER BY i.created_at
"""


def _parse_embedding(value) -> list[float] | None:
    """asyncpg 对 vector 类型默认返回 '[1,2,3]' 字符串，解析为数组。"""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            logger.warning("导出时发现无法解析的 embedding，按 None 处理")
            return None
    return list(value)


def _idea_doc(i) -> dict:
    return {
        "id": str(i["id"]),
        "raw_content": i["raw_content"],
        "ai": {
            "title": i["ai_title"],
            "summary": i["ai_summary"],
            "maturity": i["ai_maturity"],
            "key_assumption": i["ai_key_assumption"],
            "confidence": i["ai_confidence"],
            "status": i["ai_status"],
            "suggested_project": i["ai_suggested_project"],
        },
        "tags": sorted(i["tags"]),
        "project_id": str(i["project_id"]) if i["project_id"] else None,
        "project_name": i["project_name"],
        "status": i["status"],
        "source": i["source"],
        "importance": i["importance"],
        "embedding": _parse_embedding(i["embedding"]),
        "created_at": i["created_at"].isoformat(),
    }


@router.get("")
async def export_all(request: Request):
    # 限流：全量导出是重操作（H1）
    client = request.client.host if request.client else "unknown"
    if not export_limiter.allow(f"web:{client}"):
        raise HTTPException(429, "请求过于频繁，请稍后再试")

    pool = await get_pool()
    now = datetime.now(timezone.utc)

    async def generate():
        project_rows = await pool.fetch(
            "SELECT id, name, description, created_at FROM projects ORDER BY created_at"
        )
        total_ideas = await pool.fetchval("SELECT COUNT(*) FROM ideas")

        head = {
            "app": "ReMuse 溯游",
            "format_version": 1,
            "exported_at": now.isoformat(),
            "counts": {"projects": len(project_rows), "ideas": total_ideas},
        }
        # 逐段拼接合法 JSON：head 去掉收尾 }，继续拼 projects/ideas 数组
        yield json.dumps(head, ensure_ascii=False)[:-1]
        yield ',"projects":['
        yield ",".join(
            json.dumps(
                {
                    "id": str(p["id"]),
                    "name": p["name"],
                    "description": p["description"],
                    "created_at": p["created_at"].isoformat(),
                },
                ensure_ascii=False,
            )
            for p in project_rows
        )
        yield '],"ideas":['
        first = True
        offset = 0
        while True:
            rows = await pool.fetch(
                f"{_IDEAS_SQL} LIMIT $1 OFFSET $2", _BATCH, offset
            )
            if not rows:
                break
            for row in rows:
                yield ("" if first else ",") + json.dumps(
                    _idea_doc(row), ensure_ascii=False
                )
                first = False
            offset += _BATCH
        yield "]}"

    filename = f"remuse-export-{now:%Y%m%d}.json"
    return StreamingResponse(
        generate(),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
