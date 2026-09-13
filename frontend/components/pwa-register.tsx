"use client";

import { useEffect, useState } from "react";

/** 注册 Service Worker（仅生产环境；开发环境避免缓存干扰调试）。 */
export function PwaRegister() {
  // 非安全上下文（既非 https:// 也非 localhost）时给出可见提示，
  // 而不是让 register() 静默失败——否则用户不知道为何装不上主屏、离线不可用
  const [insecure, setInsecure] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) {
      return;
    }
    if (!window.isSecureContext) {
      // setState 放异步回调里（react-hooks/set-state-in-effect）
      const timer = setTimeout(() => setInsecure(true), 0);
      return () => clearTimeout(timer);
    }
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // SW 注册失败不影响主功能
    });
  }, []);

  if (!insecure || dismissed) return null;
  return (
    <div
      role="alert"
      className="fixed inset-x-0 bottom-4 z-50 mx-auto flex w-[calc(100%-2rem)] max-w-lg items-start gap-3 rounded-lg border border-border bg-surface px-4 py-3 text-sm shadow-lg"
    >
      <p className="flex-1 leading-relaxed text-ink-muted">
        当前地址不是 <span className="text-warning">HTTPS</span>
        ：无法安装到主屏，离线记录不可用。换用 HTTPS 地址（如 Tailscale
        分配的地址）后这些能力自动恢复，详见 README「在手机上使用」。
      </p>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label="关闭提示"
        className="shrink-0 text-ink-faint hover:text-ink-muted"
      >
        ✕
      </button>
    </div>
  );
}
