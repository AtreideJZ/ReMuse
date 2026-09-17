"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Idea, Project, TagItem } from "@/lib/types";
import {
  addSearchHistory,
  clearSearchHistory,
  readSearchHistory,
  removeSearchHistory,
} from "@/lib/search-history";
import { IdeaCard } from "@/components/idea-card";
import { ErrorBanner } from "@/components/error-banner";

const DAY_OPTIONS = [
  { value: "", label: "全部时间" },
  { value: "7", label: "最近 7 天" },
  { value: "30", label: "最近 30 天" },
] as const;

/** 首屏兜底（T4.1）：从未被唤醒（captured）的灵感中随机抽取的条数 */
const FALLBACK_POOL_SIZE = 50;
const FALLBACK_PICK = 3;

/** 洗牌后取前 n 条（用于兜底内容随机抽取） */
function pickRandom(items: Idea[], n: number): Idea[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy.slice(0, n);
}

interface SearchFilters {
  q: string;
  projectId: string;
  tag: string;
  days: string;
}

export default function SearchPage() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [projectFilter, setProjectFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [days, setDays] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [tags, setTags] = useState<TagItem[]>([]);
  // null 表示尚未搜索
  const [results, setResults] = useState<Idea[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  // 首屏兜底内容（T4.1）与搜索历史（T4.2），仅在未搜索时展示
  const [fallback, setFallback] = useState<Idea[]>([]);
  const [history, setHistory] = useState<string[]>([]);
  // 在途请求控制器：新搜索发起时 abort 旧的，消除「筛选 B 结果 A」竞态
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    api
      .listProjects()
      .then((data) => setProjects(data.items))
      .catch(() => setProjects([]));
    api
      .listTags()
      .then((data) => setTags(data.items))
      .catch(() => setTags([]));
    // 兜底内容加载失败不阻断搜索功能，保持空数组静默降级
    api
      .listIdeas({ status: "captured", limit: FALLBACK_POOL_SIZE })
      .then((data) => setFallback(pickRandom(data.items, FALLBACK_PICK)))
      .catch(() => {});
    // 历史读取放进异步回调（react-hooks/set-state-in-effect）
    const timer = setTimeout(() => setHistory(readSearchHistory()), 0);
    return () => clearTimeout(timer);
  }, []);

  // 卸载时取消在途搜索
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  async function runSearch(filters: SearchFilters) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError("");
    try {
      const data = await api.searchIdeas(
        {
          q: filters.q,
          project_id: filters.projectId || undefined,
          tag: filters.tag || undefined,
          days: filters.days ? Number(filters.days) : undefined,
          limit: 20,
        },
        controller.signal,
      );
      if (abortRef.current !== controller) return;
      setResults(data);
      // 搜索成功后记入历史（去重置顶，最多 8 条）
      setHistory(addSearchHistory(filters.q));
    } catch (e) {
      if (e instanceof ApiError && e.aborted) return;
      if (abortRef.current !== controller) return;
      setError(e instanceof ApiError ? e.message : "搜索失败，请稍后重试");
    } finally {
      if (abortRef.current === controller) setLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;
    setQuery(trimmed);
    void runSearch({
      q: trimmed,
      projectId: projectFilter,
      tag: tagFilter,
      days,
    });
  }

  // 已搜索过的情况下，筛选变化立即重新搜索（旧请求会被 abort）
  function handleFilterChange(kind: "projectId" | "tag" | "days", value: string) {
    const next: SearchFilters = {
      q: query,
      projectId: kind === "projectId" ? value : projectFilter,
      tag: kind === "tag" ? value : tagFilter,
      days: kind === "days" ? value : days,
    };
    if (kind === "projectId") setProjectFilter(value);
    if (kind === "tag") setTagFilter(value);
    if (kind === "days") setDays(value);
    if (query) {
      void runSearch(next);
    }
  }

  // 点击历史词即重搜（T4.2）：回填输入框并沿用当前筛选
  function handleHistoryClick(q: string) {
    setInput(q);
    setQuery(q);
    void runSearch({ q, projectId: projectFilter, tag: tagFilter, days });
  }

  // 零结果降级（T4.3）：一键清空筛选后按当前查询词重搜
  function handleClearFiltersAndResearch() {
    setProjectFilter("");
    setTagFilter("");
    setDays("");
    void runSearch({ q: query, projectId: "", tag: "", days: "" });
  }

  return (
    <div className="space-y-5">
      <form onSubmit={handleSubmit}>
        <div className="flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 shadow-sm focus-within:border-primary-border">
          <input
            type="search"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="试试模糊描述，例如：学生学习计划"
            aria-label="搜索灵感"
            className="min-w-0 flex-1 bg-transparent py-1.5 text-base text-ink-strong placeholder:text-ink-faint focus:outline-none"
          />
          <button
            type="submit"
            disabled={!input.trim() || loading}
            className="shrink-0 rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-border-strong"
          >
            搜索
          </button>
        </div>
      </form>

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={projectFilter}
          onChange={(e) => handleFilterChange("projectId", e.target.value)}
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
        <select
          value={tagFilter}
          onChange={(e) => handleFilterChange("tag", e.target.value)}
          aria-label="按标签筛选"
          className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm text-ink-secondary focus:border-primary-border focus:outline-none"
        >
          <option value="">全部标签</option>
          {tags.map((t) => (
            <option key={t.name} value={t.name}>
              {t.name}（{t.count}）
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
      </div>

      {error && (
        <ErrorBanner
          message={error}
          onRetry={() =>
            void runSearch({ q: query, projectId: projectFilter, tag: tagFilter, days })
          }
        />
      )}

      {loading ? (
        <p className="py-12 text-center text-sm text-ink-faint">搜索中…</p>
      ) : results === null ? (
        // 首屏（T4.1/T4.2）：搜索历史 + 待唤醒兜底内容；两者皆空时退回说明文字
        <div className="space-y-6">
          {history.length > 0 && (
            <section>
              <div className="mb-2 flex items-center justify-between">
                <h2 className="text-xs font-medium text-ink-faint">搜索历史</h2>
                <button
                  type="button"
                  onClick={() => {
                    clearSearchHistory();
                    setHistory([]);
                  }}
                  className="text-xs text-ink-faint transition-colors hover:text-ink-secondary"
                >
                  清空
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {history.map((q) => (
                  <span
                    key={q}
                    className="inline-flex items-center rounded-full bg-fill text-xs"
                  >
                    <button
                      type="button"
                      onClick={() => handleHistoryClick(q)}
                      className="py-1 pl-2.5 pr-1.5 text-ink-secondary transition-colors hover:text-ink-strong"
                    >
                      {q}
                    </button>
                    <button
                      type="button"
                      aria-label={`删除历史「${q}」`}
                      onClick={() => setHistory(removeSearchHistory(q))}
                      className="py-1 pl-0.5 pr-2 text-ink-faint transition-colors hover:text-error"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </section>
          )}
          {fallback.length > 0 && (
            <section className="space-y-3">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <h2 className="text-sm font-semibold text-ink-strong">
                  待唤醒的灵感
                </h2>
                <p className="text-xs text-ink-faint">
                  随机 {fallback.length} 条还未被找回过的记录，描述大意就能搜到它们
                </p>
              </div>
              {fallback.map((idea) => (
                <IdeaCard key={idea.id} idea={idea} />
              ))}
            </section>
          )}
          {history.length === 0 && fallback.length === 0 && (
            <div className="py-16 text-center">
              <p className="text-sm text-ink-muted">
                输入关键词或模糊描述，回车开始搜索。
              </p>
              <p className="mt-2 text-xs text-ink-faint">
                支持语义搜索：不必逐字匹配，描述大意也能命中相关灵感。
              </p>
            </div>
          )}
        </div>
      ) : results.length === 0 ? (
        <div className="py-12 text-center">
          <p className="text-sm text-ink-faint">没有找到相关灵感</p>
          <p className="mt-2 text-xs text-ink-faint">
            试试更宽泛的描述{projectFilter || tagFilter || days ? "，或放宽筛选条件" : ""}
          </p>
          {(projectFilter || tagFilter || days) && (
            <button
              type="button"
              onClick={handleClearFiltersAndResearch}
              className="mt-3 rounded-md border border-border px-3 py-1.5 text-sm text-ink-secondary transition-colors hover:bg-fill-soft"
            >
              清除筛选后重搜
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-ink-faint">
            「{query}」共 {results.length} 条结果，按相关度排序
          </p>
          {results.map((idea) => (
            <IdeaCard key={idea.id} idea={idea} />
          ))}
        </div>
      )}
    </div>
  );
}
