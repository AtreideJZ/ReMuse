"""W4 发布验收补充用例：此前未覆盖的 AC 缺口。

- AC-F001-03 超长内容拒绝
- /api/health、/api/tags
- retry-ai 状态冲突 409
- AC-F011-02 创建 Key 默认只读
- AC-F010-03 日志保留期清理
- AC-F003-01 AI 正常结构化（需真实 LLM，未配置跳过）
- 复用率统计口径
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    from app.config import settings
    from app.main import app

    settings.admin_token = "test-admin-token"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Admin-Token": "test-admin-token"},
    ) as c:
        yield c


async def test_health(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_overlong_content_rejected(client: AsyncClient):
    """AC-F001-03：超过 10000 字符明确拒绝（Pydantic 422 或路由 400）。"""
    resp = await client.post("/api/ideas", json={"content": "长" * 10001})
    assert resp.status_code in (400, 422)


async def test_retry_conflict_returns_409(client: AsyncClient):
    """AI 处理中（非 failed/done）时重试 → 409，而非混淆语义的 404。"""
    resp = await client.post("/api/ideas", json={"content": "409 语义测试灵感"})
    idea_id = resp.json()["id"]
    try:
        # 新建灵感处于 pending/processing，立即重试应 409
        resp = await client.post(f"/api/ideas/{idea_id}/retry-ai")
        assert resp.status_code == 409
        # 不存在的灵感 → 404
        resp = await client.post(f"/api/ideas/{uuid.uuid4()}/retry-ai")
        assert resp.status_code == 404
    finally:
        await client.delete(f"/api/ideas/{idea_id}")


async def test_key_defaults_to_readonly(client: AsyncClient):
    """AC-F011-02：创建时未显式指定 scopes → 默认只读。"""
    resp = await client.post(
        "/api/keys", json={"name": f"默认scope-{uuid.uuid4().hex[:6]}"}
    )
    assert resp.status_code == 201
    key = resp.json()
    assert key["scopes"] == ["read"]
    await client.post(f"/api/keys/{key['id']}/revoke")


async def test_log_retention_purge(client: AsyncClient):
    """AC-F010-03：超期日志被清理，期内日志保留。"""
    from app.db import get_pool
    from app.services.logs import purge_old_logs

    pool = await get_pool()
    marker_old = f"旧日志-{uuid.uuid4().hex[:6]}"
    marker_new = f"新日志-{uuid.uuid4().hex[:6]}"
    await pool.execute(
        "INSERT INTO agent_call_logs (agent_name, tool_name, created_at) "
        "VALUES ($1, 'test', now() - interval '100 days')",
        marker_old,
    )
    await pool.execute(
        "INSERT INTO agent_call_logs (agent_name, tool_name) VALUES ($1, 'test')",
        marker_new,
    )
    try:
        purged = await purge_old_logs(90)
        assert purged >= 1
        remaining_old = await pool.fetchval(
            "SELECT COUNT(*) FROM agent_call_logs WHERE agent_name = $1", marker_old
        )
        remaining_new = await pool.fetchval(
            "SELECT COUNT(*) FROM agent_call_logs WHERE agent_name = $1", marker_new
        )
        assert remaining_old == 0
        assert remaining_new == 1
    finally:
        await pool.execute(
            "DELETE FROM agent_call_logs WHERE agent_name = ANY($1)",
            [marker_old, marker_new],
        )


async def test_tags_endpoint(client: AsyncClient):
    from app.db import get_pool

    pool = await get_pool()
    idea_id = await pool.fetchval(
        "INSERT INTO ideas (raw_content, ai_status) VALUES ($1, 'done') RETURNING id",
        "标签接口测试灵感",
    )
    tag_id = await pool.fetchval(
        "INSERT INTO tags (name) VALUES ($1) ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
        f"测试标签-{uuid.uuid4().hex[:6]}",
    )
    tag_name = await pool.fetchval("SELECT name FROM tags WHERE id = $1", tag_id)
    await pool.execute(
        "INSERT INTO idea_tags (idea_id, tag_id) VALUES ($1, $2)", idea_id, tag_id
    )
    try:
        resp = await client.get("/api/tags")
        assert resp.status_code == 200
        items = resp.json()["items"]
        hit = next((t for t in items if t["name"] == tag_name), None)
        assert hit is not None and hit["count"] >= 1
    finally:
        await pool.execute("DELETE FROM ideas WHERE id = $1", idea_id)
        await pool.execute("DELETE FROM tags WHERE id = $1", tag_id)


async def test_ai_success_path(client: AsyncClient):
    """AC-F003-01：真实 LLM 下结构化成功，各字段带 AI 推断产出。"""
    import asyncio

    from app.config import settings

    if not settings.llm_api_key:
        pytest.skip("未配置 LLM_API_KEY")

    resp = await client.post(
        "/api/ideas", json={"content": "做一个帮独立开发者管理待办事项的 Agent"}
    )
    idea_id = resp.json()["id"]
    try:
        for _ in range(40):
            await asyncio.sleep(0.5)
            resp = await client.get(f"/api/ideas/{idea_id}")
            if resp.json()["ai_status"] in ("done", "failed"):
                break
        idea = resp.json()
        assert idea["ai_status"] == "done", f"AI 处理未成功: {idea['ai_error']}"
        assert idea["ai_title"]
        assert idea["ai_summary"]
        assert isinstance(idea["tags"], list) and len(idea["tags"]) >= 1
        # 原文永不被改动
        assert idea["raw_content"] == "做一个帮独立开发者管理待办事项的 Agent"
    finally:
        await client.delete(f"/api/ideas/{idea_id}")


async def test_export_all(client: AsyncClient):
    """全量导出：结构完整、含原文与向量、带下载头（数据主权 P0）。

    自备数据（try/finally 清理），不依赖库中既有内容——空库（如 CI）也能跑。
    """
    marker = f"导出测试-{uuid.uuid4().hex[:8]}"
    resp = await client.post("/api/ideas", json={"content": marker})
    assert resp.status_code == 201
    idea_id = resp.json()["id"]
    try:
        resp = await client.get("/api/export")
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")

        doc = resp.json()
        assert doc["app"] == "ReMuse 溯游"
        assert doc["format_version"] == 1
        assert doc["counts"]["ideas"] == len(doc["ideas"])
        assert doc["counts"]["projects"] == len(doc["projects"])

        ideas = doc["ideas"]
        assert ideas, "导出应包含灵感"
        sample = next(i for i in ideas if i["id"] == idea_id)
        assert sample["raw_content"] == marker, "导出必须含原文"
        assert "ai" in sample and "tags" in sample and "embedding" in sample

        # 向量断言依赖真实 Embedding 服务（未配置时跳过，与 test_search 同一约定）
        from app.config import settings

        if settings.embedding_api_key:
            with_vec = [i for i in ideas if i["embedding"] is not None]
            assert with_vec, "至少部分灵感应含向量"
            assert isinstance(with_vec[0]["embedding"], list) and len(with_vec[0]["embedding"]) > 0
    finally:
        await client.delete(f"/api/ideas/{idea_id}")


async def test_reuse_stats(client: AsyncClient):
    from app.db import get_pool

    pool = await get_pool()
    ids = []
    for content, status in [
        ("复用统计-已复用", "used"),
        ("复用统计-已合并", "merged"),
        ("复用统计-新记录", "captured"),
    ]:
        iid = await pool.fetchval(
            "INSERT INTO ideas (raw_content, status, ai_status) "
            "VALUES ($1, $2, 'done') RETURNING id",
            content,
            status,
        )
        ids.append(iid)
    try:
        resp = await client.get("/api/stats/reuse")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_ideas"] >= 3
        assert data["used"] >= 1 and data["merged"] >= 1
        # 复用率口径：(used + merged) / total
        expected = round((data["used"] + data["merged"]) / data["total_ideas"], 4)
        assert data["reuse_rate"] == expected
    finally:
        await pool.execute("DELETE FROM ideas WHERE id = ANY($1)", ids)
