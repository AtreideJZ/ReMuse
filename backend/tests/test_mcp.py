"""W3 MCP Server 集成测试：真实 MCP client + Streamable HTTP，不 mock 协议。

覆盖：AC-F008-01 工具调用、AC-F008-02 未授权拒绝、AC-F008-03 只读边界、
F-010 调用日志写入。
需要数据库可用（与 test_api.py 同环境）。
"""

import asyncio
import json
import uuid

import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="session")
async def mcp_url():
    """整个测试会话共享一个 MCP 服务器实例（随机空闲端口）。

    反复启停 uvicorn 在 Windows 上会触发端口绑定竞态，单实例更稳也更快。
    """
    from app.mcp_server import asgi_app

    config = uvicorn.Config(asgi_app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail("MCP 测试服务器启动失败")
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    await task


@pytest.fixture
async def keys():
    """创建只读 / 读写两个 Key，测试后清理（含其调用日志）。"""
    from app.db import get_pool
    from app.services.keys import generate_key

    pool = await get_pool()
    created = {}
    for label, scopes in [("ro", ["read"]), ("rw", ["read", "write"])]:
        token, prefix, key_hash = generate_key()
        kid = await pool.fetchval(
            "INSERT INTO api_keys (name, prefix, key_hash, scopes) "
            "VALUES ($1, $2, $3, $4) RETURNING id",
            f"mcp-test-{label}-{uuid.uuid4().hex[:6]}",
            prefix,
            key_hash,
            scopes,
        )
        created[label] = {"token": token, "id": kid}
    yield created
    await pool.execute(
        "DELETE FROM agent_call_logs WHERE api_key_id = ANY($1)",
        [k["id"] for k in created.values()],
    )
    await pool.execute(
        "DELETE FROM api_keys WHERE id = ANY($1)", [k["id"] for k in created.values()]
    )


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _call(mcp_url, token, tool, arguments):
    async with streamablehttp_client(mcp_url, headers=_auth(token)) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            return await session.call_tool(tool, arguments)


def _payload(result):
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text)


async def test_list_tools(mcp_url, keys):
    async with streamablehttp_client(mcp_url, headers=_auth(keys["ro"]["token"])) as (
        r,
        w,
        _,
    ):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {
                "capture_idea",
                "search_ideas",
                "get_idea",
                "list_recent_ideas",
                "find_related_ideas",
                "mark_idea_as_used",
            } <= names


async def test_search_and_logs(mcp_url, keys):
    """AC-F008-01：搜索返回结构化灵感；F-010：调用日志落库。"""
    res = await _call(mcp_url, keys["ro"]["token"], "search_ideas", {"query": "复习", "limit": 3})
    assert not res.isError
    data = _payload(res)
    assert "note" in data and "ideas" in data

    from app.db import get_pool

    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT tool_name, status, arguments FROM agent_call_logs "
        "WHERE api_key_id = $1 ORDER BY created_at DESC LIMIT 1",
        keys["ro"]["id"],
    )
    assert row["tool_name"] == "search_ideas"
    assert row["status"] == "ok"
    assert json.loads(row["arguments"])["query"] == "复习"


async def test_readonly_write_denied(mcp_url, keys):
    """AC-F008-03：只读 Key 调 capture_idea 被拒绝且记录 denied 日志。"""
    res = await _call(
        mcp_url, keys["ro"]["token"], "capture_idea", {"content": "越权测试"}
    )
    assert res.isError

    from app.db import get_pool

    pool = await get_pool()
    status = await pool.fetchval(
        "SELECT status FROM agent_call_logs "
        "WHERE api_key_id = $1 AND tool_name = 'capture_idea' "
        "ORDER BY created_at DESC LIMIT 1",
        keys["ro"]["id"],
    )
    assert status == "denied"


async def test_capture_with_write_scope(mcp_url, keys):
    res = await _call(
        mcp_url, keys["rw"]["token"], "capture_idea", {"content": "MCP 写入测试灵感"}
    )
    assert not res.isError
    data = _payload(res)
    idea_id = data["idea_id"]

    # 用 get_idea 读回
    res = await _call(mcp_url, keys["rw"]["token"], "get_idea", {"idea_id": idea_id})
    assert not res.isError
    assert _payload(res)["idea"]["content"] == "MCP 写入测试灵感"

    from app.db import get_pool

    pool = await get_pool()
    await pool.execute("DELETE FROM ideas WHERE id = $1", uuid.UUID(idea_id))


async def test_unauthorized_rejected(mcp_url, keys):
    """AC-F008-02：无 Key / 假 Key 连接即 401。"""
    with pytest.raises(Exception):
        async with streamablehttp_client(mcp_url) as (r, w, _):
            async with ClientSession(r, w) as session:
                await session.initialize()
    with pytest.raises(Exception):
        async with streamablehttp_client(
            mcp_url, headers={"Authorization": "Bearer rm_fake"}
        ) as (r, w, _):
            async with ClientSession(r, w) as session:
                await session.initialize()


async def test_resource_recent(mcp_url, keys):
    async with streamablehttp_client(mcp_url, headers=_auth(keys["ro"]["token"])) as (
        r,
        w,
        _,
    ):
        async with ClientSession(r, w) as session:
            await session.initialize()
            res = await session.read_resource("ideas://recent")
            data = json.loads(res.contents[0].text)
            assert "note" in data and "ideas" in data


async def test_logs_api(mcp_url, keys):
    """F-010 日志查询 API：days 过滤可用、arguments 返回对象为 dict。"""
    await _call(mcp_url, keys["ro"]["token"], "search_ideas", {"query": "日志API测试"})

    from httpx import ASGITransport, AsyncClient

    from app.config import settings
    from app.main import app

    settings.admin_token = "test-admin-token"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Admin-Token": "test-admin-token"},
    ) as client:
        resp = await client.get("/api/agent-logs", params={"days": 7, "limit": 10})
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(l["tool_name"] == "search_ideas" for l in items)
        assert all(isinstance(l["arguments"], dict) for l in items)


async def test_get_idea_log_distinguishes_denied_from_missing(mcp_url, keys):
    """读取失败对内区分「越权」与「不存在」（对外仍统一不泄露存在性）。"""
    from app.db import get_pool
    from app.services.keys import generate_key

    pool = await get_pool()

    # 真不存在：日志 status=error, error=不存在
    missing_id = str(uuid.uuid4())
    res = await _call(mcp_url, keys["ro"]["token"], "get_idea", {"idea_id": missing_id})
    assert res.isError
    row = await pool.fetchrow(
        "SELECT status, error FROM agent_call_logs "
        "WHERE api_key_id = $1 AND tool_name = 'get_idea' "
        "ORDER BY created_at DESC LIMIT 1",
        keys["ro"]["id"],
    )
    assert row["status"] == "error" and row["error"] == "不存在"

    # 真越权：灵感存在但 Key 被限定到另一个项目 → status=denied, error=越权访问
    pid_a = await pool.fetchval(
        "INSERT INTO projects (name) VALUES ($1) RETURNING id",
        f"日志区分A-{uuid.uuid4().hex[:6]}",
    )
    pid_b = await pool.fetchval(
        "INSERT INTO projects (name) VALUES ($1) RETURNING id",
        f"日志区分B-{uuid.uuid4().hex[:6]}",
    )
    idea_b = await pool.fetchval(
        "INSERT INTO ideas (raw_content, project_id, ai_status) "
        "VALUES ($1, $2, 'done') RETURNING id",
        "项目B的灵感（越权日志区分测试）",
        pid_b,
    )
    token, prefix, key_hash = generate_key()
    key_a_id = await pool.fetchval(
        "INSERT INTO api_keys (name, prefix, key_hash, scopes, project_ids) "
        "VALUES ($1, $2, $3, '{read}', $4) RETURNING id",
        f"mcp-test-scoped-{uuid.uuid4().hex[:6]}",
        prefix,
        key_hash,
        [pid_a],
    )
    try:
        res = await _call(mcp_url, token, "get_idea", {"idea_id": str(idea_b)})
        assert res.isError
        row = await pool.fetchrow(
            "SELECT status, error FROM agent_call_logs "
            "WHERE api_key_id = $1 AND tool_name = 'get_idea' "
            "ORDER BY created_at DESC LIMIT 1",
            key_a_id,
        )
        assert row["status"] == "denied" and row["error"] == "越权访问"
    finally:
        await pool.execute("DELETE FROM agent_call_logs WHERE api_key_id = $1", key_a_id)
        await pool.execute("DELETE FROM api_keys WHERE id = $1", key_a_id)
        await pool.execute("DELETE FROM ideas WHERE id = $1", idea_b)
        await pool.execute("DELETE FROM projects WHERE id = ANY($1)", [pid_a, pid_b])


async def test_principal_isolation_under_concurrency(mcp_url, keys):
    """stateless + ContextVar 传 Principal：并发请求间认证上下文不能串。

    两个 Key 各发 20 个并发请求，若 ContextVar 泄漏，
    调用日志的 api_key_id 归属就会错位（计数对不上）。
    """
    from app.db import get_pool

    calls = []
    for _ in range(20):
        calls.append(_call(mcp_url, keys["ro"]["token"], "list_recent_ideas", {"limit": 1}))
        calls.append(_call(mcp_url, keys["rw"]["token"], "list_recent_ideas", {"limit": 1}))
    results = await asyncio.gather(*calls, return_exceptions=True)
    failures = [r for r in results if isinstance(r, Exception)]
    assert not failures, f"并发调用出现失败: {failures[:3]}"

    pool = await get_pool()
    for label, expected in [("ro", 20), ("rw", 20)]:
        count = await pool.fetchval(
            "SELECT COUNT(*) FROM agent_call_logs "
            "WHERE api_key_id = $1 AND tool_name = 'list_recent_ideas'",
            keys[label]["id"],
        )
        assert count >= expected, f"{label} 归属日志数 {count} < {expected}，可能存在串请求"


async def test_search_marks_retrieved(mcp_url, keys):
    """闭环：Agent 搜索命中的灵感 captured → retrieved；used 状态不被回退。"""
    from app.db import get_pool

    pool = await get_pool()
    marker = f"闭环检索标记-{uuid.uuid4().hex[:6]}"
    idea_captured = await pool.fetchval(
        "INSERT INTO ideas (raw_content, status, ai_status) "
        "VALUES ($1, 'captured', 'done') RETURNING id",
        f"{marker} 一条新灵感",
    )
    idea_used = await pool.fetchval(
        "INSERT INTO ideas (raw_content, status, ai_status) "
        "VALUES ($1, 'used', 'done') RETURNING id",
        f"{marker} 一条已复用灵感",
    )
    try:
        res = await _call(
            mcp_url, keys["ro"]["token"], "search_ideas", {"query": marker, "limit": 10}
        )
        assert not res.isError

        s1 = await pool.fetchval("SELECT status FROM ideas WHERE id = $1", idea_captured)
        s2 = await pool.fetchval("SELECT status FROM ideas WHERE id = $1", idea_used)
        assert s1 == "retrieved", f"命中后应为 retrieved，实际 {s1}"
        assert s2 == "used", f"已复用状态不应被回退，实际 {s2}"
    finally:
        await pool.execute(
            "DELETE FROM ideas WHERE id = ANY($1)", [idea_captured, idea_used]
        )


async def test_mark_idea_as_used(mcp_url, keys):
    """闭环：mark_idea_as_used 置为 used 并带归因 note 写入日志（F-018）。"""
    from app.db import get_pool

    pool = await get_pool()
    idea_id = await pool.fetchval(
        "INSERT INTO ideas (raw_content, status, ai_status) "
        "VALUES ('闭环复用确认测试', 'captured', 'done') RETURNING id",
    )
    try:
        # 只读 Key 应被拒绝
        res = await _call(
            mcp_url, keys["ro"]["token"],
            "mark_idea_as_used", {"idea_id": str(idea_id), "note": "越权标记"},
        )
        assert res.isError
        s = await pool.fetchval("SELECT status FROM ideas WHERE id = $1", idea_id)
        assert s == "captured"

        # 读写 Key 成功
        res = await _call(
            mcp_url, keys["rw"]["token"],
            "mark_idea_as_used",
            {"idea_id": str(idea_id), "note": "用在了新项目的方案里"},
        )
        assert not res.isError
        data = _payload(res)
        assert data["status"] == "used"
        s = await pool.fetchval("SELECT status FROM ideas WHERE id = $1", idea_id)
        assert s == "used"

        # 日志带归因 note
        row = await pool.fetchrow(
            "SELECT arguments FROM agent_call_logs "
            "WHERE api_key_id = $1 AND tool_name = 'mark_idea_as_used' "
            "ORDER BY created_at DESC LIMIT 1",
            keys["rw"]["id"],
        )
        assert "用在了新项目的方案里" in json.loads(row["arguments"])["note"]
    finally:
        await pool.execute("DELETE FROM ideas WHERE id = $1", idea_id)


async def test_find_related_ideas_after_refactor(mcp_url, keys):
    """T1.3 重构回归：find_related_ideas 行为不变——授权校验 + 命中记 retrieved + 写调用日志。"""
    from app.db import get_pool

    pool = await get_pool()
    idea_id = await pool.fetchval(
        "INSERT INTO ideas (raw_content, status, ai_status) "
        "VALUES ($1, 'captured', 'done') RETURNING id",
        f"相关灵感MCP回归-{uuid.uuid4().hex[:6]}",
    )
    try:
        # 目标无 embedding → 空结果但调用成功（与重构前一致）
        res = await _call(
            mcp_url, keys["ro"]["token"],
            "find_related_ideas", {"idea_id": str(idea_id), "limit": 5},
        )
        assert not res.isError
        data = _payload(res)
        assert "note" in data and data["ideas"] == []

        row = await pool.fetchrow(
            "SELECT status FROM agent_call_logs "
            "WHERE api_key_id = $1 AND tool_name = 'find_related_ideas' "
            "ORDER BY created_at DESC LIMIT 1",
            keys["ro"]["id"],
        )
        assert row["status"] == "ok"

        # 不存在的灵感 → 工具错误（不泄露存在性），日志记 error
        res = await _call(
            mcp_url, keys["ro"]["token"],
            "find_related_ideas", {"idea_id": str(uuid.uuid4())},
        )
        assert res.isError
        row = await pool.fetchrow(
            "SELECT status, error FROM agent_call_logs "
            "WHERE api_key_id = $1 AND tool_name = 'find_related_ideas' "
            "ORDER BY created_at DESC LIMIT 1",
            keys["ro"]["id"],
        )
        assert row["status"] == "error" and row["error"] == "不存在"
    finally:
        await pool.execute("DELETE FROM ideas WHERE id = $1", idea_id)
