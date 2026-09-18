"""T1.1 复用档案 + T1.3 相关灵感（管理面端点）回归测试。

红线验证：Web UI 的相关灵感检索不得调用 mark_retrieved（不改 status/计数）、
不得写 agent_call_logs；reuse-trace 只读。
需要可访问的数据库（与 test_api.py 同环境）；向量用例直接写库构造，
不依赖外部 Embedding 服务。
"""

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://flash:flash@localhost:5432/flash"
)

pytestmark = pytest.mark.asyncio


async def _db_available() -> bool:
    try:
        import asyncpg

        conn = await asyncpg.connect(DATABASE_URL)
        await conn.close()
        return True
    except Exception:
        return False


@pytest.fixture
async def client():
    if not await _db_available():
        pytest.skip("数据库不可用，跳过 API 集成测试")
    from app.config import settings
    from app.main import app

    settings.admin_token = "test-admin-token"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Admin-Token": "test-admin-token"},
    ) as c:
        yield c


async def test_reuse_trace_never_retrieved(client: AsyncClient):
    """未被检索的灵感：retrieved_count=0、events 为空（T1.1）。"""
    from app.db import get_pool

    pool = await get_pool()
    idea_id = await pool.fetchval(
        "INSERT INTO ideas (raw_content, status, ai_status) "
        "VALUES ($1, 'captured', 'done') RETURNING id",
        f"复用档案测试-{uuid.uuid4().hex[:6]}",
    )
    try:
        resp = await client.get(f"/api/ideas/{idea_id}/reuse-trace")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "captured"
        assert data["retrieved_count"] == 0
        assert data["last_retrieved_at"] is None
        assert data["first_retrieved_at"] is None
        assert data["events"] == []
    finally:
        await pool.execute("DELETE FROM ideas WHERE id = $1", idea_id)


async def test_search_near_miss_degraded(client: AsyncClient, monkeypatch):
    """E7 降级：Embedding 未配置时零结果检索返回 near_miss=None，不报错。"""
    from app.config import settings

    monkeypatch.setattr(settings, "embedding_api_key", "")
    resp = await client.get(
        "/api/search/ideas",
        params={"q": f"绝不存在的词-{uuid.uuid4().hex[:8]}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["near_miss"] is None


async def test_reuse_trace_counters(client: AsyncClient):
    """mark_retrieved 后计数与时间正确；重复检索累计递增；终态不回退。"""
    from app.db import get_pool
    from app.services.reuse import mark_retrieved

    pool = await get_pool()
    idea_id = await pool.fetchval(
        "INSERT INTO ideas (raw_content, status, ai_status) "
        "VALUES ($1, 'captured', 'done') RETURNING id",
        f"复用档案计数-{uuid.uuid4().hex[:6]}",
    )
    used_id = await pool.fetchval(
        "INSERT INTO ideas (raw_content, status, ai_status) "
        "VALUES ($1, 'used', 'done') RETURNING id",
        f"复用档案计数-已复用-{uuid.uuid4().hex[:6]}",
    )
    try:
        # 首次命中：captured → retrieved，计数 1，时间非空
        await mark_retrieved([idea_id])
        data = (await client.get(f"/api/ideas/{idea_id}/reuse-trace")).json()
        assert data["status"] == "retrieved"
        assert data["retrieved_count"] == 1
        assert data["last_retrieved_at"] is not None
        # E3：首次检索时间落库
        assert data["first_retrieved_at"] is not None
        first_at = data["first_retrieved_at"]

        # 重复检索：状态不变，计数累计递增；首次时间不被覆盖
        await mark_retrieved([idea_id])
        data = (await client.get(f"/api/ideas/{idea_id}/reuse-trace")).json()
        assert data["status"] == "retrieved"
        assert data["retrieved_count"] == 2
        assert data["first_retrieved_at"] == first_at

        # used 终态：计数照记，状态不回退
        await mark_retrieved([used_id])
        data = (await client.get(f"/api/ideas/{used_id}/reuse-trace")).json()
        assert data["status"] == "used"
        assert data["retrieved_count"] == 1
        assert data["last_retrieved_at"] is not None
    finally:
        await pool.execute("DELETE FROM ideas WHERE id = ANY($1)", [idea_id, used_id])


async def test_reuse_trace_events(client: AsyncClient):
    """events 明细来自 agent_call_logs（不 join，取冗余 agent_name）。"""
    from app.db import get_pool

    pool = await get_pool()
    idea_id = await pool.fetchval(
        "INSERT INTO ideas (raw_content, status, ai_status) "
        "VALUES ($1, 'captured', 'done') RETURNING id",
        f"复用档案明细-{uuid.uuid4().hex[:6]}",
    )
    log_id = await pool.fetchval(
        "INSERT INTO agent_call_logs (agent_name, tool_name, returned_idea_ids) "
        "VALUES ($1, $2, $3) RETURNING id",
        "测试Agent",
        "search_ideas",
        [idea_id],
    )
    try:
        resp = await client.get(f"/api/ideas/{idea_id}/reuse-trace")
        assert resp.status_code == 200
        events = resp.json()["events"]
        assert len(events) == 1
        assert events[0]["agent_name"] == "测试Agent"
        assert events[0]["tool_name"] == "search_ideas"
        assert events[0]["at"]
    finally:
        await pool.execute("DELETE FROM agent_call_logs WHERE id = $1", log_id)
        await pool.execute("DELETE FROM ideas WHERE id = $1", idea_id)


async def test_related_and_reuse_trace_404(client: AsyncClient):
    """两个新端点对不存在的灵感返回与 get_idea 一致的 404 形态。"""
    missing = uuid.uuid4()
    for suffix in ("reuse-trace", "related"):
        resp = await client.get(f"/api/ideas/{missing}/{suffix}")
        assert resp.status_code == 404
        assert resp.json() == {"detail": "灵感不存在"}


async def test_related_no_embedding_returns_empty(client: AsyncClient):
    """目标灵感无 embedding → 200 空列表，不报错（T1.3 验收）。"""
    from app.db import get_pool

    pool = await get_pool()
    idea_id = await pool.fetchval(
        "INSERT INTO ideas (raw_content, ai_status) VALUES ($1, 'done') RETURNING id",
        f"无向量相关测试-{uuid.uuid4().hex[:6]}",
    )
    try:
        resp = await client.get(f"/api/ideas/{idea_id}/related")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        await pool.execute("DELETE FROM ideas WHERE id = $1", idea_id)


async def test_related_readonly_redlines(client: AsyncClient):
    """红线：调用 related 不改目标与结果集的 status/计数、不写 agent_call_logs。

    向量直接写库（手工构造近邻向量），不依赖外部 Embedding 服务。
    """
    from app.db import get_pool

    pool = await get_pool()
    dim = await pool.fetchval(
        "SELECT atttypmod FROM pg_attribute "
        "WHERE attrelid = 'ideas'::regclass AND attname = 'embedding'"
    )

    def _vec(pairs: dict[int, float]) -> str:
        v = [0.0] * dim
        for i, x in pairs.items():
            v[i] = x
        return "[" + ",".join(map(str, v)) + "]"

    marker = uuid.uuid4().hex[:6]
    target_id = await pool.fetchval(
        "INSERT INTO ideas (raw_content, status, ai_status, embedding) "
        "VALUES ($1, 'captured', 'done', $2::vector) RETURNING id",
        f"相关灵感测试-目标-{marker}",
        _vec({0: 1.0}),
    )
    similar_id = await pool.fetchval(
        "INSERT INTO ideas (raw_content, status, ai_status, embedding) "
        "VALUES ($1, 'captured', 'done', $2::vector) RETURNING id",
        f"相关灵感测试-近邻-{marker}",
        _vec({0: 0.9, 1: 0.1}),
    )
    ids = [target_id, similar_id]
    try:
        logs_before = await pool.fetchval(
            "SELECT COUNT(*) FROM agent_call_logs WHERE $1 = ANY(returned_idea_ids)",
            similar_id,
        )

        resp = await client.get(f"/api/ideas/{target_id}/related", params={"limit": 5})
        assert resp.status_code == 200
        result_ids = [i["id"] for i in resp.json()]
        assert str(target_id) not in result_ids, "结果不应包含目标自身"
        assert str(similar_id) in result_ids, "近邻灵感应被召回"

        # 红线 1：不出现 retrieved，计数也不变
        for iid in ids:
            row = await pool.fetchrow(
                "SELECT status, retrieved_count FROM ideas WHERE id = $1", iid
            )
            assert row["status"] == "captured"
            assert row["retrieved_count"] == 0

        # 红线 2：不写 agent_call_logs
        logs_after = await pool.fetchval(
            "SELECT COUNT(*) FROM agent_call_logs WHERE $1 = ANY(returned_idea_ids)",
            similar_id,
        )
        assert logs_after == logs_before
    finally:
        await pool.execute("DELETE FROM ideas WHERE id = ANY($1)", ids)


async def test_agent_rest_related_unchanged(client: AsyncClient):
    """REST Agent 的 related 重构回归：授权校验、写调用日志行为不变。"""
    from app.db import get_pool
    from app.services.keys import generate_key

    pool = await get_pool()
    token, prefix, key_hash = generate_key()
    key_id = await pool.fetchval(
        "INSERT INTO api_keys (name, prefix, key_hash, scopes) "
        "VALUES ($1, $2, $3, '{read}') RETURNING id",
        f"related-rest-{uuid.uuid4().hex[:6]}",
        prefix,
        key_hash,
    )
    idea_id = await pool.fetchval(
        "INSERT INTO ideas (raw_content, status, ai_status) "
        "VALUES ($1, 'captured', 'done') RETURNING id",
        f"REST相关回归-{uuid.uuid4().hex[:6]}",
    )
    auth = {"Authorization": f"Bearer {token}"}
    try:
        # 无 embedding → 空列表但调用成功
        resp = await client.get(f"/api/agent/ideas/{idea_id}/related", headers=auth)
        assert resp.status_code == 200
        assert resp.json() == []

        # 调用日志落库（Agent 侧红线相反：必须记日志）
        status = await pool.fetchval(
            "SELECT status FROM agent_call_logs "
            "WHERE api_key_id = $1 AND tool_name = 'rest:find_related_ideas' "
            "ORDER BY created_at DESC LIMIT 1",
            key_id,
        )
        assert status == "ok"

        # 不存在的灵感 → 404「无权限或不存在」，不泄露存在性
        resp = await client.get(f"/api/agent/ideas/{uuid.uuid4()}/related", headers=auth)
        assert resp.status_code == 404
        assert "无权限或不存在" in resp.json()["detail"]
    finally:
        await pool.execute("DELETE FROM agent_call_logs WHERE api_key_id = $1", key_id)
        await pool.execute("DELETE FROM api_keys WHERE id = $1", key_id)
        await pool.execute("DELETE FROM ideas WHERE id = $1", idea_id)
