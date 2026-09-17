"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { Idea, Project, ReuseTrace } from "@/lib/types";
import { readIdeaListOrder, type ListOrderEntry } from "@/lib/idea-list-order";
import { formatDateTime, relativeTime, truncate } from "@/lib/time";
import { ErrorBanner } from "@/components/error-banner";

const POLL_INTERVAL_MS = 4000;

const SOURCE_LABELS: Record<Idea["source"], string> = {
  web: "网页",
  pwa: "PWA",
  mcp: "MCP",
};

export default function IdeaDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();

  const [idea, setIdea] = useState<Idea | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [accepting, setAccepting] = useState(false);
  const [suggestionDismissed, setSuggestionDismissed] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [markingUsed, setMarkingUsed] = useState(false);
  // 列表顺序快照（T4.5）：来自列表页写入的 sessionStorage，供上一条/下一条浏览
  const [listOrder, setListOrder] = useState<ListOrderEntry[]>([]);
  // 复用档案 / 相关灵感：与主数据并行请求、独立容错（接口不存在或失败时区块静默隐藏）。
  // 带上请求时的 id，路由参数变化时旧数据不会错显在新灵感上
  const [reuseTrace, setReuseTrace] = useState<{
    id: string;
    data: ReuseTrace;
  } | null>(null);
  const [relatedIdeas, setRelatedIdeas] = useState<{
    id: string;
    items: Idea[];
  } | null>(null);
  // 请求序号：轮询与首次加载共用一个计数器，防止旧响应覆盖新状态
  const requestSeq = useRef(0);

  // 首次加载（setState 只发生在异步回调里）
  useEffect(() => {
    const seq = ++requestSeq.current;
    let cancelled = false;
    api
      .getIdea(id)
      .then((data) => {
        if (cancelled || seq !== requestSeq.current) return;
        setIdea(data);
        setError("");
      })
      .catch((e: unknown) => {
        if (cancelled || seq !== requestSeq.current) return;
        if (e instanceof ApiError && e.status === 404) {
          setNotFound(true);
        } else {
          setError(e instanceof ApiError ? e.message : "加载失败，请稍后重试");
        }
      });
    api
      .listProjects()
      .then((data) => {
        if (!cancelled) setProjects(data.items);
      })
      .catch(() => {});
    api
      .getReuseTrace(id)
      .then((data) => {
        if (!cancelled) setReuseTrace({ id, data });
      })
      .catch(() => {});
    api
      .getRelatedIdeas(id)
      .then((items) => {
        if (!cancelled) setRelatedIdeas({ id, items });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [id]);

  // 挂载时读取列表顺序快照（setState 放在异步回调里，react-hooks/set-state-in-effect）
  useEffect(() => {
    const timer = setTimeout(() => setListOrder(readIdeaListOrder()), 0);
    return () => clearTimeout(timer);
  }, []);

  const loadIdea = useCallback(
    async (silent = false) => {
      const seq = ++requestSeq.current;
      try {
        const data = await api.getIdea(id);
        if (seq !== requestSeq.current) return;
        setIdea(data);
        setError("");
      } catch (e) {
        if (seq !== requestSeq.current) return;
        if (e instanceof ApiError && e.status === 404) {
          setNotFound(true);
        } else if (!silent) {
          setError(e instanceof ApiError ? e.message : "加载失败，请稍后重试");
        }
      }
    },
    [id],
  );

  // AI 处理中时轮询，直到 done / failed
  const aiWorking =
    idea !== null &&
    (idea.ai_status === "pending" || idea.ai_status === "processing");
  useEffect(() => {
    if (!aiWorking) return;
    const timer = setInterval(() => {
      void loadIdea(true);
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [aiWorking, loadIdea]);

  async function handleRetryAI() {
    if (!idea || retrying) return;
    setRetrying(true);
    setActionError("");
    try {
      const updated = await api.retryIdeaAI(idea.id);
      requestSeq.current += 1; // 使用户操作结果优先于在途轮询响应
      setIdea(updated);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "重试失败，请稍后再试");
    } finally {
      setRetrying(false);
    }
  }

  async function handleProjectChange(projectId: string) {
    if (!idea) return;
    setActionError("");
    try {
      const updated = await api.updateIdea(idea.id, {
        project_id: projectId || null,
      });
      requestSeq.current += 1;
      setIdea(updated);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "更新项目失败");
    }
  }

  async function handleAcceptSuggestion() {
    if (!idea || !idea.ai_suggested_project || accepting) return;
    setAccepting(true);
    setActionError("");
    try {
      const name = idea.ai_suggested_project;
      let project = projects.find((p) => p.name === name);
      if (!project) {
        project = await api.createProject(name);
        setProjects((prev) => [...prev, project as Project]);
      }
      const updated = await api.updateIdea(idea.id, { project_id: project.id });
      requestSeq.current += 1;
      setIdea(updated);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "归入项目失败");
    } finally {
      setAccepting(false);
    }
  }

  async function handleDelete() {
    if (!idea || deleting) return;
    if (!window.confirm("确定删除这条灵感吗？删除后无法恢复。")) return;
    setDeleting(true);
    setActionError("");
    try {
      await api.deleteIdea(idea.id);
      router.push("/");
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "删除失败");
      setDeleting(false);
    }
  }

  // T1.1：复用确认入口——复用率的分子全靠用户主动确认。used → captured 为「取消标记」
  async function handleToggleUsed() {
    if (!idea || markingUsed) return;
    const next = idea.status === "used" ? "captured" : "used";
    setMarkingUsed(true);
    setActionError("");
    try {
      const updated = await api.updateIdea(idea.id, { status: next });
      requestSeq.current += 1; // 用户操作结果优先于在途轮询响应
      setIdea(updated);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "标记失败，请稍后重试");
    } finally {
      setMarkingUsed(false);
    }
  }

  // 返回列表：优先浏览器返回以保留列表滚动位置与已加载分页（T4.5）；
  // 直接打开详情（新标签页等无来源场景）时回首页
  function handleBack() {
    if (window.history.length > 1) {
      router.back();
    } else {
      router.push("/");
    }
  }

  if (notFound) {
    return (
      <div className="py-16 text-center">
        <p className="text-ink-muted">这条灵感不存在或已被删除。</p>
        <Link
          href="/"
          className="mt-4 inline-block text-sm text-primary hover:underline"
        >
          ← 返回列表
        </Link>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4 py-8">
        <ErrorBanner message={error} onRetry={() => void loadIdea()} />
        <Link href="/" className="inline-block text-sm text-primary hover:underline">
          ← 返回列表
        </Link>
      </div>
    );
  }

  if (!idea) {
    return <p className="py-16 text-center text-sm text-ink-faint">加载中…</p>;
  }

  const showSuggestion =
    idea.ai_suggested_project !== null &&
    idea.project_id === null &&
    !suggestionDismissed;

  // 仅当数据对应当前 id 才使用（路由参数切换时不显示上一条的遗留数据）
  const trace = reuseTrace && reuseTrace.id === id ? reuseTrace.data : null;
  const related =
    relatedIdeas && relatedIdeas.id === id ? relatedIdeas.items : [];

  // 上一条/下一条（T4.5）：按列表页快照顺序；当前条不在快照中（直接打开等）则整体隐藏
  const orderIndex = listOrder.findIndex((entry) => entry.id === id);
  const prevEntry = orderIndex > 0 ? listOrder[orderIndex - 1] : null;
  const nextEntry =
    orderIndex >= 0 && orderIndex < listOrder.length - 1
      ? listOrder[orderIndex + 1]
      : null;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={handleBack}
          className="text-sm text-primary hover:underline"
        >
          ← 返回列表
        </button>
        <button
          type="button"
          onClick={() => void handleDelete()}
          disabled={deleting}
          className="rounded-md border border-error-border px-3 py-1.5 text-sm text-error transition-colors hover:bg-error-soft disabled:opacity-50"
        >
          {deleting ? "删除中…" : "删除"}
        </button>
      </div>

      {actionError && <ErrorBanner message={actionError} />}

      {/* 原文：只读，无任何编辑入口 */}
      <section className="rounded-xl border border-border bg-surface p-5">
        <div className="mb-3 flex items-center justify-between">
          <h1 className="text-sm font-semibold text-ink-strong">原文</h1>
          <span className="text-xs text-ink-faint">
            {formatDateTime(idea.created_at)} · 来源 {SOURCE_LABELS[idea.source] ?? idea.source}
          </span>
        </div>
        <p className="whitespace-pre-wrap text-base leading-relaxed text-ink">
          {idea.raw_content}
        </p>
      </section>

      {/* 复用确认（T1.1）：复用率的分子全靠用户主动确认，入口放在读完原文的位置。
          bg-success 配 text-success-soft：浅深两套主题下对比度均成立 */}
      <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface px-4 py-3">
        {idea.status === "used" ? (
          <>
            <p className="text-sm font-medium text-success">已标记为「已复用」</p>
            <button
              type="button"
              onClick={() => void handleToggleUsed()}
              disabled={markingUsed}
              className="rounded-md border border-border px-3 py-1.5 text-sm text-ink-secondary transition-colors hover:bg-fill-soft disabled:opacity-50"
            >
              {markingUsed ? "处理中…" : "取消标记"}
            </button>
          </>
        ) : (
          <>
            <p className="text-sm text-ink-muted">
              这条灵感在实际项目里用上了吗？
            </p>
            <button
              type="button"
              onClick={() => void handleToggleUsed()}
              disabled={markingUsed}
              className="rounded-md bg-success px-3 py-1.5 text-sm font-medium text-success-soft transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {markingUsed ? "标记中…" : "标为已复用"}
            </button>
          </>
        )}
      </section>

      {/* 复用档案（T1.1）：从未被 Agent 检索过则不渲染，避免噪音 */}
      {trace && trace.retrieved_count > 0 && (
        <section className="rounded-xl border border-border bg-surface p-5">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h2 className="text-sm font-semibold text-ink-strong">复用档案</h2>
            <p className="text-xs text-ink-faint">
              累计被 Agent 检索{" "}
              <span className="font-medium text-ink-secondary">
                {trace.retrieved_count}
              </span>{" "}
              次
              {trace.last_retrieved_at &&
                ` · 最近一次 ${relativeTime(trace.last_retrieved_at)}`}
            </p>
          </div>
          {trace.events.length > 0 && (
            <ul className="space-y-1.5">
              {trace.events.map((event, index) => (
                <li
                  key={`${event.at}-${index}`}
                  className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs"
                >
                  <span className="text-ink-faint">{relativeTime(event.at)}</span>
                  <span className="font-medium text-ink-secondary">
                    {event.agent_name}
                  </span>
                  <code className="text-primary">{event.tool_name}</code>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* AI 推断 */}
      <section className="relative rounded-xl border border-primary-soft-hover bg-primary-soft/40 p-5">
        <div className="mb-3 flex items-center gap-2">
          <span className="rounded-md bg-primary px-2 py-0.5 text-xs font-medium text-white">
            AI 推断
          </span>
          {idea.ai_confidence !== null && (
            <span className="text-xs text-primary">
              置信度 {Math.round(idea.ai_confidence * 100)}%
            </span>
          )}
        </div>

        {idea.ai_status === "pending" || idea.ai_status === "processing" ? (
          <p className="flex items-center gap-2 text-sm text-primary">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary-pulse" />
            AI 正在分析这条灵感…
          </p>
        ) : idea.ai_status === "failed" ? (
          <div className="space-y-2">
            <p className="text-sm text-error">
              AI 分析失败{idea.ai_error ? `：${idea.ai_error}` : "。"}
            </p>
            <button
              type="button"
              onClick={() => void handleRetryAI()}
              disabled={retrying}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:opacity-50"
            >
              {retrying ? "重试中…" : "重试"}
            </button>
          </div>
        ) : (
          <dl className="space-y-3 text-sm">
            {idea.ai_title && (
              <div>
                <dt className="text-xs text-primary-faint">标题</dt>
                <dd className="mt-0.5 font-medium text-ink-strong">{idea.ai_title}</dd>
              </div>
            )}
            {idea.ai_summary && (
              <div>
                <dt className="text-xs text-primary-faint">摘要</dt>
                <dd className="mt-0.5 leading-relaxed text-ink">{idea.ai_summary}</dd>
              </div>
            )}
            {idea.ai_maturity && (
              <div>
                <dt className="text-xs text-primary-faint">成熟度</dt>
                <dd className="mt-0.5 text-ink">{idea.ai_maturity}</dd>
              </div>
            )}
            {idea.ai_key_assumption && (
              <div>
                <dt className="text-xs text-primary-faint">待验证假设</dt>
                <dd className="mt-0.5 leading-relaxed text-ink">
                  {idea.ai_key_assumption}
                </dd>
              </div>
            )}
            {idea.tags.length > 0 && (
              <div>
                <dt className="text-xs text-primary-faint">标签</dt>
                <dd className="mt-1 flex flex-wrap gap-1.5">
                  {idea.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-surface px-2 py-0.5 text-xs text-ink-secondary ring-1 ring-primary-soft-hover"
                    >
                      {tag}
                    </span>
                  ))}
                </dd>
              </div>
            )}
          </dl>
        )}
      </section>

      {/* AI 建议项目 */}
      {showSuggestion && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-warning-border bg-warning-soft px-4 py-3 text-sm">
          <span className="text-warning-strong">
            AI 建议归入项目：{idea.ai_suggested_project}
          </span>
          <div className="ml-auto flex gap-2">
            <button
              type="button"
              onClick={() => void handleAcceptSuggestion()}
              disabled={accepting}
              className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-primary-hover disabled:opacity-50"
            >
              {accepting ? "处理中…" : "接受"}
            </button>
            <button
              type="button"
              onClick={() => setSuggestionDismissed(true)}
              className="rounded-md border border-border-strong bg-surface px-3 py-1 text-xs text-ink-secondary transition-colors hover:bg-fill-soft"
            >
              忽略
            </button>
          </div>
        </div>
      )}

      {/* 项目归属 */}
      <section className="flex items-center gap-3 rounded-xl border border-border bg-surface px-4 py-3">
        <label htmlFor="project-select" className="shrink-0 text-sm text-ink-muted">
          所属项目
        </label>
        <select
          id="project-select"
          value={idea.project_id ?? ""}
          onChange={(e) => void handleProjectChange(e.target.value)}
          className="w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm text-ink focus:border-primary-border focus:outline-none"
        >
          <option value="">无项目</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </section>

      {/* 相关灵感（T1.3）：空数组（含目标无 embedding）时静默隐藏 */}
      {related.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-ink-strong">相关灵感</h2>
          <ul className="space-y-2">
            {related.map((rel) => (
              <li key={rel.id}>
                <Link
                  href={`/ideas/${rel.id}`}
                  className="block rounded-xl border border-border bg-surface px-4 py-3 transition-colors hover:border-primary-onsoft hover:bg-primary-soft/30"
                >
                  <p className="text-sm font-medium leading-snug text-ink-strong">
                    {rel.ai_status === "done" && rel.ai_title
                      ? rel.ai_title
                      : truncate(rel.raw_content, 50)}
                  </p>
                  <p className="mt-1 text-xs text-ink-faint">
                    {relativeTime(rel.created_at)}
                    {rel.project_name && ` · ${rel.project_name}`}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* 上一条 / 下一条（T4.5）：无相邻条目时禁用；当前条不在快照中则整组隐藏 */}
      {orderIndex >= 0 && (
        <nav aria-label="顺序浏览" className="flex items-center justify-between gap-2 pt-1">
          {prevEntry ? (
            <Link
              href={`/ideas/${prevEntry.id}`}
              title={prevEntry.title}
              className="max-w-[45%] truncate rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-ink-secondary transition-colors hover:bg-fill-soft"
            >
              ← 上一条
            </Link>
          ) : (
            <span
              aria-disabled="true"
              className="rounded-md border border-border-soft px-3 py-1.5 text-sm text-ink-faint"
            >
              ← 上一条
            </span>
          )}
          {nextEntry ? (
            <Link
              href={`/ideas/${nextEntry.id}`}
              title={nextEntry.title}
              className="max-w-[45%] truncate rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-ink-secondary transition-colors hover:bg-fill-soft"
            >
              下一条 →
            </Link>
          ) : (
            <span
              aria-disabled="true"
              className="rounded-md border border-border-soft px-3 py-1.5 text-sm text-ink-faint"
            >
              下一条 →
            </span>
          )}
        </nav>
      )}
    </div>
  );
}
