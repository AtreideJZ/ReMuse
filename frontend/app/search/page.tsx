"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Idea, Project, TagItem } from "@/lib/types";
import { IdeaCard } from "@/components/idea-card";
import { ErrorBanner } from "@/components/error-banner";

const DAY_OPTIONS = [
  { value: "", label: "全部时间" },
  { value: "7", label: "最近 7 天" },
  { value: "30", label: "最近 30 天" },
] as const;

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
        <div className="py-16 text-center">
          <p className="text-sm text-ink-muted">
            输入关键词或模糊描述，回车开始搜索。
          </p>
          <p className="mt-2 text-xs text-ink-faint">
            支持语义搜索：不必逐字匹配，描述大意也能命中相关灵感。
          </p>
        </div>
      ) : results.length === 0 ? (
        <p className="py-12 text-center text-sm text-ink-faint">
          没有找到相关灵感
        </p>
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
