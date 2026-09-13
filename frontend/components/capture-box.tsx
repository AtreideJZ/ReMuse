"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import {
  addDraft,
  clearCaptureDraft,
  draftCount,
  readCaptureDraft,
  readDrafts,
  removeDraftAt,
  writeCaptureDraft,
} from "@/lib/offline-drafts";
import type { Idea, Project } from "@/lib/types";

interface CaptureBoxProps {
  projects: Project[];
  /** 保存成功后回调；在线保存带新建对象（供乐观插入），离线补发等场景不带 */
  onSaved: (idea?: Idea) => void;
}

function autoResize(el: HTMLTextAreaElement) {
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
}

export function CaptureBox({ projects, onSaved }: CaptureBoxProps) {
  const [content, setContent] = useState("");
  const [projectId, setProjectId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pendingDrafts, setPendingDrafts] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // 输入即存的 debounce 计时器（T2.2）
  const draftTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // onSaved 经 ref 使用，避免父组件重渲染导致同步 effect 反复执行
  const onSavedRef = useRef(onSaved);
  useEffect(() => {
    onSavedRef.current = onSaved;
  });

  // 挂载：回填未提交草稿（优先）或 URL ?text= 预填，再按端型聚焦（T2.1 / T2.2 / T2.5）
  // setState 统一放在异步回调里（react-hooks/set-state-in-effect）
  useEffect(() => {
    const timer = setTimeout(() => {
      const params = new URLSearchParams(window.location.search);
      const draft = readCaptureDraft();
      const prefill = (params.get("text") ?? "").trim();
      if (draft.trim().length > 0) {
        setContent(draft);
        setNotice("已恢复未提交的内容");
      } else if (prefill.length > 0) {
        setContent(prefill);
      }
      // 桌面端打开即聚焦；移动端仅在 ?capture=1（PWA 快捷方式/分享/快捷指令）时聚焦，避免弹键盘遮挡
      const isDesktop = window.matchMedia("(min-width: 768px)").matches;
      if (isDesktop || params.get("capture") === "1") {
        textareaRef.current?.focus();
      }
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  // 回填/预填后让高度适配内容（逐字输入时 onChange 已同步处理）
  useEffect(() => {
    if (textareaRef.current) autoResize(textareaRef.current);
  }, [content]);

  // 卸载时清掉未触发的草稿写入
  useEffect(() => {
    return () => {
      if (draftTimerRef.current) clearTimeout(draftTimerRef.current);
    };
  }, []);

  function handleContentChange(el: HTMLTextAreaElement) {
    const value = el.value;
    setContent(value);
    autoResize(el);
    // 输入即存：debounce 1s 写入单条快照（独立于离线待上传队列）
    if (draftTimerRef.current) clearTimeout(draftTimerRef.current);
    draftTimerRef.current = setTimeout(() => writeCaptureDraft(value), 1000);
  }

  /** 提交后清理输入即存快照：取消未触发的写入并删 key，防止幽灵回填 */
  function discardCaptureDraft() {
    if (draftTimerRef.current) {
      clearTimeout(draftTimerRef.current);
      draftTimerRef.current = null;
    }
    clearCaptureDraft();
  }

  const canSave = content.trim().length > 0 && !saving;

  // 挂载时与恢复联网时补发离线草稿（AC-F013-02）
  useEffect(() => {
    let cancelled = false;

    async function syncDrafts() {
      const drafts = readDrafts();
      if (drafts.length === 0) {
        if (!cancelled) setPendingDrafts(0);
        return;
      }
      let synced = 0;
      // 逆序遍历补发（原地 removeDraftAt 不打乱未处理下标）；
      // 入库时间取草稿的 saved_at 而非补发时刻，时间线不因逆序而颠倒
      for (let i = drafts.length - 1; i >= 0; i--) {
        try {
          await api.createIdea(
            drafts[i].content,
            drafts[i].project_id,
            drafts[i].saved_at,
          );
          removeDraftAt(i);
          synced += 1;
        } catch {
          break; // 仍然离线或后端不可用：停止，剩余草稿下轮再试
        }
      }
      if (cancelled) return;
      setPendingDrafts(draftCount());
      if (synced > 0) {
        setNotice(`已同步 ${synced} 条离线草稿`);
        onSavedRef.current();
      }
    }

    void syncDrafts();
    const handleOnline = () => void syncDrafts();
    window.addEventListener("online", handleOnline);
    return () => {
      cancelled = true;
      window.removeEventListener("online", handleOnline);
    };
  }, []);

  async function save() {
    const text = content.trim();
    if (!text || saving) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const created = await api.createIdea(text, projectId || null);
      discardCaptureDraft();
      setContent("");
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
      onSaved(created);
    } catch (e) {
      // 网络故障（离线/后端不可达）：存入离线草稿，联网后自动补发
      if (e instanceof ApiError && e.status === 0 && !e.aborted) {
        const drafts = addDraft(text, projectId || null);
        discardCaptureDraft();
        setPendingDrafts(drafts.length);
        setContent("");
        if (textareaRef.current) {
          textareaRef.current.style.height = "auto";
        }
        setNotice("已保存为离线草稿，联网后自动同步");
      } else {
        setError(e instanceof ApiError ? e.message : "保存失败，请稍后重试");
      }
    } finally {
      setSaving(false);
      textareaRef.current?.focus();
    }
  }

  return (
    <div className="rounded-xl border border-border bg-surface shadow-sm">
      <textarea
        ref={textareaRef}
        value={content}
        onChange={(e) => handleContentChange(e.target)}
        onKeyDown={(e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
            e.preventDefault();
            void save();
          }
        }}
        placeholder="此刻的想法…"
        aria-label="记录灵感"
        maxLength={10000}
        rows={3}
        className="block w-full resize-none rounded-t-xl bg-transparent px-4 py-3 text-base leading-relaxed text-ink-strong placeholder:text-ink-faint focus:outline-none"
      />
      <div className="flex items-center justify-between gap-3 border-t border-border-soft px-3 py-2">
        <select
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          aria-label="归入项目"
          className="max-w-[45%] rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-ink-muted hover:border-border focus:border-primary-border focus:outline-none"
        >
          <option value="">无项目</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <div className="flex items-center gap-3">
          {/* 状态提示（成功/失败/草稿恢复/离线补发）对屏幕阅读器播报（T3.5） */}
          <div role="status" aria-live="polite" className="flex items-center gap-3">
            {pendingDrafts > 0 && (
              <span className="text-xs text-warning">
                离线草稿 {pendingDrafts} 条待同步
              </span>
            )}
            {notice && <span className="text-xs text-success">{notice}</span>}
            {error && <span className="text-xs text-error">{error}</span>}
          </div>
          <span className="hidden text-xs text-ink-faint sm:inline">
            Ctrl/⌘ + Enter 保存
          </span>
          <button
            type="button"
            onClick={() => void save()}
            disabled={!canSave}
            className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-border-strong"
          >
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
