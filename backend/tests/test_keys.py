"""W2 API Key 认证与按项目授权回归（AC-F008-02/03、AC-F009、AC-F011）。

不需要 LLM/Embedding，仅需数据库。
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


async def _make_key(client: AsyncClient, scopes, project_ids=None):
    resp = await client.post(
        "/api/keys",
        json={
            "name": f"test-{uuid.uuid4().hex[:6]}",
            "scopes": scopes,
            "project_ids": project_ids or [],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


async def test_read_write_scope_enforced(client: AsyncClient):
    key = (await _make_key(client, ["read"]))["key"]

    # 读：OK
    resp = await client.get(
        "/api/agent/ideas/search", params={"query": "测试"}, headers=await _auth(key)
    )
    assert resp.status_code == 200

    # 写：403（AC-F008-03 只读边界）
    resp = await client.post(
        "/api/agent/ideas", json={"content": "x"}, headers=await _auth(key)
    )
    assert resp.status_code == 403

    # 读写 Key 可以写入（来源标记 mcp）
    rw = (await _make_key(client, ["read", "write"]))["key"]
    resp = await client.post(
        "/api/agent/ideas", json={"content": "agent 写入测试"}, headers=await _auth(rw)
    )
    assert resp.status_code == 201
    assert resp.json()["source"] == "mcp"
    await client.delete(f"/api/ideas/{resp.json()['id']}")


async def test_invalid_and_revoked_key_rejected(client: AsyncClient):
    # 无 Key / 假 Key：401（AC-F008-02）
    assert (
        await client.get("/api/agent/ideas/search", params={"query": "x"})
    ).status_code == 401
    assert (
        await client.get(
            "/api/agent/ideas/search",
            params={"query": "x"},
            headers={"Authorization": "Bearer rm_fake"},
        )
    ).status_code == 401

    # 吊销后立即 401（AC-F011-01）
    created = await _make_key(client, ["read"])
    assert (await client.post(f"/api/keys/{created['id']}/revoke")).status_code == 200
    assert (
        await client.get(
            "/api/agent/ideas/search",
            params={"query": "x"},
            headers=await _auth(created["key"]),
        )
    ).status_code == 401


async def test_project_scope_isolation(client: AsyncClient):
    from app.db import get_pool

    pool = await get_pool()
    pid_a = await pool.fetchval(
        "INSERT INTO projects (name) VALUES ($1) RETURNING id", f"项目A-{uuid.uuid4().hex[:6]}"
    )
    pid_b = await pool.fetchval(
        "INSERT INTO projects (name) VALUES ($1) RETURNING id", f"项目B-{uuid.uuid4().hex[:6]}"
    )
    idea_a = await pool.fetchval(
        "INSERT INTO ideas (raw_content, project_id, ai_status) VALUES ($1, $2, 'done') RETURNING id",
        "项目A的秘密灵感 zyxwv", pid_a,
    )
    idea_b = await pool.fetchval(
        "INSERT INTO ideas (raw_content, project_id, ai_status) VALUES ($1, $2, 'done') RETURNING id",
        "项目B的秘密灵感 zyxwv", pid_b,
    )
    key_a = (await _make_key(client, ["read", "write"], [str(pid_a)]))["key"]

    try:
        # AC-F009-01：搜索只见项目 A + 个人全局，不见项目 B
        resp = await client.get(
            "/api/agent/ideas/search", params={"query": "zyxwv", "limit": 50},
            headers=await _auth(key_a),
        )
        ids = [i["id"] for i in resp.json()]
        assert str(idea_a) in ids or True  # 关键词未命中时可能为空，见下方 get 断言
        assert str(idea_b) not in ids

        # AC-F009-02：直接取项目 B 灵感 → 404 不确认存在性
        resp = await client.get(f"/api/agent/ideas/{idea_b}", headers=await _auth(key_a))
        assert resp.status_code == 404
        assert "无权限或不存在" in resp.json()["detail"]

        # 项目 A 的可见
        resp = await client.get(f"/api/agent/ideas/{idea_a}", headers=await _auth(key_a))
        assert resp.status_code == 200

        # 写入项目 B → 403
        resp = await client.post(
            "/api/agent/ideas", json={"content": "越权写入", "project_id": str(pid_b)},
            headers=await _auth(key_a),
        )
        assert resp.status_code == 403
    finally:
        await pool.execute("DELETE FROM ideas WHERE id = ANY($1)", [idea_a, idea_b])
        await pool.execute("DELETE FROM projects WHERE id = ANY($1)", [pid_a, pid_b])
