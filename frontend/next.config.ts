import type { NextConfig } from "next";

// rewrites 在构建期固化，API_ORIGIN 必须构建时注入（Docker ARG），运行时 -e 无效
const API_ORIGIN = (process.env.API_ORIGIN || "http://localhost:8001").replace(/\/+$/, "");
if (!/^https?:\/\//.test(API_ORIGIN)) {
  throw new Error(`API_ORIGIN 必须以 http:// 或 https:// 开头，当前值: ${API_ORIGIN}`);
}

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_ORIGIN}/api/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
          {
            // Next.js 水合依赖内联脚本，script-src 需保留 'unsafe-inline'
            key: "Content-Security-Policy",
            value:
              "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
