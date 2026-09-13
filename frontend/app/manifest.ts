import type { MetadataRoute } from "next";

// PWA manifest（Next.js 约定式路由，输出 /manifest.webmanifest）
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "ReMuse 溯游",
    short_name: "溯游",
    description: "Agent 的个人灵感记忆库：随手记录，Agent 在未来项目中准确找回",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#4f46e5",
    // T2.3：系统快捷方式，进入即聚焦记录框（?capture=1 语义见 capture-box）
    shortcuts: [{ name: "记一条", url: "/?capture=1" }],
    // T2.4：Android 分享目标，由 /capture 页接住 query 后预填到首页记录框
    share_target: {
      action: "/capture",
      method: "GET",
      params: { title: "title", text: "text", url: "url" },
    },
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      {
        src: "/icons/icon-maskable-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "maskable",
      },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
