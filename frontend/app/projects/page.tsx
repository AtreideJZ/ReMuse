"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { Project } from "@/lib/types";
import { formatDateTime } from "@/lib/time";
import { ErrorBanner } from "@/components/error-banner";

export default function ProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState("");

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const editNameInputRef = useRef<HTMLInputElement>(null);

  // 首次加载（setState 只发生在异步回调里）
  useEffect(() => {
    let cancelled = false;
    api
      .listProjects()
      .then((data) => {
        if (cancelled) return;
        setProjects(data.items);
        setError("");
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : "加载失败，请稍后重试");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 进入行内编辑时聚焦名称输入框
  useEffect(() => {
    if (editingId !== null) {
      editNameInputRef.current?.focus();
    }
  }, [editingId]);

  async function loadProjects() {
    try {
      const data = await api.listProjects();
      setProjects(data.items);
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "加载失败，请稍后重试");
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || creating) return;
    setCreating(true);
    setFormError("");
    try {
      await api.createProject(trimmed, description.trim());
      setName("");
      setDescription("");
      await loadProjects();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "创建失败，请稍后重试");
    } finally {
      setCreating(false);
    }
  }

  function startEdit(project: Project) {
    setEditingId(project.id);
    setEditName(project.name);
    setEditDescription(project.description);
    setFormError("");
  }

  async function handleSaveEdit(projectId: string) {
    const trimmed = editName.trim();
    if (!trimmed || savingEdit) return;
    setSavingEdit(true);
    setFormError("");
    try {
      await api.updateProject(projectId, {
        name: trimmed,
        description: editDescription.trim(),
      });
      setEditingId(null);
      await loadProjects();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "保存失败，请稍后重试");
    } finally {
      setSavingEdit(false);
    }
  }

  async function handleDelete(project: Project) {
    const ok = window.confirm(
      `确定删除项目「${project.name}」吗？\n项目下 ${project.idea_count} 条灵感将转为无项目，不会被删除。`,
    );
    if (!ok) return;
    setFormError("");
    try {
      await api.deleteProject(project.id);
      await loadProjects();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "删除失败，请稍后重试");
    }
  }

  return (
    <div className="space-y-6">
      {/* 创建项目 */}
      <form
        onSubmit={(e) => void handleCreate(e)}
        className="space-y-3 rounded-xl border border-border bg-surface p-4"
      >
        <h1 className="text-sm font-semibold text-ink-strong">新建项目</h1>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="项目名称"
          maxLength={100}
          className="block w-full rounded-md border border-border px-3 py-2 text-sm text-ink-strong placeholder:text-ink-faint focus:border-primary-border focus:outline-none"
        />
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="项目描述（可选）"
          rows={2}
          className="block w-full resize-none rounded-md border border-border px-3 py-2 text-sm text-ink-strong placeholder:text-ink-faint focus:border-primary-border focus:outline-none"
        />
        <div className="flex items-center justify-between">
          {formError ? (
            <span className="text-xs text-error">{formError}</span>
          ) : (
            <span />
          )}
          <button
            type="submit"
            disabled={!name.trim() || creating}
            className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-border-strong"
          >
            {creating ? "创建中…" : "创建项目"}
          </button>
        </div>
      </form>

      {error && <ErrorBanner message={error} onRetry={() => void loadProjects()} />}

      {loading ? (
        <p className="py-12 text-center text-sm text-ink-faint">加载中…</p>
      ) : projects.length === 0 ? (
        <p className="py-12 text-center text-sm text-ink-faint">
          还没有项目，先创建一个吧。
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {projects.map((project) => (
            <div
              key={project.id}
              // 整卡可点击进入首页按该项目筛选（T1.3）；行内编辑态下禁用跳转
              onClick={
                editingId === project.id
                  ? undefined
                  : () => router.push(`/?project=${project.id}`)
              }
              onKeyDown={
                editingId === project.id
                  ? undefined
                  : (e) => {
                      // 仅当焦点在卡片本体上时响应；内部按钮的 Enter 会冒泡至此，须排除
                      if (e.key === "Enter" && e.target === e.currentTarget) {
                        router.push(`/?project=${project.id}`);
                      }
                    }
              }
              role={editingId === project.id ? undefined : "link"}
              tabIndex={editingId === project.id ? undefined : 0}
              className={`rounded-xl border border-border bg-surface p-4${
                editingId === project.id
                  ? ""
                  : " cursor-pointer transition-colors hover:border-primary-onsoft hover:bg-primary-soft/30"
              }`}
            >
              {editingId === project.id ? (
                <div
                  className="space-y-2"
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setEditingId(null);
                  }}
                >
                  <input
                    ref={editNameInputRef}
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    maxLength={100}
                    aria-label="项目名称"
                    className="block w-full rounded-md border border-border px-2.5 py-1.5 text-sm text-ink-strong focus:border-primary-border focus:outline-none"
                  />
                  <textarea
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    rows={2}
                    placeholder="项目描述（可选）"
                    aria-label="项目描述"
                    className="block w-full resize-none rounded-md border border-border px-2.5 py-1.5 text-sm text-ink-strong placeholder:text-ink-faint focus:border-primary-border focus:outline-none"
                  />
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => setEditingId(null)}
                      className="rounded-md border border-border px-3 py-1 text-xs text-ink-secondary transition-colors hover:bg-fill-soft"
                    >
                      取消
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleSaveEdit(project.id)}
                      disabled={!editName.trim() || savingEdit}
                      className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-primary-hover disabled:bg-border-strong"
                    >
                      {savingEdit ? "保存中…" : "保存"}
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="flex items-start justify-between gap-2">
                    <h2 className="min-w-0 flex-1 truncate text-base font-medium text-ink-strong">
                      {project.name}
                    </h2>
                    <span className="shrink-0 rounded-full bg-primary-soft px-2 py-0.5 text-xs text-primary">
                      {project.idea_count} 条灵感
                    </span>
                  </div>
                  {project.description && (
                    <p className="mt-1.5 line-clamp-3 text-sm text-ink-muted">
                      {project.description}
                    </p>
                  )}
                  <div className="mt-3 flex items-center justify-between">
                    <span className="text-xs text-ink-faint">
                      创建于 {formatDateTime(project.created_at)}
                    </span>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          startEdit(project);
                        }}
                        className="rounded-md border border-border px-2.5 py-1 text-xs text-ink-secondary transition-colors hover:bg-fill-soft"
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleDelete(project);
                        }}
                        className="rounded-md border border-error-border px-2.5 py-1 text-xs text-error transition-colors hover:bg-error-soft"
                      >
                        删除
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
