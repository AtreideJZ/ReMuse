"""MCP 容器端到端验证：真实 MCP client 连 localhost:8002/mcp。

用法（在 backend/ 下，set -a && source ../.env && set +a 之后）：
    .venv/Scripts/python scripts/verify_mcp.py
"""

import asyncio
import json
import os
import sys

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

API = "http://localhost:8001/api"
MCP = "http://localhost:8002/mcp"

# 管理面认证（C1）：从环境变量读取 ADMIN_TOKEN
ADMIN_HEADERS = {"X-Admin-Token": os.environ.get("ADMIN_TOKEN", "")}


async def main() -> int:
    # 1. 健康检查
    health = httpx.get("http://localhost:8002/health", timeout=10).json()
    print("health:", health)

    # 2. 建一个读写 Key
    resp = httpx.post(
        f"{API}/keys",
        json={"name": "mcp-e2e 验证", "scopes": ["read", "write"], "project_ids": []},
        headers=ADMIN_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    key = resp.json()["key"]
    key_id = resp.json()["id"]
    print("key created:", resp.json()["prefix"])

    try:
        # 3. 真实 MCP 会话
        # streamable_http_client（SDK 1.29 新 API）需自备带 Bearer 头的 httpx client
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {key}"},
            timeout=httpx.Timeout(30.0, read=300.0),
        ) as http_client:
            async with streamable_http_client(MCP, http_client=http_client) as (r, w, _):
                async with ClientSession(r, w) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    print("tools:", sorted(t.name for t in tools.tools))

                    res = await session.call_tool(
                        "search_ideas", {"query": "学生学习计划", "limit": 3}
                    )
                    data = res.structuredContent or json.loads(res.content[0].text)
                    titles = [i["title"] for i in data["ideas"]]
                    print("search hits:", len(titles), "| top:", titles[0] if titles else None)

                    res = await session.call_tool(
                        "capture_idea", {"content": "MCP 容器链路验证：这条灵感由 Agent 写入"}
                    )
                    data = res.structuredContent or json.loads(res.content[0].text)
                    idea_id = data["idea_id"]
                    print("captured:", idea_id[:8])

                    res = await session.read_resource("ideas://recent")
                    recent = json.loads(res.contents[0].text)
                    print("resource recent count:", len(recent["ideas"]))

        # 4. 调用日志应已记录
        logs = httpx.get(
            f"{API}/agent-logs",
            params={"agent_name": "mcp-e2e 验证"},
            headers=ADMIN_HEADERS,
            timeout=10,
        ).json()
        tools_logged = sorted({l["tool_name"] for l in logs["items"]})
        print("logged tools:", tools_logged, "| total:", logs["total"])

        # 5. 清理测试数据
        httpx.delete(f"{API}/ideas/{idea_id}", headers=ADMIN_HEADERS, timeout=10)
        ok = (
            health.get("status") == "ok"
            and len(tools_logged) >= 3
            and titles
        )
        print("E2E:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        httpx.post(f"{API}/keys/{key_id}/revoke", headers=ADMIN_HEADERS, timeout=10)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
