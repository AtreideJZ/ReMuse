"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Idea, Project, TagItem } from "@/lib/types";
import { writeIdeaListOrder } from "@/lib/idea-list-order";
import { CaptureBox } from "@/components/capture-box";
import { IdeaCard, type AiEcho } from "@/components/idea-card";
import { AgentActivity } from "@/components/agent-activity";
import { ErrorBanner } from "@/components/error-banner";

const POLL_INTERVAL_MS = 4000;
const PAGE_SIZE = 50;
/** 「已记录 · AI 分析中」提示的停留时长 */
const SAVED_NOTICE_MS = 4000;
/** AI 完成回响（E2）在卡片内的停留时长 */
const ECHO_MS = 6000;

/** 挂载时读取 ?project=（项目卡片「查看灵感」的落点，T1.3）；无则空串 */
function readInitialProjectFilter(): string {
  if (typeof window === "undefined") return "";
  try {
    return new URLSearchParams(window.location.search).get("project") ?? "";
  } catch {
    return "";
  }
}

export default function HomePage() {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [total, setTotal] = useState(0);
  const [projects, setProjects] = useState<Project[]>([]);
  const [tags, setTags] = useState<TagItem[]>([]);
  const [projectFilter, setProjectFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  // 保存成功后的短暂提示与刚插入的卡片 id（用于淡入）
  const [savedNotice, setSavedNotice] = useState("");
  const [lastSavedId, setLastSavedId] = useState<string | null>(null);
  // 请求序号：每次发起自增，响应落地前校验，防止旧响应覆盖新状态
  const requestSeq = useRef(0);
  const noticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // E2：AI 完成回响。仅对本次会话新建（经过 handleSaved）的条目触发，一次性；
  // 刷新页面后历史条目不触发（sessionNewIds 随挂载重建）
  const [aiEchoes, setAiEchoes] = useState<Record<string, AiEcho>>({});
  const sessionNewIdsRef = useRef<Set<string>>(new Set());
  const echoShownRef = useRef<Set<string>>(new Set());
  const echoTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(
    new Map(),
  );
  // ideas 的 ref 镜像：轮询响应落地时对比 ai_status 迁移用
  const ideasRef = useRef<Idea[]>([]);
  useEffect(() => {
    ideasRef.current = ideas;
  }, [ideas]);
  useEffect(() => {
    const echoTimers = echoTimersRef.current;
    return () => {
      if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
      for (const t of echoTimers.values()) clearTimeout(t);
    };
  }, []);

  // E2：卡内回响一次性展示，约 6 秒后自动消失（仅 done/failed 迁移瞬间调用）
  const showEcho = useCallback((idea: Idea, kind: AiEcho["kind"]) => {
    echoShownRef.current.add(idea.id);
    setAiEchoes((prev) => ({
      ...prev,
      [idea.id]: { kind, title: idea.ai_title },
    }));
    const timer = setTimeout(() => {
      setAiEchoes((prev) => {
        const next = { ...prev };
        delete next[idea.id];
        return next;
      });
      echoTimersRef.current.delete(idea.id);
    }, ECHO_MS);
    echoTimersRef.current.set(idea.id, timer);
  }, []);

  // 挂载时读取 ?project= 作为初始筛选（T1.3，项目卡片的落点）。
  // 不用 useState 初始化函数：首页是静态预渲染，客户端初始值若与服务端 HTML
  // 不一致会导致 hydration 不匹配；首帧后设置即可，列表 effect 会随筛选变化重取
  useEffect(() => {
    const timer = setTimeout(() => {
      const initial = readInitialProjectFilter();
      if (initial) setProjectFilter(initial);
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  // 列表顺序快照（T4.5）：供详情页「上一条 / 下一条」按当前列表顺序浏览
  useEffect(() => {
    writeIdeaListOrder(ideas);
  }, [ideas]);

  // 首次加载与筛选变化时刷新列表（回到第一页；setState 只发生在异步回调里）
  useEffect(() => {
    const seq = ++requestSeq.current;
    let cancelled = false;
    api
      .listIdeas({
        project_id: projectFilter || undefined,
        tag: tagFilter || undefined,
        limit: PAGE_SIZE,
      })
      .then((data) => {
        if (cancelled || seq !== requestSeq.current) return;
        setIdeas(data.items);
        setTotal(data.total);
        setError("");
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (cancelled || seq !== requestSeq.current) return;
        setError(e instanceof ApiError ? e.message : "加载失败，请稍后重试");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectFilter, tagFilter]);

  useEffect(() => {
    api
      .listProjects()
      .then((data) => setProjects(data.items))
      .catch(() => setProjects([]));
    api
      .listTags()
      .then((data) => setTags(data.items))
      .catch(() => setTags([]));
  }, []);

  const loadIdeas = useCallback(
    async (silent = false) => {
      const seq = ++requestSeq.current;
      if (!silent) setLoading(true);
      try {
        const data = await api.listIdeas({
          project_id: projectFilter || undefined,
          tag: tagFilter || undefined,
          limit: PAGE_SIZE,
        });
        if (seq !== requestSeq.current) return;
        // E2：检测本次会话新建条目的 AI 状态迁移（pending/processing → done/failed），
        // 在数据到达时（事件语境）出回响，而非在 effect 里
        const prevStatusById = new Map(
          ideasRef.current.map((item) => [item.id, item.ai_status]),
        );
        for (const item of data.items) {
          if (!sessionNewIdsRef.current.has(item.id)) continue;
          if (echoShownRef.current.has(item.id)) continue;
          const prev = prevStatusById.get(item.id);
          if (
            (prev === "pending" || prev === "processing") &&
            (item.ai_status === "done" || item.ai_status === "failed")
          ) {
            showEcho(item, item.ai_status);
          }
        }
        if (silent) {
          // 静默刷新（T3.1）：只拉第一页并与现有列表按 id 合并——新条目进头部、
          // 已有条目用新数据覆盖（ai_status 等）、已加载的尾部原样保留，
          // 不再整体替换导致「加载更多」的窗口被截断
          setIdeas((prev) => {
            const freshIds = new Set(data.items.map((item) => item.id));
            const tail = prev.filter((item) => !freshIds.has(item.id));
            return [...data.items, ...tail];
          });
        } else {
          setIdeas(data.items);
        }
        setTotal(data.total);
        setError("");
      } catch (e) {
        if (seq !== requestSeq.current || silent) return;
        setError(e instanceof ApiError ? e.message : "加载失败，请稍后重试");
      } finally {
        if (seq === requestSeq.current && !silent) setLoading(false);
      }
    },
    [projectFilter, tagFilter, showEcho],
  );

  // T2.7：保存成功后乐观插入列表头部 + 短暂提示；loadIdeas(true) 作兜底一致性校验
  const handleSaved = useCallback(
    (idea?: Idea) => {
      if (idea) {
        // 顶掉在途请求，防止旧响应覆盖刚插入的卡片
        requestSeq.current += 1;
        // E2：登记本次会话新建条目，其 AI 状态迁移才会触发卡内回响
        sessionNewIdsRef.current.add(idea.id);
        const matchesFilter =
          (!projectFilter || idea.project_id === projectFilter) &&
          (!tagFilter || idea.tags.includes(tagFilter));
        if (matchesFilter) {
          setIdeas((prev) => [idea, ...prev]);
          setTotal((prev) => prev + 1);
        }
        setLastSavedId(idea.id);
        setSavedNotice("已记录 · AI 分析中");
        if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
        noticeTimerRef.current = setTimeout(
          () => setSavedNotice(""),
          SAVED_NOTICE_MS,
        );
      }
      void loadIdeas(true);
    },
    [loadIdeas, projectFilter, tagFilter],
  );

  // E2 失败分支：卡内重试入口。清掉回响记录，让重试后的完成再次出回响
  async function handleRetryAI(ideaId: string) {
    try {
      const updated = await api.retryIdeaAI(ideaId);
      echoShownRef.current.delete(ideaId);
      const timer = echoTimersRef.current.get(ideaId);
      if (timer) {
        clearTimeout(timer);
        echoTimersRef.current.delete(ideaId);
      }
      setAiEchoes((prev) => {
        const next = { ...prev };
        delete next[ideaId];
        return next;
      });
      // 立即把 pending 状态合入列表，轮询会继续直到 done/failed
      requestSeq.current += 1;
      setIdeas((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "重试失败，请稍后再试");
    }
  }

  // T3.4：加载更多（offset 分页 + 请求序号校验，同日志页模式）
  function handleLoadMore() {
    if (loadingMore) return;
    const seq = ++requestSeq.current;
    setLoadingMore(true);
    api
      .listIdeas({
        project_id: projectFilter || undefined,
        tag: tagFilter || undefined,
        limit: PAGE_SIZE,
        offset: ideas.length,
      })
      .then((data) => {
        if (seq !== requestSeq.current) return;
        // 按 id 去重（T3.2）：offset 分页期间有新记录插入时窗口滑动会产生重复条目
        setIdeas((prev) => {
          const seen = new Set(prev.map((item) => item.id));
          return [...prev, ...data.items.filter((item) => !seen.has(item.id))];
        });
        setTotal(data.total);
        setLoadingMore(false);
      })
      .catch((e: unknown) => {
        if (seq !== requestSeq.current) return;
        setError(e instanceof ApiError ? e.message : "加载失败，请稍后重试");
        setLoadingMore(false);
      });
  }

  // 有待处理（pending/processing）的条目时轮询刷新，直到全部完成或失败
  const hasPending = ideas.some(
    (idea) => idea.ai_status === "pending" || idea.ai_status === "processing",
  );
  useEffect(() => {
    if (!hasPending) return;
    const timer = setInterval(() => {
      void loadIdeas(true);
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [hasPending, loadIdeas]);

  const hasMore = ideas.length < total;

  return (
    <div className="space-y-6">
      {/* 乐观插入卡片的淡入动画；prefers-reduced-motion 下不启用（T2.7） */}
      <style>{`
        @keyframes remuse-idea-fade-in {
          from { opacity: 0; transform: translateY(-4px); }
          to { opacity: 1; transform: none; }
        }
        @media (prefers-reduced-motion: no-preference) {
          .remuse-idea-fade-in { animation: remuse-idea-fade-in 240ms ease-out; }
        }
      `}</style>

      <CaptureBox projects={projects} onSaved={handleSaved} />
      {savedNotice && (
        <p role="status" className="-mt-3 text-xs text-success">
          {savedNotice}
        </p>
      )}

      <AgentActivity />

      {(projects.length > 0 || tags.length > 0) && (
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={projectFilter}
            onChange={(e) => setProjectFilter(e.target.value)}
            aria-label="按项目筛选"
            className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm text-ink-secondary focus:border-primary-border focus:outline-none"
          >
            <option value="">全部项目</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          {tags.map((t) => {
            const active = tagFilter === t.name;
            return (
              <button
                key={t.name}
                type="button"
                onClick={() => setTagFilter(active ? "" : t.name)}
                className={`rounded-full px-2.5 py-1 text-xs transition-colors ${
                  active
                    ? "bg-primary text-white"
                    : "bg-fill text-ink-secondary hover:bg-fill-hover"
                }`}
              >
                {t.name}
                <span className={active ? "text-primary-onsoft" : "text-ink-faint"}>
                  {" "}
                  {t.count}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {error && <ErrorBanner message={error} onRetry={() => void loadIdeas()} />}

      {loading ? (
        <p className="py-12 text-center text-sm text-ink-faint">加载中…</p>
      ) : ideas.length === 0 ? (
        projectFilter || tagFilter ? (
          <div className="py-12 text-center">
            <p className="text-sm text-ink-faint">没有符合筛选条件的灵感</p>
            <button
              type="button"
              onClick={() => {
                setProjectFilter("");
                setTagFilter("");
              }}
              className="mt-3 rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-ink-secondary transition-colors hover:bg-fill-soft"
            >
              清除筛选
            </button>
          </div>
        ) : (
          // E6：空态预告机制——记录与找回两个语义都在
          <div className="py-12 text-center">
            <p className="text-sm text-ink-secondary">还没有灵感。</p>
            <p className="mt-1.5 text-sm text-ink-faint">
              写下第一条——过些日子，Agent 会替你把它找回来。
            </p>
          </div>
        )
      ) : (
        <div className="space-y-3">
          {ideas.map((idea) => (
            <div
              key={idea.id}
              className={
                idea.id === lastSavedId ? "remuse-idea-fade-in" : undefined
              }
            >
              <IdeaCard
                idea={idea}
                aiEcho={aiEchoes[idea.id]}
                onRetryAI={(ideaId) => void handleRetryAI(ideaId)}
              />
            </div>
          ))}
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
