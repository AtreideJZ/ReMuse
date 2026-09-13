import type { AIStatus } from "@/lib/types";

interface AIStatusBadgeProps {
  status: AIStatus;
}

/** 灵感条目的 AI 状态标识：处理中 / 失败可重试；done 时不显示。 */
export function AIStatusBadge({ status }: AIStatusBadgeProps) {
  if (status === "pending" || status === "processing") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-primary-soft px-2 py-0.5 text-xs text-primary">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary-pulse" />
        AI 处理中…
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="inline-flex items-center rounded-full bg-error-soft px-2 py-0.5 text-xs text-error">
        AI 失败 · 可重试
      </span>
    );
  }
  return null;
}
