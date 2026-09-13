"""W1 API 回归测试：灵感 / 项目 / 标签。

需要可访问的数据库（默认 postgresql://flash:flash@localhost:5432/flash，
可用 DATABASE_URL 覆盖）。数据库不可用时自动跳过。
LLM/Embedding 未配置时 AI 处理会失败降级——这正是要验证的行为（AC-F003-02）。
注意：测试直接操作真实数据库，清理用 try/finally 保证（即使断言失败也执行）。
"""

import asyncio
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

    # 管理面认证（C1）：测试显式设置令牌并携带请求头
    settings.admin_token = "test-admin-token"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Admin-Token": "test-admin-token"},
    ) as c:
        yield c


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def test_idea_lifecycle(client: AsyncClient):
    # 记录：201，原文落库，AI 异步处理（AC-F001-01）
    resp = await client.post("/api/ideas", json={"content": "测试灵感：用 Agent 管理灵感"})
    assert resp.status_code == 201
    idea = resp.json()
    idea_id = idea["id"]
    try:
        assert idea["raw_content"] == "测试灵感：用 Agent 管理灵感"
        assert idea["ai_status"] in ("pending", "processing", "done", "failed")
        assert idea["status"] == "captured"

        # 详情
        resp = await client.get(f"/api/ideas/{idea_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == idea_id

        # 列表含该条
        resp = await client.get("/api/ideas", params={"limit": 50})
        assert resp.status_code == 200
        assert any(i["id"] == idea_id for i in resp.json()["items"])
    finally:
        await client.delete(f"/api/ideas/{idea_id}")

    # 删除后 404
    assert (await client.get(f"/api/ideas/{idea_id}")).status_code == 404


async def test_empty_content_rejected(client: AsyncClient):
    resp = await client.post("/api/ideas", json={"content": "   "})
    assert resp.status_code == 400
    assert "不能为空" in resp.json()["detail"]


async def test_create_idea_with_captured_at(client: AsyncClient):
    """离线草稿补发：客户端可提交记录时刻，服务端做范围校验。"""
    from datetime import datetime, timedelta, timezone

    # 过去的合法时刻 → created_at 取记录时刻而非入库时刻
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    resp = await client.post(
        "/api/ideas",
        json={"content": "离线时记下的灵感", "captured_at": past.isoformat()},
    )
    assert resp.status_code == 201
    idea = resp.json()
    try:
        created = datetime.fromisoformat(idea["created_at"])
        assert abs((created - past).total_seconds()) < 1
    finally:
        await client.delete(f"/api/ideas/{idea['id']}")

    # 未来时刻（超出时钟偏移容忍）→ 422
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    resp = await client.post(
        "/api/ideas",
        json={"content": "来自未来的灵感", "captured_at": future.isoformat()},
    )
    assert resp.status_code == 422


async def test_project_lifecycle_and_delete_protection(client: AsyncClient):
    name = _uniq("测试项目")
    resp = await client.post("/api/projects", json={"name": name, "description": "d"})
    assert resp.status_code == 201
    pid = resp.json()["id"]
    idea_id = None
    try:
        # 重名 409
        resp = await client.post("/api/projects", json={"name": name})
        assert resp.status_code == 409

        # 灵感归入项目
        resp = await client.post(
            "/api/ideas", json={"content": "属于项目的灵感", "project_id": pid}
        )
        idea_id = resp.json()["id"]
        resp = await client.get("/api/ideas", params={"project_id": pid})
        assert any(i["id"] == idea_id for i in resp.json()["items"])

        # 删除项目：灵感转无项目而非被删除（AC-F006-02）
        assert (await client.delete(f"/api/projects/{pid}")).status_code == 204
        resp = await client.get(f"/api/ideas/{idea_id}")
        assert resp.status_code == 200
        assert resp.json()["project_id"] is None
    finally:
        if idea_id:
            await client.delete(f"/api/ideas/{idea_id}")
        await client.delete(f"/api/projects/{pid}")


async def test_ai_degrades_gracefully_without_llm_key(client: AsyncClient):
    """未配置 LLM 时：灵感正常保存，AI 失败可重试，原文完整（AC-F003-02）。"""
    from app.config import settings

    if settings.llm_api_key:
        pytest.skip("已配置 LLM，跳过降级用例")

    resp = await client.post("/api/ideas", json={"content": "降级测试灵感"})
    idea_id = resp.json()["id"]
    try:
        # 等异步任务跑完（未配置 key 会立即失败）
        for _ in range(20):
            await asyncio.sleep(0.5)
            resp = await client.get(f"/api/ideas/{idea_id}")
            if resp.json()["ai_status"] in ("done", "failed"):
                break
        idea = resp.json()
        assert idea["ai_status"] == "failed"
        assert idea["ai_error"]
        assert idea["raw_content"] == "降级测试灵感"

        # 重试接口可用（仍会失败，但状态机正确流转）
        resp = await client.post(f"/api/ideas/{idea_id}/retry-ai")
        assert resp.status_code == 200
        assert resp.json()["ai_status"] == "pending"
    finally:
        await client.delete(f"/api/ideas/{idea_id}")
