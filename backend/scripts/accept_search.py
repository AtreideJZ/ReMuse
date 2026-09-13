"""AC-F005 混合检索验收脚本（需服务运行在 8001，种子数据已插入且向量已回填）。

用法（在 backend/ 下）：
    .venv/Scripts/python scripts/accept_search.py
"""

import os
import sys

import httpx

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8001/api")
# 管理面认证（C1）
ADMIN_HEADERS = {"X-Admin-Token": os.environ.get("ADMIN_TOKEN", "")}


def search(q: str, **params) -> list[dict]:
    resp = httpx.get(
        f"{BASE}/search/ideas",
        params={"q": q, **params},
        headers=ADMIN_HEADERS,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    return ok


def main() -> int:
    results: list[bool] = []

    # AC-F005-01：语义召回。查询「学生学习计划」，目标灵感应进前 5
    hits = search("学生学习计划")
    titles = [h["raw_content"] for h in hits]
    target = next(
        (i for i, t in enumerate(titles) if "考试日期自动规划复习" in t), None
    )
    results.append(
        check(
            "AC-F005-01 语义召回",
            target is not None and target < 5,
            f"目标排名: {target + 1 if target is not None else '未命中'} / {len(hits)}",
        )
    )

    # AC-F005-02：关键词精确召回。查询「pgvector」，目标应排第 1
    hits = search("pgvector")
    first = hits[0]["raw_content"] if hits else ""
    results.append(
        check(
            "AC-F005-02 关键词精确",
            bool(hits) and "pgvector" in first,
            f"第 1 名: {first[:40]}",
        )
    )

    # AC-F005-03：过滤器组合。限定项目 + 最近 7 天
    projects = httpx.get(f"{BASE}/projects", headers=ADMIN_HEADERS, timeout=10).json()["items"]
    campus = next(p for p in projects if p["name"] == "校园效率工具")
    hits = search("学习", project_id=campus["id"], days=7)
    only_project = all(h["project_name"] == "校园效率工具" for h in hits)
    results.append(
        check(
            "AC-F005-03 过滤器组合",
            bool(hits) and only_project,
            f"命中 {len(hits)} 条，全部归属校园效率工具: {only_project}",
        )
    )

    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
