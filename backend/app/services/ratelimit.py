"""轻量 in-memory 滑动窗口限流（H1）。

单进程部署规模足够，无需 Redis。重点是触发 LLM/Embedding 计费调用与
重查询的端点：灵感写入（AI 结构化）、检索（Embedding 调用）、全量导出。
"""

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        dq = self._hits[key]
        while dq and now - dq[0] >= self.window_seconds:
            dq.popleft()
        if len(dq) >= self.max_requests:
            return False
        dq.append(now)
        return True


# 写入（每条触发 LLM 结构化 + Embedding 计费）
capture_limiter = SlidingWindowLimiter(max_requests=20, window_seconds=60)
# 检索（每次触发一次 Embedding 调用）
search_limiter = SlidingWindowLimiter(max_requests=60, window_seconds=60)
# 全量导出
export_limiter = SlidingWindowLimiter(max_requests=5, window_seconds=300)
