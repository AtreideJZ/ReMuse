"""标签 API：列表 + 计数，供筛选使用。"""

from fastapi import APIRouter

from ..db import get_pool
from ..schemas import TagListOut

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=TagListOut)
async def list_tags():
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT t.name, COUNT(it.idea_id)::int AS count
        FROM tags t
        JOIN idea_tags it ON it.tag_id = t.id
        GROUP BY t.name
        ORDER BY count DESC, t.name
        """
    )
    return TagListOut(items=[{"name": r["name"], "count": r["count"]} for r in rows])
