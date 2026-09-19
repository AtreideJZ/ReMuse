"""中文混合检索精度评测（路线图阶段一 P0：检索精度人工评测 ≥80%）。

对运行中的服务（默认 localhost:8001）跑评测集（eval_dataset.json），
输出每个查询的命中情况与汇总指标：
- Hit@5：前 5 名中至少命中 1 条相关（主指标，目标 ≥80%）
- P@5：前 5 名中相关结果占比
- MRR：首条相关结果排名的倒数均值

用法（在 backend/ 下）：
    .venv/Scripts/python scripts/eval_search.py [--api http://localhost:8001/api]
"""

import json
import os
import statistics
import sys
from pathlib import Path

import httpx

DATASET = Path(__file__).parent / "eval_dataset.json"
API = sys.argv[sys.argv.index("--api") + 1] if "--api" in sys.argv else "http://localhost:8001/api"
TARGET = 0.80
# 管理面认证（C1）
ADMIN_HEADERS = {"X-Admin-Token": os.environ.get("ADMIN_TOKEN", "")}


def main() -> int:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    rows = []
    for item in dataset:
        q, relevant = item["query"], item["relevant"]
        resp = httpx.get(
            f"{API}/search/ideas",
            params={"q": q, "limit": 5},
            headers=ADMIN_HEADERS,
            timeout=60,
        )
        resp.raise_for_status()
        top = [h["raw_content"] for h in resp.json()["items"]]

        first_rank = next(
            (i for i, c in enumerate(top, 1) if any(r in c for r in relevant)), None
        )
        rel_in_top = sum(1 for c in top if any(r in c for r in relevant))
        rel_found = sum(1 for r in relevant if any(r in c for c in top))
        rows.append(
            {
                "query": q,
                "hit": first_rank is not None,
                "first_rank": first_rank,
                "p5": rel_in_top / 5,
                "rr": 1.0 / first_rank if first_rank else 0.0,
                "found": f"{rel_found}/{len(relevant)}",
            }
        )

    for r in rows:
        mark = "✅" if r["hit"] else "❌"
        rank = r["first_rank"] or "-"
        print(f"{mark} {r['query']:<16} 首个相关排名: {rank}  P@5: {r['p5']:.1f}  相关命中: {r['found']}")

    hit_rate = statistics.mean(1 if r["hit"] else 0 for r in rows)
    mean_p5 = statistics.mean(r["p5"] for r in rows)
    mrr = statistics.mean(r["rr"] for r in rows)
    print()
    print(f"Hit@5 命中率: {hit_rate:.0%}（目标 ≥{TARGET:.0%}）  "
          f"P@5 均值: {mean_p5:.2f}  MRR: {mrr:.2f}  n={len(rows)}")

    if hit_rate < TARGET:
        print("FAIL: 命中率未达标，需要调优（RRF k / 分词 mapping / probes）")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
