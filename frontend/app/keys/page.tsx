"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ApiKey, ApiKeyWithSecret, Project } from "@/lib/types";
import { formatDateTime } from "@/lib/time";
import { ErrorBanner } from "@/components/error-banner";

export default function KeysPage() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [name, setName] = useState("");
  const [withWrite, setWithWrite] = useState(false);
  const [selectedProjectIds, setSelectedProjectIds] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState("");

  const [createdKey, setCreatedKey] = useState<ApiKeyWithSecret | null>(null);
  const [copied, setCopied] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const createButtonRef = useRef<HTMLButtonElement>(null);
  const copyButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 首次加载（setState 只发生在异步回调里）
  useEffect(() => {
    let cancelled = false;
    api
      .listKeys()
      .then((data) => {
        if (cancelled) return;
        setKeys(data.items);
        setError("");
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : "加载失败，请稍后重试");
        setLoading(false);
      });
    api
      .listProjects()
      .then((data) => {
        if (!cancelled) setProjects(data.items);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // 弹窗可访问性：打开时聚焦「复制密钥」；Escape 关闭并归还焦点；Tab 在弹窗内循环
  useEffect(() => {
    if (!createdKey) return;
    copyButtonRef.current?.focus();

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setCreatedKey(null);
        createButtonRef.current?.focus();
        return;
      }
      if (e.key !== "Tab") return;
      const root = dialogRef.current;
      if (!root) return;
      const focusable = Array.from(
        root.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => !el.hasAttribute("disabled"));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [createdKey]);

  // 卸载时清理「已复制」提示的定时器
  useEffect(() => {
    return () => {
      if (copyTimerRef.current !== null) {
        clearTimeout(copyTimerRef.current);
      }
    };
  }, []);

  function closeCreatedKeyDialog() {
    setCreatedKey(null);
    createButtonRef.current?.focus();
  }

  function projectName(id: string): string {
    return projects.find((p) => p.id === id)?.name ?? "未知项目";
  }

  function toggleProject(id: string) {
    setSelectedProjectIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || creating) return;
    setCreating(true);
    setFormError("");
    try {
      const created = await api.createKey({
        name: trimmed,
        // read 为基础权限恒包含，write 可选（最小化授权）
        scopes: withWrite ? ["read", "write"] : ["read"],
        project_ids: selectedProjectIds,
      });
      setCreatedKey(created);
      setCopied(false);
      setName("");
      setWithWrite(false);
      setSelectedProjectIds([]);
      setKeys((prev) => [created, ...prev]);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "创建失败，请稍后重试");
    } finally {
      setCreating(false);
    }
  }

  async function handleCopy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      if (copyTimerRef.current !== null) {
        clearTimeout(copyTimerRef.current);
      }
      copyTimerRef.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt("自动复制失败，请手动复制：", text);
    }
  }

  async function handleRevoke(key: ApiKey) {
    if (revokingId) return;
    if (!window.confirm(`确定吊销密钥「${key.name}」吗？吊销后立即失效，且无法恢复。`)) {
      return;
    }
    setRevokingId(key.id);
    setFormError("");
    try {
      const revoked = await api.revokeKey(key.id);
      setKeys((prev) => prev.map((k) => (k.id === revoked.id ? revoked : k)));
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "吊销失败，请稍后重试");
    } finally {
      setRevokingId(null);
    }
  }

  return (
    <div className="space-y-6">
      {/* 创建密钥 */}
      <form
        onSubmit={(e) => void handleCreate(e)}
        className="space-y-3 rounded-xl border border-border bg-surface p-4"
      >
        <h1 className="text-sm font-semibold text-ink-strong">创建 API 密钥</h1>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="密钥名称（如：MCP 客户端）"
          maxLength={100}
          className="block w-full rounded-md border border-border px-3 py-2 text-sm text-ink-strong placeholder:text-ink-faint focus:border-primary-border focus:outline-none"
        />
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-ink-secondary">
          <span className="text-ink-muted">权限：</span>
          <label className="flex items-center gap-1.5 text-ink-faint">
            <input type="checkbox" checked disabled className="accent-primary" />
            读取（基础权限）
          </label>
          <label className="flex cursor-pointer items-center gap-1.5">
            <input
              type="checkbox"
              checked={withWrite}
              onChange={(e) => setWithWrite(e.target.checked)}
              className="accent-primary"
            />
            写入
          </label>
        </div>
        <div className="space-y-1.5 text-sm">
          <p className="text-ink-muted">
            授权项目：
            {selectedProjectIds.length === 0 && (
              <span className="text-ink-faint">未选择时授予全部项目</span>
            )}
          </p>
          {projects.length > 0 && (
            <div className="flex flex-wrap gap-x-4 gap-y-1.5">
              {projects.map((p) => (
                <label
                  key={p.id}
                  className="flex cursor-pointer items-center gap-1.5 text-ink-secondary"
                >
                  <input
                    type="checkbox"
                    checked={selectedProjectIds.includes(p.id)}
                    onChange={() => toggleProject(p.id)}
                    className="accent-primary"
                  />
                  {p.name}
                </label>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center justify-between">
          {formError ? (
            <span className="text-xs text-error">{formError}</span>
          ) : (
            <span />
          )}
          <button
            ref={createButtonRef}
            type="submit"
            disabled={!name.trim() || creating}
            className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-border-strong"
          >
            {creating ? "创建中…" : "创建密钥"}
          </button>
        </div>
      </form>

      {error && (
        <ErrorBanner
          message={error}
          onRetry={() => window.location.reload()}
        />
      )}

      {/* 密钥列表 */}
      {loading ? (
        <p className="py-12 text-center text-sm text-ink-faint">加载中…</p>
      ) : keys.length === 0 ? (
        <p className="py-12 text-center text-sm text-ink-faint">
          还没有 API 密钥，先创建一个吧。
        </p>
      ) : (
        <div className="space-y-3">
          {keys.map((key) => {
            const revoked = key.revoked_at !== null;
            return (
              <div
                key={key.id}
                className={`rounded-xl border bg-surface p-4 ${
                  revoked ? "border-border-soft opacity-60" : "border-border"
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-base font-medium text-ink-strong">{key.name}</h2>
                  <code className="rounded bg-fill px-1.5 py-0.5 text-xs text-ink-muted">
                    {key.prefix}…
                  </code>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      key.scopes.includes("write")
                        ? "bg-warning-soft text-warning"
                        : "bg-success-soft text-success"
                    }`}
                  >
                    {key.scopes.includes("write") ? "读写" : "只读"}
                  </span>
                  {revoked ? (
                    <span className="rounded-full bg-fill px-2 py-0.5 text-xs text-ink-muted">
                      已吊销
                    </span>
                  ) : (
                    <span className="rounded-full bg-primary-soft px-2 py-0.5 text-xs text-primary">
                      有效
                    </span>
                  )}
                  {!revoked && (
                    <button
                      type="button"
                      onClick={() => void handleRevoke(key)}
                      disabled={revokingId === key.id}
                      className="ml-auto rounded-md border border-error-border px-2.5 py-1 text-xs text-error transition-colors hover:bg-error-soft disabled:opacity-50"
                    >
                      {revokingId === key.id ? "吊销中…" : "吊销"}
                    </button>
                  )}
                </div>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-faint">
                  <span>
                    授权范围：
                    {key.project_ids.length === 0
                      ? "全部项目"
                      : key.project_ids.map(projectName).join("、")}
                  </span>
                  <span>创建于 {formatDateTime(key.created_at)}</span>
                  {revoked && key.revoked_at && (
                    <span>吊销于 {formatDateTime(key.revoked_at)}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 创建成功弹窗：完整密钥仅此一次显示 */}
      {createdKey && (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/40 p-4">
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="created-key-dialog-title"
            className="w-full max-w-md rounded-xl bg-surface p-5 shadow-xl"
          >
            <h2
              id="created-key-dialog-title"
              className="text-base font-semibold text-ink-strong"
            >
              密钥「{createdKey.name}」创建成功
            </h2>
            <p className="mt-2 rounded-md border border-warning-border bg-warning-soft px-3 py-2 text-xs text-warning-strong">
              完整密钥仅此一次显示，关闭后无法再次查看，请立即复制并妥善保存。
            </p>
            <code className="mt-3 block break-all rounded-md bg-fill px-3 py-2.5 text-sm text-ink">
              {createdKey.key}
            </code>
            <div className="mt-4 flex justify-end gap-2">
              <button
                ref={copyButtonRef}
                type="button"
                onClick={() => void handleCopy(createdKey.key)}
                className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-primary-hover"
              >
                {copied ? "已复制" : "复制密钥"}
              </button>
              <button
                type="button"
                onClick={closeCreatedKeyDialog}
                className="rounded-md border border-border px-4 py-1.5 text-sm text-ink-secondary transition-colors hover:bg-fill-soft"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
