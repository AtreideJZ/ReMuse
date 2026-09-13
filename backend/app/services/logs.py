"""Agent 调用日志（F-010）：MCP 与 REST Agent 接口共用的审计写入。

任何 Agent 调用入口（MCP 工具/资源、REST /api/agent/*）都必须记录，
含越权尝试（status='denied'）。日志失败只告警，不影响主流程。
"""

import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from ..db import get_pool

if TYPE_CHECKING:  # 避免与 services.keys 循环导入
    from .keys import Principal

logger = logging.getLogger(__name__)


async def purge_old_logs(retention_days: int) -> int:
    """清理超期调用日志（AC-F010-03）。返回删除行数。"""
    from datetime import timedelta

    pool = await get_pool()
    result = await pool.execute(
        "DELETE FROM agent_call_logs WHERE created_at < now() - $1::interval",
        timedelta(days=retention_days),
    )
    return int(result.split()[-1])


async def log_call(
    principal: "Principal",
    tool: str,
    arguments: dict,
    returned_ids: list[UUID] | None = None,
    status: str = "ok",
    error: str | None = None,
) -> None:
    try:
        pool = await get_pool()
        await pool.execute(
            "INSERT INTO agent_call_logs "
            "(api_key_id, agent_name, tool_name, arguments, returned_idea_ids, status, error) "
            "VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)",
            principal.key_id,
            principal.name,
            tool,
            json.dumps(arguments, ensure_ascii=False, default=str),
            returned_ids or [],
            status,
            error,
        )
    except Exception:
        logger.warning("调用日志写入失败（%s）", tool, exc_info=True)
