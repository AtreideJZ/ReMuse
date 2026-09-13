"""统计报表：灵感复用率（北极星指标的度量口径）。

口径（PRD §1.2）：复用率 = 被确认复用的灵感数 / 总灵感数。
「已复用」= status 为 used 或 merged（merged 视为被并入其他方案，同样算复用）；
dropped（已放弃）不计入分母。
"""

from fastapi import APIRouter

from ..db import get_pool

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/reuse")
async def reuse_stats():
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT COUNT(*)::int AS total,
               COUNT(*) FILTER (WHERE status = 'used')::int AS used,
               COUNT(*) FILTER (WHERE status = 'merged')::int AS merged,
               COUNT(*) FILTER (WHERE status = 'retrieved')::int AS retrieved,
               COUNT(*) FILTER (WHERE status = 'captured')::int AS captured
        FROM ideas
        WHERE status != 'dropped'
        """
    )
    total = row["total"]
    reused = row["used"] + row["merged"]
    return {
        "total_ideas": total,
        "used": row["used"],
        "merged": row["merged"],
        "retrieved": row["retrieved"],
        "captured": row["captured"],
        "reuse_rate": round(reused / total, 4) if total else 0.0,
    }
