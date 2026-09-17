import Link from "next/link";
import type { Idea, IdeaStatus } from "@/lib/types";
import { relativeTime, truncate } from "@/lib/time";
import { AIStatusBadge } from "./ai-status-badge";

interface IdeaCardProps {
  idea: Idea;
}

// 复用状态徽章（T1.2）：只露用户确认过的终态；captured（默认态）与
// retrieved（Agent 找回但未确认使用）不渲染，宁可少标不可虚标
const STATUS_BADGES: Partial<
  Record<IdeaStatus, { label: string; className: string }>
> = {
  used: { label: "已复用", className: "bg-success-soft text-success" },
  merged: { label: "已合并", className: "bg-fill text-ink-muted" },
};

export function IdeaCard({ idea }: IdeaCardProps) {
  const aiDone = idea.ai_status === "done";
  // 记忆锚点是原文：AI 完成时标题用 ai_title 便于扫读、第二行显示原文；
  // 未完成（含失败）时主标题直接显示原文截断
  const title =
    aiDone && idea.ai_title ? idea.ai_title : truncate(idea.raw_content, 30);
  const statusBadge = STATUS_BADGES[idea.status];

  return (
    <Link
      href={`/ideas/${idea.id}`}
      className="block rounded-xl border border-border bg-surface p-4 transition-colors hover:border-primary-onsoft hover:bg-primary-soft/30"
    >
      <div className="flex items-start justify-between gap-3">
        <h2 className="min-w-0 flex-1 break-words text-base font-medium leading-snug text-ink-strong">
          {title}
        </h2>
        <AIStatusBadge status={idea.ai_status} />
      </div>
      {aiDone && (
        <p className="mt-1.5 line-clamp-2 break-words text-sm text-ink-muted">
          {idea.raw_content}
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-ink-faint">
        {statusBadge && (
          <span className={`rounded-full px-2 py-0.5 ${statusBadge.className}`}>
            {statusBadge.label}
          </span>
        )}
        {idea.tags.map((tag) => (
          <span
            key={tag}
            className="rounded-full bg-fill px-2 py-0.5 text-ink-secondary"
          >
            {tag}
          </span>
        ))}
        {idea.project_name && (
          <span className="rounded-full bg-primary-soft px-2 py-0.5 text-primary">
            {idea.project_name}
          </span>
        )}
        <span className="ml-auto shrink-0">
          {relativeTime(idea.created_at)}
        </span>
      </div>
    </Link>
  );
}
