"use client";

import { useEffect, useState } from "react";

type ThemePreference = "light" | "dark" | "system";

const STORAGE_KEY = "remuse-theme";

const OPTIONS: readonly { value: ThemePreference; label: string }[] = [
  { value: "light", label: "浅色" },
  { value: "dark", label: "深色" },
  { value: "system", label: "跟随系统" },
];

/**
 * 主题三态切换：浅色 / 深色 / 跟随系统。
 * 偏好持久化到 localStorage（remuse-theme），layout.tsx 的内联脚本在首帧前
 * 读取同一 key 并设置 <html data-theme>，避免深色首帧闪白。
 */
export function ThemeToggle() {
  const [theme, setTheme] = useState<ThemePreference>("system");

  // 挂载后读取偏好（异步回调里 setState，避免 SSR 水合不一致与 effect 内同步 setState）
  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => {
      if (cancelled) return;
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "light" || stored === "dark" || stored === "system") {
        setTheme(stored);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  function applyTheme(next: ThemePreference) {
    setTheme(next);
    localStorage.setItem(STORAGE_KEY, next);
    // 跟随系统 = 不带 data-theme 属性，由 CSS 媒体查询接管
    if (next === "system") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", next);
    }
  }

  return (
    <div
      role="group"
      aria-label="主题"
      className="inline-flex rounded-lg border border-border bg-fill-soft p-0.5"
    >
      {OPTIONS.map((option) => {
        const active = theme === option.value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => applyTheme(option.value)}
            className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
              active
                ? "bg-surface font-medium text-ink-strong shadow-sm"
                : "text-ink-muted hover:text-ink-strong"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
