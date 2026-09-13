"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { AgentLog } from "@/lib/types";
import { relativeTime } from "@/lib/time";

const REFRESH_INTERVAL_MS = 60000;
const LOG_COUNT = 5;

/** 把一次调用渲染成中文活动描述；REST 入口的 rest: 前缀去掉后与 MCP 同构 */
function activityText(log: AgentLog): string {
  if (log.status === "denied") return "越权访问被拒绝";
  if (log.status === "error") return "调用出错";
  const tool = log.tool_name.replace(/^rest:/, "");
  const hits = log.returned_idea_ids.length;
  switch (tool) {
    case "search_ideas":
      return hits > 0 ? `检索了 ${hits} 条灵感` : "检索了灵感";
    case "find_related_ideas":
      return hits > 0 ? `找到 ${hits} 条相关灵感` : "查找了相关灵感";
    case "get_idea":
      return "读取了 1 条灵感";
    case "list_recent_ideas":
      return hits > 0 ? `浏览了最近 ${hits} 条灵感` : "浏览了最近的灵感";
    case "capture_idea":
      return "记录了 1 条灵感";
    case "mark_idea_as_used":
      return "确认复用了 1 条灵感";
    default:
      return `调用了 ${tool}`;
  }
}

/** 首页 Agent 活动流（T1.2）：最近几次调用，60s 自刷新；无活动时给出接入引导 */
export function AgentActivity() {
  // null = 首次加载中（不占位）；[] = 无活动（显示引导）
  const [logs, setLogs] = useState<AgentLog[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      api
        .listAgentLogs({ limit: LOG_COUNT })
        .then((data) => {
          if (!cancelled) setLogs(data.items);
        })
        .catch(() => {
          // 静默失败：首页不因此报错，下一轮刷新再试
        });
    };
    load();
    const timer = setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  if (logs === null) return null;

  if (logs.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border px-4 py-3 text-sm text-ink-faint">
        Agent 尚未接入，配置 MCP 后这里会出现活动。
        <Link href="/logs" className="ml-1 text-primary hover:underline">
          前往日志页 →
        </Link>
      </p>
    );
  }

  return (
    <section aria-label="Agent 最近活动" className="space-y-0.5">
      {logs.map((log) => (
        <Link
          key={log.id}
          href="/logs"
          className="flex items-baseline gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors hover:bg-fill-soft"
        >
          <span className="shrink-0 text-xs text-ink-faint">
            {relativeTime(log.created_at)}
          </span>
          <span className="min-w-0 truncate">
            <span className="font-medium text-ink-strong">{log.agent_name}</span>{" "}
            <span className="text-ink-secondary">{activityText(log)}</span>
          </span>
        </Link>
      ))}
    </section>
  );
}
