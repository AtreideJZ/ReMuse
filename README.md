# ReMuse 溯游

**随手记下的灵感，在真正需要它的那一刻自己回来。**

灵感从来不缺记录工具，缺的是**回头被用上**。ReMuse 是一个可自部署的单用户灵感库：10 秒记下一条突然想到的东西，AI 在后台自动结构化；之后你用 Claude Code、Cursor、Codex 这类 Agent 做相关的事时，Agent 会通过 MCP 把这些旧灵感**主动找回来**——让过去的自己参与今天的决策。

> **[待补截图]** 建议放三张：记录页 / 详情页复用档案 / Agent 在会话中主动找回。这是本 README 目前最大的缺口。

## 它和笔记应用有什么不同

| | 普通笔记应用 | ReMuse |
|---|---|---|
| 记的时候 | 要想放哪个文件夹、打什么标签 | 直接写，零整理 |
| 记完之后 | 埋进列表，靠你自己想起来翻 | AI 结构化，Agent 在需要时主动找回 |
| 谁来用它 | 只有你 | 你和你的 Agent |

## 工作原理

```
你随手记一条
      │
      ▼
AI 异步结构化 ── 标题 / 摘要 / 标签 / 项目建议（原文不可变，派生内容分区展示）
      │
      ▼
混合检索 ── 中文全文 + 向量 + RRF 融合
      │
      ▼
MCP Server ── 六个工具 + ideas:// 资源
      │
      ▼
你的 Agent 在下一个项目里把它找回来
```

## 快速开始

前置：Docker Desktop。

```bash
git clone <repo-url> remuse && cd remuse
cp .env.example .env
```

编辑 `.env`，填两项：

1. **必填** `POSTGRES_PASSWORD` 与 `ADMIN_TOKEN`（用高强度随机值，生成方式见 `.env.example` 里的注释）
2. `LLM_API_KEY` / `EMBEDDING_API_KEY` —— 兼容 OpenAI 接口的任何服务均可。**不填也能跑**：记录与原文永远可用，AI 结构化会标记为 `failed` 并可随时重试

```bash
docker compose up -d --build
```

| 服务 | 地址 | 说明 |
|------|------|------|
| Web | <http://localhost:3000> | 首次访问需输入 `.env` 里的 `ADMIN_TOKEN` |
| API | <http://localhost:8001> | 宿主编口由 `API_PORT` 控制，容器内恒为 8000 |
| MCP | <http://localhost:8002/mcp> | 宿主编口由 `MCP_PORT` 控制，容器内恒为 8001 |
| 数据库 | — | PostgreSQL 16 + pgvector + zhparser，端口仅绑定 `127.0.0.1` |

停止：`docker compose down` · 清空数据重来：`docker compose down -v`
备份：`bash scripts/backup.sh`（pg_dump 到 `./backups`，保留最近 14 份）

> 历史命名说明：数据库默认用户/库名 `flash`、数据卷 `flash_pgdata` 是项目更名前的遗留（曾用名「Flash 灵感库」），为兼容已有部署而保留，不影响使用。

## 接入你的 Agent

1. 在 Web 的**密钥**页创建一个 API Key（默认只读；需要 Agent 写入时勾选 write 权限，可按项目授权）
2. 把 MCP 地址 `http://localhost:8002/mcp` 与 Bearer Token 填进你的 Agent

已实测的平台配置方法见 **[docs/MCP接入指南.md](docs/MCP接入指南.md)**，覆盖 Claude Code、Cursor、Codex、OpenCode、Claude Desktop、Kimi、WorkBuddy、Qoder、Trae、Cherry Studio。

配好之后，让它「搜索我的灵感库」，日志页就会出现这次调用记录。

## 在手机上使用（PWA）

两端分工是设计的一部分：**手机负责随手记录，电脑负责让 Agent 找回**。两者访问的是同一个部署，数据在同一张表里——所以不存在"两端同步"这回事，也就不会有同步冲突。

> **前提：这台服务器需要常在线。** 跑在你自己的电脑上时，电脑一关，手机端就读不到已有灵感、Agent 也连不上。**但记录不会丢**：只要用 HTTPS 地址打开过（Service Worker 已缓存页面外壳），服务端不在线时你依然可以打开页面并记录，内容先进入本地队列，服务端恢复后自动补发。所以手机端要真正常用，**服务端最好放在一台常开设备上**：NAS、迷你主机、软路由、淘汰的旧笔记本都可以，`docker compose` 原样搬过去即可，**不需要改任何代码**。下面三种方式讨论的都是"手机怎么连上它"，而不是"怎么把它装进手机"。

### 1. 手机要能访问到服务器

**手机上不能输 `localhost`。** 它指的是「当前这台设备自己」——你在电脑上访问它指向电脑，在手机上输入它指向手机，而手机上什么都没跑。手机要输的是**那台跑着服务的机器在网络里的地址**。

分两步走，可以先跑通再升级。

**① 先在同一 WiFi 下跑通（零配置）。** 查出服务器所在机器的局域网 IP，手机浏览器输入：

```
http://192.168.1.50:3000        # 换成你自己的 IP
```

查 IP：Windows 用 `ipconfig`，macOS 用 `ipconfig getifaddr en0`，Linux 用 `hostname -I`，NAS 看管理面板。这个地址**只在家里的 WiFi 下有效**（出门连不上），而且因为是 HTTP——浏览器不会注册 Service Worker——**加不到主屏、也没有离线能力**。但页面能开、记录能用，足够先验证一遍。

**② 要长期用，换成 HTTPS 地址。** Service Worker 只在**安全上下文**下注册：`https://`，或 `localhost`（后者只对本机有效，所以对手机没有意义）。三种方式：

| 方式 | 手机上输入的地址 | 适合 |
|------|------|------|
| **Tailscale**（推荐） | `https://<机器名>.<tailnet>.ts.net` | 个人自部署。服务器与手机各装 Tailscale、登录同一账号，然后在服务器执行 `tailscale serve --bg 3000`。**自动签发真实证书**，只在你自己的私有网络内可见，不开公网端口 |
| Cloudflare Tunnel | `https://<你的域名>` | 已有域名、想要固定公网地址。**注意这等于把服务放上公网**，务必保证 `ADMIN_TOKEN` 足够强 |
| VPS + 反向代理 | `https://<你的域名>` | 把 compose 部署到有域名的机器，用 Caddy / Nginx 签发 Let's Encrypt 证书。适合希望在任意网络下都能访问、并接受数据不在本地 |

只有 Web 端（默认 3000）需要暴露——`/api/*` 由 Web 容器在服务端转发给 API，浏览器始终只跟一个来源通信。**也因此不需要为任何地址改动代码或配置：你从哪个地址打开，应用就在那个地址上工作。**

### 2. 添加到主屏

用 HTTPS 地址打开后：iOS Safari 点「分享 → 添加到主屏幕」，Android Chrome 点「安装应用」。首次打开需输入 `.env` 里的 `ADMIN_TOKEN`，令牌按来源存一次，之后免输。

装到主屏不只是好看：iOS 对 Safari 中访问的站点有"7 天未访问即清理本地存储"的机制，**而已添加到主屏的 Web App 不受此限**——你离线记的草稿因此更不容易丢。

### 3. 记录动线

- 长按主屏图标可直达并聚焦记录框
- Android 可从任意应用「分享」文本或链接到「溯游」，内容预填后落在记录页（iOS 不支持这个 API，可用快捷指令打开 `https://<你的地址>/?capture=1`）
- **断网也能记**：Service Worker 缓存了记录页外壳，离线时打开发送即入本地队列，恢复联网后自动补发；`/api/*` 永不缓存，不会读到过期数据

## 功能

**记录与整理**

- 快速记录，原文不可变（数据库触发器强制），AI 派生内容单独分区并标注置信度
- AI 异步结构化：标题 / 摘要 / 标签 / 项目建议，失败可重试
- 项目空间、标签筛选

**找回与复用**

- 混合检索：中文全文 + 向量 + RRF 融合
- `find_related_ideas`：从一个灵感出发找到相关灵感
- 复用追踪闭环：Agent 命中自动记 `retrieved`，`mark_idea_as_used` 回写归因
- 详情页「复用档案」：这个灵感被谁、在什么时候用过

**接入与运维**

- MCP Server（Streamable HTTP，六个工具 + `ideas://` 资源）
- API Key 管理：只读默认 / 按项目授权 / 吊销即失效
- Agent 调用日志（含越权记录）、灵感复用率统计
- 全量数据导出（JSON，含原文与向量）
- PWA：可添加到主屏，离线草稿联网自动同步

## 设计取舍

**三条红线**

- 灵感原文不可变，AI 派生内容永远分开展示
- LLM / Embedding 挂了不影响记录 —— 原文永远可用
- 删除项目不删除其下灵感（自动转为无项目）

**方向边界**

写在这里，是为了让「能不能加 XX」「什么时候出 App」这类问题有一个统一的答案，而不必每次现场判断。

**永久不做。** 这是产品定位，不是资源限制——需求再高也不会改变：

- **多人协作 / 团队共享** —— ReMuse 是**个人工具**。当前认证层只有一个管理令牌，数据模型里没有"用户"这个概念；加进来是架构级变更，不是加一个开关
- **企业版功能（SSO / RBAC / 审计）** —— 依赖上一条，同样不纳入

**当前阶段不做，但不排除：**

- **原生 App** —— 限制在**开发资源**，不在需求：单人维护难以同时支撑 Web、后端与两个平台的原生客户端。PWA 已覆盖手机端记录的主干动线（装到主屏、离线记录、分享目标，见 [在手机上使用（PWA）](#在手机上使用pwa)）。**因此解锁条件不是"呼声够高"，而是有人能承担开发**——若你读到这里并有意愿，欢迎开 issue 讨论

**当前阶段不做，且不接受实现类 PR：**

- **云托管版** —— 只做自部署。托管版的启动条件有明确定义（复用率验证通过），不满足就不会启动

**关于响应**：项目当前为单人维护，**不承诺任何议题的响应时间**，重复追问也不会改变优先级。

## 技术架构

```
┌──────────────┐      ┌──────────────────────┐    ┌──────────────────┐
│  Next.js 前端 │      │ Agent 客户端 (REST)   │    │ Agent 客户端(MCP) │
│  :3000       │      │ Bearer Token          │    │ Bearer Token      │
└──────┬───────┘      └──────────┬───────────┘    └────────┬─────────┘
       │ /api/* rewrite          │ /api/agent/*            │ :8002/mcp
       └──────────────┬──────────┘                  ┌───────▼───────┐
                ┌─────▼──────┐                      │ MCP Server     │
                │ FastAPI API │ :8000（容器内）      │ FastMCP        │
                └──────┬──────┘                      └───────┬───────┘
                       │          共享服务层与连接池           │
                       └──────────────┬───────────────┘
                              ┌───────▼────────┐   ┌─────────────────┐
                              │ PostgreSQL 16  │   │ LLM / Embedding │
                              │ pgvector+zhparser│ │ OpenAI 兼容 API │
                              └────────────────┘   └─────────────────┘
```

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 16（App Router）+ React 19 + TypeScript 5 + Tailwind CSS 4 |
| 后端 | Python 3.11 + FastAPI + asyncpg + Pydantic v2 |
| MCP | 官方 MCP Python SDK（FastMCP，Streamable HTTP，stateless） |
| 数据库 | PostgreSQL 16 + pgvector + zhparser（中文分词） |
| 迁移 | Alembic（手写 SQL 迁移） |

MCP 与 REST 分进程部署，但共享同一服务层（`hybrid_search` / `enqueue_ai_processing`）与数据模型，不重复实现业务逻辑。

## 本地开发

### 后端

```bash
cd backend
python -m venv .venv

# macOS / Linux
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
# Windows (Git Bash)
.venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt

docker compose up -d db          # 只起数据库

# 连接串需与 .env 中的 POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB 一致
export DATABASE_URL="postgresql://<user>:<password>@localhost:5432/<db>"
.venv/bin/python -m alembic upgrade head      # Windows 用 .venv/Scripts/python
.venv/bin/python -m uvicorn app.main:app --port 8001 --reload
```

跑测试（需要数据库在运行）：

```bash
.venv/bin/python -m pytest tests/ -q          # Windows 用 .venv/Scripts/python
```

### 前端

```bash
cd frontend
npm install
API_ORIGIN=http://localhost:8001 npm run dev
```

## 目录结构

```
db/         PostgreSQL 镜像（pgvector + zhparser 中文分词）与初始化 SQL
backend/    FastAPI + asyncpg + Alembic；app/routers 为 API，app/services 为业务逻辑
frontend/   Next.js（App Router）+ Tailwind；/api/* 经 rewrite 代理到后端
docs/       公开文档
scripts/    备份等运维脚本
```

## 文档

- [Agent 接入指南](docs/MCP接入指南.md) —— 10 个平台的 MCP 配置方法

## 许可证

Apache License 2.0，见 [LICENSE](LICENSE)。第三方组件归属见 [NOTICE](NOTICE)。
