"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { ThemeToggle } from "@/components/theme-toggle";

const ENTRY_LINKS = [
  {
    href: "/keys",
    label: "API 密钥",
    description: "创建、按项目授权与吊销 Agent 访问密钥",
  },
  {
    href: "/logs",
    label: "Agent 日志",
    description: "Agent 调用记录、复用率统计与复用标注",
  },
] as const;

export default function SettingsPage() {
  const pathname = usePathname();
  const [exporting, setExporting] = useState(false);

  // 导出全部数据：带管理令牌请求 /api/export，Blob 触发本地下载
  async function handleExport() {
    if (exporting) return;
    setExporting(true);
    try {
      const blob = await api.exportData();
      const url = URL.createObjectURL(blob);
      const stamp = new Date().toISOString().slice(0, 10).replaceAll("-", "");
      const a = document.createElement("a");
      a.href = url;
      a.download = `remuse-export-${stamp}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      if (!(e instanceof ApiError && e.aborted)) {
        window.alert(e instanceof ApiError ? `导出失败：${e.message}` : "导出失败，请稍后重试");
      }
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-semibold text-ink-strong">设置</h1>

      {/* 外观 */}
      <section className="rounded-xl border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-medium text-ink-strong">外观</h2>
            <p className="mt-0.5 text-xs text-ink-faint">
              浅色、深色或跟随系统
            </p>
          </div>
          <ThemeToggle />
        </div>
      </section>

      {/* 管理与运维入口 */}
      <section className="space-y-2">
        {ENTRY_LINKS.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className="block rounded-xl border border-border bg-surface p-4 transition-colors hover:border-primary-onsoft hover:bg-primary-soft/30"
            >
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-medium text-ink-strong">
                  {item.label}
                </h2>
                <span aria-hidden className="text-ink-faint">
                  →
                </span>
              </div>
              <p className="mt-1 text-xs text-ink-muted">{item.description}</p>
            </Link>
          );
        })}

        {/* 数据导出（原顶部导航导出按钮迁移至此） */}
        <div className="rounded-xl border border-border bg-surface p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-medium text-ink-strong">数据导出</h2>
              <p className="mt-1 text-xs text-ink-muted">
                一键导出全部灵感与项目（JSON，含原文与向量）
              </p>
            </div>
            <button
              type="button"
              onClick={() => void handleExport()}
              disabled={exporting}
              className="shrink-0 rounded-md border border-border px-3 py-1.5 text-sm font-medium text-ink-secondary transition-colors hover:bg-fill hover:text-ink-strong disabled:opacity-50"
            >
              {exporting ? "导出中…" : "导出"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
