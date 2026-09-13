"""AI 结构化后台任务：LLM 结构化 + Embedding 回填。

- 记录接口只负责落库并派发任务，不阻塞响应（AC-F001-01）
- 任何一步失败都只影响 AI 派生字段，原文永远可用（AC-F003-02）
- 并发安全：CAS 条件 UPDATE 抢占任务（B4），Semaphore 限制 LLM 并发（S3）
"""

import asyncio
import logging
from uuid import UUID

from ..db import get_pool
from .embedder import get_embedder, to_vector_literal
from .llm import structure_idea

logger = logging.getLogger(__name__)

# 持有任务引用，避免被 GC 提前回收
_bg_tasks: set[asyncio.Task] = set()

# LLM 并发上限：防止批量入队时触发下游限流、耗尽 DB 连接池（S3）
_llm_semaphore = asyncio.Semaphore(4)


def enqueue_ai_processing(idea_id: UUID) -> None:
    task = asyncio.create_task(process_idea(idea_id))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def requeue_unfinished() -> int:
    """服务重启后，把未完成结构化的灵感重新入队。

    重启时本进程没有 in-flight 任务，先把遗留 processing 重置回 pending
    （配合 process_idea 的 CAS 抢占，避免双重处理）。
    """
    pool = await get_pool()
    await pool.execute(
        "UPDATE ideas SET ai_status = 'pending' WHERE ai_status = 'processing'"
    )
    rows = await pool.fetch("SELECT id FROM ideas WHERE ai_status = 'pending'")
    for row in rows:
        enqueue_ai_processing(row["id"])
    return len(rows)


async def backfill_embeddings(batch_size: int = 50) -> int:
    """为缺失向量的灵感补算 Embedding（W2）。

    - 仅在 Embedder 已配置时执行
    - 单行失败不阻断整批；失败行标记 embedding_attempted_at，
      1 小时内不重试，避免坏数据造成死循环（B5）
    - 串行执行即为限流（S5 的批量 embed 留待数据量大后再做）
    """
    embedder = get_embedder()
    if not embedder.configured():
        return 0
    pool = await get_pool()
    done = 0
    while True:
        rows = await pool.fetch(
            """
            SELECT id, raw_content FROM ideas
            WHERE embedding IS NULL
              AND (embedding_attempted_at IS NULL
                   OR embedding_attempted_at < now() - interval '1 hour')
            ORDER BY created_at
            LIMIT $1
            """,
            batch_size,
        )
        if not rows:
            break
        for row in rows:
            try:
                vec = await embedder.embed(row["raw_content"])
                await pool.execute(
                    "UPDATE ideas SET embedding = $2::vector, "
                    "embedding_attempted_at = NULL WHERE id = $1",
                    row["id"],
                    to_vector_literal(vec),
                )
                done += 1
            except Exception:
                logger.warning("回填 embedding 失败（idea %s）", row["id"], exc_info=True)
                await pool.execute(
                    "UPDATE ideas SET embedding_attempted_at = now() WHERE id = $1",
                    row["id"],
                )
    return done


async def process_idea(idea_id: UUID) -> None:
    async with _llm_semaphore:
        pool = await get_pool()
        # CAS 抢占：仅当仍处于 pending 才接管，否则说明已被其他任务处理（B4）
        claimed = await pool.execute(
            "UPDATE ideas SET ai_status = 'processing', ai_error = NULL "
            "WHERE id = $1 AND ai_status = 'pending'",
            idea_id,
        )
        if claimed != "UPDATE 1":
            return
        try:
            row = await pool.fetchrow(
                "SELECT raw_content FROM ideas WHERE id = $1", idea_id
            )
            if row is None:
                return
            content: str = row["raw_content"]

            project_rows = await pool.fetch("SELECT id, name FROM projects")
            projects_by_name = {p["name"]: p["id"] for p in project_rows}

            result = await structure_idea(content, list(projects_by_name))

            # Embedding 失败不影响结构化结果落库
            embedding_literal: str | None = None
            embedder = get_embedder()
            if embedder.configured():
                try:
                    vec = await embedder.embed(content)
                    embedding_literal = to_vector_literal(vec)
                except Exception:
                    logger.warning("embedding 失败（idea %s）", idea_id, exc_info=True)

            suggested = result.get("suggested_project") or None
            confidence = result.get("confidence")
            # 置信度低时不展示建议（AC-F003-03 交由前端按「建议」处理，后端只存原始值）

            await pool.execute(
                """
                UPDATE ideas SET
                    ai_title = $2,
                    ai_summary = $3,
                    ai_maturity = $4,
                    ai_key_assumption = $5,
                    ai_confidence = $6,
                    ai_suggested_project = $7,
                    ai_status = 'done',
                    ai_error = NULL,
                    embedding = COALESCE($8::vector, embedding)
                WHERE id = $1
                """,
                idea_id,
                _as_str(result.get("title"), 200),
                _as_str(result.get("summary"), 500),
                _as_str(result.get("maturity"), 50),
                _as_str(result.get("key_assumption"), 500),
                float(confidence) if isinstance(confidence, (int, float)) else None,
                _as_str(suggested, 200),
                embedding_literal,
            )

            tags = result.get("tags") or []
            if isinstance(tags, list):
                # M4：单条标签截断 50 字、最多 4 条，防异常数据写入
                await _replace_tags(
                    pool,
                    idea_id,
                    [str(t).strip()[:50] for t in tags if str(t).strip()][:4],
                )

            logger.info("AI 结构化完成 idea %s", idea_id)
        except Exception as exc:  # noqa: BLE001 —— 任何失败都降级为可重试状态
            logger.warning("AI 结构化失败 idea %s: %s", idea_id, exc)
            await pool.execute(
                "UPDATE ideas SET ai_status = 'failed', ai_error = $2 WHERE id = $1",
                idea_id,
                str(exc)[:500],
            )


def _as_str(value, max_len: int) -> str | None:
    if value is None:
        return None
    return str(value)[:max_len]


async def _replace_tags(pool, idea_id: UUID, tag_names: list[str]) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM idea_tags WHERE idea_id = $1", idea_id)
            for name in tag_names:
                tag_id = await conn.fetchval(
                    "INSERT INTO tags (name) VALUES ($1) "
                    "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
                    "RETURNING id",
                    name,
                )
                await conn.execute(
                    "INSERT INTO idea_tags (idea_id, tag_id) VALUES ($1, $2) "
                    "ON CONFLICT DO NOTHING",
                    idea_id,
                    tag_id,
                )
