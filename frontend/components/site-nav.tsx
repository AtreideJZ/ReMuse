"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// 主导航收敛为高频日常动作 + 设置入口；密钥 / 日志 / 导出已移入 /settings
const NAV_ITEMS = [
  { href: "/", label: "记录" },
  { href: "/search", label: "搜索" },
  { href: "/projects", label: "项目" },
  { href: "/settings", label: "设置" },
] as const;

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

export function SiteNav() {
  const pathname = usePathname();

  return (
    <>
      <header className="sticky top-0 z-10 border-b border-border bg-surface/90 backdrop-blur">
        <div className="mx-auto flex h-14 w-full max-w-3xl items-center justify-between px-4">
          <Link href="/" className="text-lg font-semibold tracking-tight text-ink-strong">
            ReMuse 溯游
          </Link>
          {/* 桌面端顶部导航 */}
          <nav aria-label="主导航" className="hidden items-center gap-1 sm:flex">
            {NAV_ITEMS.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                    active
                      ? "bg-primary-soft text-primary"
                      : "text-ink-secondary hover:bg-fill hover:text-ink-strong"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      {/* 移动端底部 tab bar（main 的 pb-20 已为其预留空间） */}
      <nav
        aria-label="主导航"
        className="fixed inset-x-0 bottom-0 z-10 border-t border-border bg-surface/90 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden"
      >
        <div className="grid grid-cols-4">
          {NAV_ITEMS.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`flex items-center justify-center px-1 py-2.5 text-xs font-medium transition-colors ${
                  active
                    ? "text-primary"
                    : "text-ink-secondary hover:text-ink-strong"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
