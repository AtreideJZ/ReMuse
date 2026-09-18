"""复用追踪（路线图阶段一 P0 闭环）：Agent 命中自动记录 + 复用确认。

状态机：captured → retrieved（Agent 检索/读取命中）→ used（确认复用）
       merged（并入其他方案，视为复用的终态之一，不回退）
"""

from uuid import UUID

from ..db import get_pool


async def mark_retrieved(ids: list[UUID]) -> None:
    """Agent 检索/读取命中的灵感：captured → retrieved，并累计检索计数（T1.1）。

    只在 Agent 接口（MCP/REST）命中时调用，Web UI 检索不算「被 Agent 复用」；
    used/merged/dropped 状态不回退。
    状态迁移仍限定 captured（保持原语义）；计数对所有命中 id 无条件递增，
    保证重复检索也计入 retrieved_count。
    """
    if not ids:
        return
    pool = await get_pool()
    await pool.execute(
        "UPDATE ideas SET status = 'retrieved' "
        "WHERE id = ANY($1) AND status = 'captured'",
        ids,
    )
    await pool.execute(
        "UPDATE ideas SET retrieved_count = retrieved_count + 1, "
        "last_retrieved_at = now(), "
        # 首次检索时间只写一次（E3 沉睡叙事的真实数据源）
        "first_retrieved_at = COALESCE(first_retrieved_at, now()) "
        "WHERE id = ANY($1)",
        ids,
    )


async def mark_used(idea_id: UUID) -> str:
    """确认复用：状态置为 used（merged 为更高优先级的复用终态，不回退）。

    返回更新后的状态。
    """
    pool = await get_pool()
    await pool.execute(
        "UPDATE ideas SET status = 'used' WHERE id = $1 AND status != 'merged'",
        idea_id,
    )
    return await pool.fetchval("SELECT status FROM ideas WHERE id = $1", idea_id)
