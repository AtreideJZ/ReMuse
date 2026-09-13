import type { Metadata, Viewport } from "next";
import "./globals.css";
import { SiteNav } from "@/components/site-nav";
import { TokenGate } from "@/components/token-gate";
import { PwaRegister } from "@/components/pwa-register";

export const metadata: Metadata = {
  title: "ReMuse 溯游",
  description: "Agent 的个人灵感记忆库",
  icons: { apple: "/icons/apple-touch-icon.png" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#4f46e5" },
    { media: "(prefers-color-scheme: dark)", color: "#17181c" },
  ],
};

// 防闪白：首帧前读取 localStorage 主题偏好并设置 <html data-theme>；
// 与 components/theme-toggle.tsx 共用同一 key。CSP 的 script-src 含 'unsafe-inline'，内联脚本可执行。
const themeInitScript = `(function(){try{var t=localStorage.getItem("remuse-theme");if(t==="light"||t==="dark"){document.documentElement.setAttribute("data-theme",t);}}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="min-h-full bg-background text-foreground">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:text-white"
        >
          跳到主内容
        </a>
        <SiteNav />
        <main
          id="main-content"
          className="mx-auto w-full max-w-3xl px-4 pb-20 pt-6"
        >
          <TokenGate>{children}</TokenGate>
        </main>
        <PwaRegister />
      </body>
    </html>
  );
}
