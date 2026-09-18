"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { AgentLog, AgentLogStatus, ReuseStats } from "@/lib/types";
import { relativeTime, truncate } from "@/lib/time";
import { ErrorBanner } from "@/components/error-banner";

const PAGE_SIZE = 50;

const TOOL_OPTIONS = [
  { value: "", label: "全部工具" },
  { value: "search_ideas", label: "search_ideas" },
  { value: "get_idea", label: "get_idea" },
  { value: "list_recent_ideas", label: "list_recent_ideas" },
  { value: "find_related_ideas", label: "find_related_ideas" },
  { value: "capture_idea", label: "capture_idea" },
] as const;

const DAY_OPTIONS = [
  { value: "", label: "全部时间" },
  { value: "7", label: "最近 7 天" },
  { value: "30", label: "最近 30 天" },
] as const;

const STATUS_STYLES: Record<AgentLogStatus, string> = {
  ok: "bg-success-soft text-success",
  denied: "bg-warning-soft text-warning",
  error: "bg-error-soft text-error",
};

const STATUS_LABELS: Record<AgentLogStatus, string> = {
  ok: "成功",
  denied: "拒绝",
  error: "错误",
};

interface LogFilters {
  agent: string;
  tool: string;
  days: string;
}

function toParams(filters: LogFilters, offset: number) {
  return {
    agent_name: filters.agent || undefined,
    tool_name: filters.tool || undefined,
    days: filters.days ? Number(filters.days) : undefined,
    limit: PAGE_SIZE,
    offset,
  };
}

function argumentsSummary(log: AgentLog): string {
  const raw: unknown = log.arguments;
  try {
    // 兼容：后端当前把 arguments 序列化为 JSON 字符串返回（契约约定为对象）
    if (typeof raw === "string") {
      return truncate(JSON.stringify(JSON.parse(raw)), 60);
    }
    return truncate(JSON.stringify(raw ?? {}), 60);
  } catch {
    return typeof raw === "string" ? truncate(raw, 60) : "{}";
  }
}

/** E4 + E10：把复用率百分比翻成人话；样本太小（< 8%）时不夸大，保留精确口径 */
function reuseRateText(stats: ReuseStats): string {
  const reused = stats.used + stats.merged;
  if (reused === 0) {
    return "还没有灵感被复用——Agent 经 MCP 接入后，检索命中并确认使用即开始累积";
  }
  const fraction = `（${reused} / ${stats.total_ideas} 条）`;
  if (stats.reuse_rate >= 0.5) {
    return `差不多每两条灵感里就有一条被用上。${fraction}`;
  }
  if (stats.reuse_rate >= 0.25) {
    return `每四条灵感里有超过一条回来了——这个比例已经不太像巧合。${fraction}`;
  }
  if (stats.reuse_rate >= 0.08) {
    return `每十条灵感左右，有一条回来了。${fraction}`;
  }
  return `复用率 ${(stats.reuse_rate * 100).toFixed(1)}%${fraction} · 开始有东西回来了。`;
}

/** 距今天数（E4「最久的一条」） */
function daysSince(iso: string): number {
  return Math.max(
    0,
    Math.floor((Date.now() - new Date(iso).getTime()) / 86400000),
  );
}

interface ReturnedIdeaChipProps {
  ideaId: string;
  marked: boolean;
  marking: boolean;
  onMarkUsed: (ideaId: string) => void;
}

/** 日志行中返回的灵感 chip：点击进详情，可标注「已复用」（标注态存组件内） */
function ReturnedIdeaChip({ ideaId, marked, marking, onMarkUsed }: ReturnedIdeaChipProps) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-fill py-0.5 pl-2 text-xs">
      <Link
        href={`/ideas/${ideaId}`}
        title={ideaId}
        className="font-mono text-primary hover:underline"
      >
        {ideaId.slice(0, 8)}
      </Link>
      {marked ? (
        <span className="pr-1.5 font-medium text-success">已复用</span>
      ) : (
        <button
          type="button"
          disabled={marking}
          onClick={() => onMarkUsed(ideaId)}
          className="pr-1.5 text-ink-faint transition-colors hover:text-success disabled:opacity-50"
        >
          {marking ? "标记中…" : "标为已复用"}
        </button>
      )}
    </span>
  );
}

export default function LogsPage() {
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [total, setTotal] = useState(0);
  const [agents, setAgents] = useState<string[]>([]);
  const [agentFilter, setAgentFilter] = useState("");
  const [toolFilter, setToolFilter] = useState("");
  const [days, setDays] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  // 复用率统计与「已复用」标注状态（组件内即可，无需持久到日志）
  const [stats, setStats] = useState<ReuseStats | null>(null);
  const [markedIds, setMarkedIds] = useState<ReadonlySet<string>>(new Set());
  const [markingIds, setMarkingIds] = useState<ReadonlySet<string>>(new Set());
  // 请求序号：筛选重载 / 加载更多共用一个计数器，防止旧响应覆盖或追加到错误列表
  const requestSeq = useRef(0);

  // 首次加载（setState 只发生在异步回调里）
  useEffect(() => {
    const seq = ++requestSeq.current;
    let cancelled = false;
    api
      .listAgentLogs(toParams({ agent: "", tool: "", days: "" }, 0))
      .then((data) => {
        if (cancelled || seq !== requestSeq.current) return;
        setLogs(data.items);
        setTotal(data.total);
        setError("");
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (cancelled || seq !== requestSeq.current) return;
        setError(e instanceof ApiError ? e.message : "加载失败，请稍后重试");
        setLoading(false);
      });
    api
      .listAgentNames()
      .then((data) => {
        if (!cancelled) setAgents(data.items);
      })
      .catch(() => {});
    api
      .getReuseStats()
      .then((data) => {
        if (!cancelled) setStats(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  function refreshStats() {
    api
      .getReuseStats()
      .then((data) => setStats(data))
      .catch(() => {});
  }

  // 筛选变化时重置列表重新加载（事件 handler 内调用，不触发 set-state-in-effect）
  function reload(filters: LogFilters) {
    const seq = ++requestSeq.current;
    setLoading(true);
    setError("");
    setExpandedId(null);
    api
      .listAgentLogs(toParams(filters, 0))
      .then((data) => {
        if (seq !== requestSeq.current) return;
        setLogs(data.items);
        setTotal(data.total);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (seq !== requestSeq.current) return;
        setError(e instanceof ApiError ? e.message : "加载失败，请稍后重试");
        setLoading(false);
      });
  }

  function handleFilterChange(kind: "agent" | "tool" | "days", value: string) {
    const next: LogFilters = {
      agent: kind === "agent" ? value : agentFilter,
      tool: kind === "tool" ? value : toolFilter,
      days: kind === "days" ? value : days,
    };
    if (kind === "agent") setAgentFilter(value);
    if (kind === "tool") setToolFilter(value);
    if (kind === "days") setDays(value);
    reload(next);
  }

  function handleLoadMore() {
    if (loadingMore) return;
    const seq = ++requestSeq.current;
    setLoadingMore(true);
    api
      .listAgentLogs(
        toParams({ agent: agentFilter, tool: toolFilter, days }, logs.length),
      )
      .then((data) => {
        if (seq !== requestSeq.current) return;
        setLogs((prev) => [...prev, ...data.items]);
        setTotal(data.total);
        setLoadingMore(false);
      })
      .catch((e: unknown) => {
        if (seq !== requestSeq.current) return;
        setError(e instanceof ApiError ? e.message : "加载失败，请稍后重试");
        setLoadingMore(false);
      });
  }

  async function handleMarkUsed(ideaId: string) {
    if (markedIds.has(ideaId) || markingIds.has(ideaId)) return;
    setMarkingIds((prev) => new Set(prev).add(ideaId));
    try {
      await api.updateIdea(ideaId, { status: "used" });
      setMarkedIds((prev) => new Set(prev).add(ideaId));
      // 标注成功后刷新顶部统计
      refreshStats();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "标记失败，请稍后重试");
    } finally {
      setMarkingIds((prev) => {
        const next = new Set(prev);
        next.delete(ideaId);
        return next;
      });
    }
  }

  const hasMore = logs.length < total;

  return (
    <div className="space-y-4">
      {/* 复用率统计卡片（T1.4）：主数字是「待唤醒」存量，复用率降为次级口径说明 */}
      {stats && (
        <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-surface p-4">
          <div>
            <p className="text-2xl font-semibold text-primary">
              待唤醒 {stats.captured} 条
            </p>
            <p className="mt-1 text-xs text-ink-faint">{reuseRateText(stats)}</p>
            {/* E4(b)：最久的待唤醒条目——可点击的观察项；老版本 API 无此字段时静默隐藏 */}
            {stats.oldest_captured_id && stats.oldest_captured_at && (
              <Link
                href={`/ideas/${stats.oldest_captured_id}`}
                className="mt-1.5 inline-block text-xs font-medium text-primary hover:underline"
              >
                最久的一条：{daysSince(stats.oldest_captured_at)} 天 · 去翻翻 →
              </Link>
            )}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-faint">
            <span>
              被检索{" "}
              <span className="font-medium text-ink-secondary">{stats.retrieved}</span>
            </span>
            <span>
              已复用 <span className="font-medium text-success">{stats.used}</span>
            </span>
            <span>
              已合并{" "}
              <span className="font-medium text-ink-secondary">{stats.merged}</span>
            </span>
          </div>
        </section>
      )}

      {/* 筛选栏 */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={agentFilter}
          onChange={(e) => handleFilterChange("agent", e.target.value)}
          aria-label="按 Agent 筛选"
          className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm text-ink-secondary focus:border-primary-border focus:outline-none"
        >
          <option value="">全部 Agent</option>
          {agents.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <select
          value={toolFilter}
          onChange={(e) => handleFilterChange("tool", e.target.value)}
          aria-label="按工具筛选"
          className="rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-sm text-ink-secondary focus:border-primary-border focus:outline-none"
        >
          {TOOL_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <div className="flex overflow-hidden rounded-md border border-border">
          {DAY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => handleFilterChange("days", opt.value)}
              className={`px-3 py-1.5 text-sm transition-colors ${
                days === opt.value
                  ? "bg-primary text-white"
                  : "bg-surface text-ink-secondary hover:bg-fill-soft"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <span className="ml-auto text-xs text-ink-faint">共 {total} 条调用</span>
      </div>

      {error && (
        <ErrorBanner
          message={error}
          onRetry={() =>
            reload({ agent: agentFilter, tool: toolFilter, days })
          }
        />
      )}

      {/* 日志列表 */}
      {loading ? (
        <p className="py-12 text-center text-sm text-ink-faint">加载中…</p>
      ) : logs.length === 0 ? (
        // E8：空态信任说明——坏消息也会被记录
        <p className="py-16 text-center text-sm text-ink-faint">
          暂无调用记录。Agent 接入后，每次检索都会留在这里——
          <span className="font-medium text-ink-secondary">包括被拒绝的那些。</span>
        </p>
      ) : (
        <div className="space-y-2">
          {logs.map((log) => {
            const expandable = log.error !== null;
            const expanded = expandedId === log.id;
            return (
              <div
                key={log.id}
                className="rounded-xl border border-border bg-surface px-4 py-3"
              >
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                  <span className="shrink-0 text-xs text-ink-faint">
                    {relativeTime(log.created_at)}
                  </span>
                  <span className="text-sm font-medium text-ink-strong">
                    {log.agent_name}
                  </span>
                  <code
                    className="max-w-48 truncate text-xs text-primary"
                    title={log.tool_name}
                  >
                    {log.tool_name}
                  </code>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${STATUS_STYLES[log.status]}`}
                  >
                    {STATUS_LABELS[log.status]}
                  </span>
                  <code className="min-w-0 flex-1 truncate text-xs text-ink-faint">
                    {argumentsSummary(log)}
                  </code>
                  {expandable && (
                    <button
                      type="button"
                      aria-expanded={expanded}
                      onClick={() => setExpandedId(expanded ? null : log.id)}
                      className="shrink-0 rounded-md border border-border px-2 py-0.5 text-xs text-ink-muted transition-colors hover:bg-fill-soft"
                    >
                      {expanded ? "收起" : "详情"}
                    </button>
                  )}
                </div>

                {log.returned_idea_ids.length > 0 && (
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <span className="text-xs text-ink-faint">
                      返回 {log.returned_idea_ids.length} 条：
                    </span>
                    {log.returned_idea_ids.slice(0, 5).map((ideaId) => (
                      <ReturnedIdeaChip
                        key={ideaId}
                        ideaId={ideaId}
                        marked={markedIds.has(ideaId)}
                        marking={markingIds.has(ideaId)}
                        onMarkUsed={handleMarkUsed}
                      />
                    ))}
                    {log.returned_idea_ids.length > 5 && (
                      <span className="text-xs text-ink-faint">
                        +{log.returned_idea_ids.length - 5}
                      </span>
                    )}
                  </div>
                )}

                {expanded && log.error !== null && (
                  <div className="mt-2 rounded-md border border-error-muted bg-error-soft px-3 py-2 text-xs text-error-strong">
                    {log.error}
                  </div>
                )}
              </div>
            );
          })}

          {hasMore && (
            <div className="pt-2 text-center">
              <button
                type="button"
                onClick={handleLoadMore}
                disabled={loadingMore}
                className="rounded-md border border-border bg-surface px-4 py-1.5 text-sm text-ink-secondary transition-colors hover:bg-fill-soft disabled:opacity-50"
              >
                {loadingMore ? "加载中…" : "加载更多"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
