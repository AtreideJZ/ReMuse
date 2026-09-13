"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * PWA 分享目标落点（T2.4）：/capture?title=&text=&url=
 * 把分享内容合并成一条文本，跳首页记录框预填并立即聚焦（与 T2.5 同走 /?capture=1&text=）。
 */
export default function CaptureSharePage() {
  const router = useRouter();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const parts = [
      params.get("title"),
      params.get("text"),
      params.get("url"),
    ]
      .map((s) => s?.trim() ?? "")
      .filter((s) => s.length > 0);
    // 去重：部分应用会把 url 重复拼进 text
    const text = [...new Set(parts)].join("\n");
    router.replace(
      text ? `/?capture=1&text=${encodeURIComponent(text)}` : "/?capture=1",
    );
  }, [router]);

  return (
    <p className="py-16 text-center text-sm text-ink-faint">
      正在打开记录页…
    </p>
  );
}
