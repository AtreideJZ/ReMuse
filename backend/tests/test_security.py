"""安全加固回归：

- C1：管理面 ADMIN_TOKEN 认证（fail-closed）
- H1：速率限制（capture 触发 LLM 计费，超限 429）
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

ADMIN = "test-admin-token"


@pytest.fixture
def admin_token():
    from app.config import settings

    settings.admin_token = ADMIN
    yield ADMIN


def _client(app, headers=None):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers)


async def test_admin_endpoints_require_token(admin_token):
    """C1：管理端点无令牌/错误令牌 401，正确令牌放行（X-Admin-Token 或 Bearer）。"""
    from app.main import app

    async with _client(app) as c:
        for path in ("/api/ideas", "/api/export", "/api/keys", "/api/agent-logs"):
            assert (await c.get(path)).status_code == 401, path
        assert (
            await c.get("/api/ideas", headers={"X-Admin-Token": "wrong"})
        ).status_code == 401
        assert (
            await c.get("/api/ideas", headers={"X-Admin-Token": admin_token})
        ).status_code == 200
        assert (
            await c.get(
                "/api/ideas", headers={"Authorization": f"Bearer {admin_token}"}
            )
        ).status_code == 200
        # 探活与 Agent 面不受影响（Agent 走自己的 Bearer Key 认证）
        assert (await c.get("/api/health")).status_code == 200
        assert (
            await c.get("/api/agent/ideas/search", params={"query": "x"})
        ).status_code == 401  # 到达 Agent 认证（无 Key 被拒）说明豁免生效


async def test_admin_fail_closed_when_unset():
    """C1：未配置 ADMIN_TOKEN 时管理面整体 503（杜绝裸奔）。"""
    from app.config import settings
    from app.main import app

    settings.admin_token = ""
    async with _client(app) as c:
        resp = await c.get("/api/ideas")
        assert resp.status_code == 503
        assert "ADMIN_TOKEN" in resp.json()["detail"]
        # 探活仍可用
        assert (await c.get("/api/health")).status_code == 200
    settings.admin_token = ADMIN


async def test_capture_rate_limited(admin_token, monkeypatch):
    """H1：capture 超限返回 429（不触发真实 LLM 调用）。"""
    from app.db import get_pool
    from app.main import app
    from app.routers import agent as agent_router
    from app.services import ratelimit
    from app.services.keys import generate_key

    # 不打真实 LLM：入队函数替换为空操作
    monkeypatch.setattr(agent_router, "enqueue_ai_processing", lambda idea_id: None)

    limiter = ratelimit.capture_limiter
    old_max = limiter.max_requests
    limiter.max_requests = 2

    pool = await get_pool()
    token, prefix, key_hash = generate_key()
    key_id = await pool.fetchval(
        "INSERT INTO api_keys (name, prefix, key_hash, scopes) "
        "VALUES ($1, $2, $3, '{read,write}') RETURNING id",
        f"ratelimit-{uuid.uuid4().hex[:6]}",
        prefix,
        key_hash,
    )
    created: list[str] = []
    try:
        async with _client(app, {"Authorization": f"Bearer {token}"}) as c:
            r1 = await c.post("/api/agent/ideas", json={"content": "限流测试-1"})
            r2 = await c.post("/api/agent/ideas", json={"content": "限流测试-2"})
            r3 = await c.post("/api/agent/ideas", json={"content": "限流测试-3"})
            assert r1.status_code == 201 and r2.status_code == 201
            assert r3.status_code == 429
            created = [r1.json()["id"], r2.json()["id"]]
    finally:
        limiter.max_requests = old_max
        for iid in created:
            await pool.execute("DELETE FROM ideas WHERE id = $1", uuid.UUID(iid))
        await pool.execute(
            "DELETE FROM agent_call_logs WHERE api_key_id = $1", key_id
        )
        await pool.execute("DELETE FROM api_keys WHERE id = $1", key_id)


async def test_security_headers_present(admin_token):
    """H2：API 响应带基础安全头。"""
    from app.main import app

    async with _client(app, {"X-Admin-Token": admin_token}) as c:
        resp = await c.get("/api/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
