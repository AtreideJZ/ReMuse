"use client";

import { useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  AUTH_REQUIRED_EVENT,
  getAdminToken,
  setAdminToken,
} from "@/lib/api";

type GateState = "checking" | "locked" | "unlocked";

/**
 * 管理令牌门禁：无令牌时渲染全屏输入卡片，有令牌才渲染 children。
 * 监听 api 层广播的 remuse:auth-required 事件回到输入态。
 */
export function TokenGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<GateState>("checking");
  const [tokenInput, setTokenInput] = useState("");
  const [error, setError] = useState("");
  const [validating, setValidating] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // 初始判定（异步回调里 setState，避免 SSR 水合不一致与 effect 内同步 setState）
  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => {
      if (cancelled) return;
      setState(getAdminToken() !== null ? "unlocked" : "locked");
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // 令牌失效广播：回到输入态
  useEffect(() => {
    function onAuthRequired() {
      setError("");
      setState("locked");
    }
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
  }, []);

  // 进入输入态时聚焦输入框
  useEffect(() => {
    if (state === "locked") {
      inputRef.current?.focus();
    }
  }, [state]);

  async function submit() {
    const token = tokenInput.trim();
    if (!token || validating) return;
    setValidating(true);
    setError("");
    // 先存 localStorage，再发轻量请求验证（401/503 时令牌会被 api 层自动清除）
    setAdminToken(token);
    try {
      await api.listIdeas({ limit: 1 });
      setState("unlocked");
      setTokenInput("");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setError("令牌无效，请重试");
      } else if (e instanceof ApiError && e.status === 503) {
        setError("后端未配置 ADMIN_TOKEN，请先在 .env 配置并重启");
      } else {
        setError("无法连接后端");
      }
    } finally {
      setValidating(false);
    }
  }

  if (state === "checking") {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <p className="text-sm text-ink-faint">加载中…</p>
      </div>
    );
  }

  if (state === "locked") {
    return (
      <div className="flex min-h-[70vh] items-center justify-center">
        <div className="w-full max-w-sm rounded-xl border border-border bg-surface p-6 shadow-sm">
          <h1 className="text-lg font-semibold text-ink-strong">ReMuse 溯游</h1>
          <p className="mt-1 text-sm text-ink-muted">
            请输入管理令牌（见部署时 .env 的 ADMIN_TOKEN）
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
            className="mt-4 space-y-3"
          >
            <input
              ref={inputRef}
              type="password"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  e.preventDefault();
                  void submit();
                }
              }}
              placeholder="管理令牌"
              aria-label="管理令牌"
              autoComplete="off"
              className="block w-full rounded-md border border-border px-3 py-2 text-sm text-ink-strong placeholder:text-ink-faint focus:border-primary-border focus:outline-none"
            />
            {error && <p className="text-xs text-error">{error}</p>}
            <button
              type="submit"
              disabled={!tokenInput.trim() || validating}
              className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-border-strong"
            >
              {validating ? "验证中…" : "确认"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
