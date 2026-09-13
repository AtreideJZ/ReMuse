"""混合检索（F-005）：中文全文排序 + 向量余弦 + RRF 融合，支持元数据过滤。

- 关键词侧：tsv @@ plainto_tsquery + ts_rank（精确术语召回的保障，AC-F005-02）
- 向量侧：embedding <=> query（语义召回的保障，AC-F005-01）
- 融合：RRF(k=60)，任一侧面命中即可进入结果
- 过滤（项目/标签/时间）在排序之前应用（AC-F005-03）
- Embedding 未配置时降级为纯关键词检索

另含 fetch_related_ideas（T1.3）：MCP / REST / 管理面共用的相关灵感纯查询。
"""

from datetime import timedelta
from uuid import UUID

from ..config import settings
from ..db import get_pool
from .embedder import get_embedder, to_vector_literal

_RRF_K = 60
# 单侧候选集大小，融合前各取这么多
_SIDE_LIMIT = 50


async def hybrid_search(
    query: str,
    *,
    project_id: UUID | None = None,
    tag: str | None = None,
    since_days: int | None = None,
    limit: int = 20,
    allowed_project_ids: list[UUID] | None = None,
) -> list[UUID]:
    """返回按相关性排序的 idea id 列表。

    allowed_project_ids 为 None 表示不限制（用户 UI）；
    为列表时表示 Agent Key 的授权范围（F-009，含「无项目」的个人全局灵感）。
    """
    query = query.strip()
    if not query:
        return []

    # 查询向量化失败/未配置 → 仅关键词侧
    vector_literal: str | None = None
    embedder = get_embedder()
    if embedder.configured():
        try:
            vector_literal = to_vector_literal(await embedder.embed(query))
        except Exception:
            vector_literal = None

    # $1 查询文本；$2 项目；$3 标签；$4 最早时间；$5 授权范围；$6 查询向量；$7 limit
    args: list = [
        query,
        project_id,
        tag,
        timedelta(days=since_days) if since_days else None,
        allowed_project_ids,
        vector_literal,
        limit,
    ]

    vec_cte = (
        """
        vec AS (
            SELECT i.id,
                   ROW_NUMBER() OVER (ORDER BY i.embedding <=> $6::vector) AS pos
            FROM ideas i
            WHERE i.id IN (SELECT id FROM filtered)
              AND i.embedding IS NOT NULL
            ORDER BY i.embedding <=> $6::vector
            LIMIT %d
        )
        """
        % _SIDE_LIMIT
        if vector_literal
        # 无向量侧时退化为空集；引用 $6 仅为让 asyncpg 预处理时能推断参数类型
        else "vec AS (SELECT NULL::uuid AS id, 1::bigint AS pos WHERE $6::text IS NOT NULL AND false)"
    )

    sql = f"""
        WITH filtered AS (
            SELECT i.id
            FROM ideas i
            WHERE ($2::uuid IS NULL OR i.project_id = $2)
              AND ($3::text IS NULL OR EXISTS (
                    SELECT 1 FROM idea_tags it JOIN tags t ON t.id = it.tag_id
                    WHERE it.idea_id = i.id AND t.name = $3))
              AND ($4::interval IS NULL OR i.created_at >= now() - $4::interval)
              AND ($5::uuid[] IS NULL OR i.project_id IS NULL OR i.project_id = ANY($5))
        ),
        kw AS (
            SELECT i.id,
                   ROW_NUMBER() OVER (
                       ORDER BY ts_rank(i.tsv, plainto_tsquery('chinese_zh', $1)) DESC
                   ) AS pos
            FROM ideas i
            WHERE i.id IN (SELECT id FROM filtered)
              AND i.tsv @@ plainto_tsquery('chinese_zh', $1)
            ORDER BY ts_rank(i.tsv, plainto_tsquery('chinese_zh', $1)) DESC
            LIMIT {_SIDE_LIMIT}
        ),
        {vec_cte}
        SELECT COALESCE(kw.id, vec.id) AS id,
               COALESCE(1.0 / ({_RRF_K} + kw.pos), 0)
               + COALESCE(1.0 / ({_RRF_K} + vec.pos), 0) AS score
        FROM kw
        FULL OUTER JOIN vec ON vec.id = kw.id
        ORDER BY score DESC
        LIMIT $7
    """

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # 小数据量下让 IVFFlat 扫全部列表，近似精确召回；数据量大后再调小
            await conn.execute("SET LOCAL ivfflat.probes = 100")
            rows = await conn.fetch(sql, *args)
    return [r["id"] for r in rows]


async def fetch_related_ideas(
    idea_id: UUID,
    limit: int,
    allowed_project_ids: list[UUID] | None = None,
) -> list:
    """相关灵感（T1.3）：按 embedding 余弦距离取最近邻，返回 _BASE_SELECT 形态的行。

    纯查询：不写调用日志、不做复用状态迁移（由调用方按需处理）。
    目标灵感无 embedding 时返回空列表（EXISTS 守卫）。
    allowed_project_ids 为 None 表示不限制（管理面）；
    为列表时表示 Agent Key 的授权范围（F-009，含「无项目」的个人全局灵感）。
    """
    # 函数内延迟导入：routers.ideas 的 related 端点也调用本函数，顶层导入会循环
    from ..routers.ideas import _BASE_SELECT

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # 与 hybrid_search 一致：小数据量下近似精确召回
            await conn.execute("SET LOCAL ivfflat.probes = 100")
            rows = await conn.fetch(
                f"{_BASE_SELECT} "
                "WHERE i.id != $1 "
                "  AND i.embedding IS NOT NULL "
                "  AND ($2::uuid[] IS NULL OR i.project_id IS NULL OR i.project_id = ANY($2)) "
                "  AND EXISTS (SELECT 1 FROM ideas s WHERE s.id = $1 AND s.embedding IS NOT NULL) "
                "GROUP BY i.id, p.name "
                "ORDER BY i.embedding <=> (SELECT embedding FROM ideas WHERE id = $1) "
                "LIMIT $3",
                idea_id,
                allowed_project_ids,
                limit,
            )
    return rows
