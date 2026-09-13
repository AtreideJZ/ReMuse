"""P95 性能实测（PRD 非功能需求：记录 P95 < 200ms、搜索 P95 < 500ms）。

对运行中的服务（默认 localhost:8001）发起真实请求，输出延迟分布。
注意：搜索含一次远程 Embedding API 调用，结果受网络影响；
测试会创建并清理若干临时灵感。

用法（在 backend/ 下）：
    .venv/Scripts/python scripts/perf.py [轮数，默认 20]
"""

import asyncio
import os
import statistics
import sys
import time

import httpx

BASE = "http://localhost:8001/api"
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 20
# 管理面认证（C1）
ADMIN_HEADERS = {"X-Admin-Token": os.environ.get("ADMIN_TOKEN", "")}

QUERIES = ["学生学习计划", "pgvector", "Agent 记忆", "复习", "效率工具"]


def _p95(samples: list[float]) -> float:
    samples = sorted(samples)
    idx = max(0, int(len(samples) * 0.95) - 1)
    return samples[idx]


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=30, headers=ADMIN_HEADERS) as client:
        # 记录接口延迟（AI 异步不阻塞，AC-F001-01）
        record_lat: list[float] = []
        idea_ids: list[str] = []
        for i in range(ROUNDS):
            t0 = time.perf_counter()
            resp = await client.post(
                "/ideas", json={"content": f"性能测试灵感 {i}：测量记录接口延迟"}
            )
            record_lat.append((time.perf_counter() - t0) * 1000)
            resp.raise_for_status()
            idea_ids.append(resp.json()["id"])

        # 等 AI 异步任务与向量落库，避免搜索测到不完整状态
        await asyncio.sleep(8)

        # 搜索接口延迟（含远程 Embedding 调用）
        search_lat: list[float] = []
        for i in range(ROUNDS):
            q = QUERIES[i % len(QUERIES)]
            t0 = time.perf_counter()
            resp = await client.get("/search/ideas", params={"q": q, "limit": 10})
            search_lat.append((time.perf_counter() - t0) * 1000)
            resp.raise_for_status()

        # 清理临时灵感
        for iid in idea_ids:
            await client.delete(f"/ideas/{iid}")

    def report(name: str, samples: list[float], target_ms: float) -> bool:
        p50 = statistics.median(samples)
        p95 = _p95(samples)
        ok = p95 < target_ms
        print(
            f"{name}: n={len(samples)} p50={p50:.0f}ms p95={p95:.0f}ms "
            f"max={max(samples):.0f}ms 目标P95<{target_ms}ms -> {'PASS' if ok else 'FAIL'}"
        )
        return ok

    ok_record = report("记录 POST /ideas", record_lat, 200)
    ok_search = report("搜索 GET /search/ideas", search_lat, 500)
    return 0 if (ok_record and ok_search) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
