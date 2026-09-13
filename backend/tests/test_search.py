"""W2 混合检索回归（AC-F005）。

需要真实 Embedding 服务（source ../.env 后运行）；未配置时跳过。
测试数据直接写库 + backfill 补向量，不触发 LLM 结构化以控制成本。
"""

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

TARGET_SEMANTIC = "做一个根据考试日期自动规划复习的Agent（测试）"
TARGET_KEYWORD = "pgvector 的 IVFFlat 索引用法（测试）"
FILLERS = [
    "每周自动生成下周三件最重要的事（测试）",
    "语音一句话记账的 App（测试）",
    "旅行规划：输入预算和天数输出行程（测试）",
    "把 Agent 对话自动提炼成决策日志（测试）",
]


async def _ctx():
    from app.config import settings
    from app.db import get_pool
    from app.main import app

    if not settings.embedding_api_key:
        pytest.skip("未配置 EMBEDDING_API_KEY，跳过检索测试")
    settings.admin_token = "test-admin-token"
    pool = await get_pool()
    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    return pool, client


@pytest.fixture
async def seeded():
    pool, client = await _ctx()

    pid = await pool.fetchval(
        "INSERT INTO projects (name) VALUES ($1) RETURNING id",
        f"检索测试项目-{uuid.uuid4().hex[:6]}",
    )
    target_id = await pool.fetchval(
        "INSERT INTO ideas (raw_content, project_id, ai_status) VALUES ($1, $2, 'done') RETURNING id",
        TARGET_SEMANTIC,
        pid,
    )
    kw_id = await pool.fetchval(
        "INSERT INTO ideas (raw_content, project_id, ai_status) VALUES ($1, $2, 'done') RETURNING id",
        TARGET_KEYWORD,
        pid,
    )
    filler_ids = []
    for content in FILLERS:
        fid = await pool.fetchval(
            "INSERT INTO ideas (raw_content, ai_status) VALUES ($1, 'done') RETURNING id",
            content,
        )
        filler_ids.append(fid)

    from app.services.structuring import backfill_embeddings

    for _ in range(3):
        await backfill_embeddings()
        missing = await pool.fetchval(
            "SELECT COUNT(*) FROM ideas WHERE id = ANY($1) AND embedding IS NULL",
            [target_id, kw_id, *filler_ids],
        )
        if missing == 0:
            break
    else:
        pytest.fail("embedding 回填失败")

    yield client, pid, target_id, kw_id

    # 清理
    await pool.execute("DELETE FROM projects WHERE id = $1", pid)
    await pool.execute("DELETE FROM ideas WHERE id = ANY($1)", [target_id, kw_id, *filler_ids])
    await client.aclose()


async def test_semantic_recall(seeded):
    """AC-F005-01：语义查询「学生学习计划」，目标进前 5。"""
    client, _, target_id, _ = seeded
    resp = await client.get("/api/search/ideas", params={"q": "学生学习计划"})
    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()]
    assert str(target_id) in ids[:5], f"目标未进前 5: {ids[:5]}"


async def test_keyword_exact(seeded):
    """AC-F005-02：精确术语「pgvector」排第 1。"""
    client, _, _, kw_id = seeded
    resp = await client.get("/api/search/ideas", params={"q": "pgvector"})
    ids = [i["id"] for i in resp.json()]
    assert ids and ids[0] == str(kw_id)


async def test_filter_combination(seeded):
    """AC-F005-03：项目 + 时间过滤同时生效。"""
    client, pid, target_id, kw_id = seeded
    resp = await client.get(
        "/api/search/ideas",
        params={"q": "规划", "project_id": str(pid), "days": 7},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert items, "过滤后应有结果"
    assert all(i["project_id"] == str(pid) for i in items)

    # 换一个无关联项目，结果不应包含本项目灵感
    from app.db import get_pool

    pool = await get_pool()
    other_pid = await pool.fetchval(
        "INSERT INTO projects (name) VALUES ($1) RETURNING id",
        f"无关项目-{uuid.uuid4().hex[:6]}",
    )
    try:
        resp = await client.get(
            "/api/search/ideas",
            params={"q": "规划", "project_id": str(other_pid), "days": 7},
        )
        assert str(target_id) not in [i["id"] for i in resp.json()]
        assert str(kw_id) not in [i["id"] for i in resp.json()]
    finally:
        await pool.execute("DELETE FROM projects WHERE id = $1", other_pid)
