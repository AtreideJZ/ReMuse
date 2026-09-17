# ReMuse 溯游 —— Agent 的个人灵感记忆库

> 本文档供 AI coding agent 与人类贡献者阅读。如果你刚进入这个项目，请先读此文件再改代码。

## 1. 项目概述

**不是 memory server，是 Agent 的个人灵感记忆库。** ReMuse 溯游是一个自部署的单用户 Web 应用：用户可以随手记录灵感（< 10 秒、零整理），后台 AI 自动把原文结构化为标题、摘要、标签、项目建议等元数据，并通过混合检索（中文全文 + 向量 + RRF 融合）让外部 Agent 在未来项目中准确、可控地找回这些灵感。

主要能力：快速文字记录、灵感列表/详情（原文与 AI 推断分区）、AI 异步结构化（失败降级可重试）、项目空间 CRUD、标签筛选、混合检索、API Key 管理（只读默认 / 按项目授权 / 吊销即失效）、Agent REST 接口（`/api/agent/*`）、MCP Server（Streamable HTTP，六工具 + `ideas://` 资源）、Agent 调用日志（含越权记录）、灵感复用率统计、全量数据导出、复用追踪闭环、PWA（离线草稿联网自动补发）。

Agent 平台接入方法见 `docs/MCP接入指南.md`。方向边界（明确不做的功能）见 `CONTRIBUTING.md`。

## 2. 技术栈与运行时架构

### 2.1 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 16（App Router）+ React 19 + TypeScript 5 + Tailwind CSS 4 |
| 后端 | Python 3.11 + FastAPI + asyncpg + Pydantic v2 |
| MCP | 官方 MCP Python SDK 1.x（FastMCP，Streamable HTTP，stateless 模式；服务名 `remuse`） |
| 数据库 | PostgreSQL 16 + pgvector + zhparser（中文分词） |
| 迁移 | Alembic（手写 SQL 迁移，不依赖 autogenerate） |
| 测试 | pytest + pytest-asyncio + httpx（ASGI 传输）+ 真实 MCP client |
| LLM / Embedding | 兼容 OpenAI 接口的任何服务（默认 gpt-4o-mini / text-embedding-3-small） |
| 部署 | Docker Compose（db + api + mcp + web，compose 项目名 `remuse`） |

### 2.2 服务架构

```
┌──────────────┐      ┌──────────────────────┐    ┌──────────────────┐
│  Next.js 前端 │      │ Agent 客户端 (REST)   │    │ Agent 客户端(MCP) │
│  :3000       │      │ Bearer Token          │    │ Bearer Token      │
└──────┬───────┘      └──────────┬───────────┘    └────────┬─────────┘
       │ /api/* rewrite          │ /api/agent/*            │ :8002/mcp
       └──────────────┬──────────┘                  ┌───────▼───────┐
                ┌─────▼──────┐                      │ MCP Server     │
                │ FastAPI API │ :8000（容器内）      │ FastMCP        │
                │ backend/app │                      │ stateless HTTP │
                └──────┬──────┘                      └───────┬───────┘
                       │            共享服务层与连接池           │
                       └──────────────┬───────────────┘
                              ┌───────▼────────┐   ┌─────────────────┐
                              │ PostgreSQL 16  │   │ LLM / Embedding │
                              │ pgvector + zhparser│ │ OpenAI 兼容 API │
                              └────────────────┘   └─────────────────┘
```

- 前端在本地开发时通过 Next.js rewrite 把 `/api/*` 转发到后端；生产镜像在构建期固化 `API_ORIGIN`。
- MCP 与 REST 分进程部署，但共享同一服务层（`hybrid_search` / `enqueue_ai_processing` 等）与数据模型，不重复实现业务逻辑。
- MCP 为 stateless 模式（无 session 状态），认证由纯 ASGI 中间件 `BearerAuthMiddleware` 完成，Principal 经 contextvar 传入工具函数。
- 后端使用单个模块级 asyncpg 连接池（`app/db.py`，加锁防并发重复建池），生命周期由 FastAPI `lifespan` 管理；MCP 进程按需惰性建池。
- LLM 结构化与 Embedding 回填均为异步后台任务，不阻塞记录接口。

## 3. 仓库结构

```
.
├── .env.example          # 环境变量模板
├── docker-compose.yml    # 一键启动：db + api + mcp + web（项目名 remuse）
├── README.md             # 用户快速开始
├── AGENTS.md             # 本文件
├── scripts/
│   └── backup.sh         # 每日备份（pg_dump → ./backups，保留 14 份）
├── db/                   # PostgreSQL 镜像（pgvector + zhparser）
│   ├── Dockerfile        # 编译安装 scws + zhparser（HTTPS + 校验和 + 固定 commit）
│   └── init/01_extensions.sql
├── backend/              # FastAPI 后端
│   ├── app/
│   │   ├── main.py       # FastAPI 入口、lifespan、路由挂载、日志保留期清理、PermissionError→403
│   │   ├── mcp_server.py # MCP Server（FastMCP，六工具+三资源+Bearer 认证+调用日志）
│   │   ├── config.py     # pydantic-settings 配置
│   │   ├── db.py         # asyncpg 连接池
│   │   ├── schemas.py    # Pydantic 请求/响应模型
│   │   ├── routers/      # API 路由
│   │   │   ├── ideas.py      # 灵感 CRUD、AI 重试（处理中 409）、相关灵感（/{id}/related）、复用档案（/{id}/reuse-trace）
│   │   │   ├── projects.py   # 项目空间 CRUD
│   │   │   ├── tags.py       # 标签列表
│   │   │   ├── search.py     # Web 混合检索
│   │   │   ├── keys.py       # API Key 管理
│   │   │   ├── logs.py       # Agent 调用日志查询
│   │   │   ├── stats.py      # 复用率统计（/api/stats/reuse）
│   │   │   ├── export.py     # 全量数据导出（/api/export）
│   │   │   └── agent.py      # Agent 访问接口（REST 形态，全量审计）
│   │   └── services/     # 业务逻辑与外部服务
│   │       ├── structuring.py  # AI 结构化（CAS 抢占+信号量）+ Embedding 回填
│   │       ├── llm.py          # LLM 调用
│   │       ├── embedder.py     # Embedding 抽象层
│   │       ├── search.py       # 混合检索 SQL + 共享相关灵感查询（fetch_related_ideas）
│   │       ├── keys.py         # Key 生成/校验/授权（guard_scope / check_project_access）
│   │       ├── logs.py         # 调用日志写入（log_call）+ 超期清理（purge_old_logs）
│   │       ├── reuse.py        # 复用追踪（命中记 retrieved / 确认记 used；冗余 retrieved_count/last_retrieved_at 计数列）
│   │       ├── admin_auth.py   # 管理面认证中间件（ADMIN_TOKEN，fail-closed）
│   │       └── ratelimit.py    # 滑动窗口限流（capture/search/export）
│   ├── alembic/          # 手写 SQL 迁移
│   │   ├── env.py
│   │   └── versions/
│   ├── scripts/          # 种子与验收脚本（seed.py / accept_search.py / verify_mcp.py / perf.py）
│   │                     # 评测集（eval_dataset.json / eval_search.py）
│   ├── tests/            # pytest 测试
│   │   ├── test_api.py
│   │   ├── test_keys.py
│   │   ├── test_search.py
│   │   ├── test_mcp.py       # 真实 MCP client 集成测试（不 mock 协议）
│   │   ├── test_related_reuse.py # 相关灵感/复用档案端点与计数口径
│   │   ├── test_security.py
│   │   └── test_release.py
│   ├── requirements.txt      # 运行时依赖（锁版本，进镜像）
│   ├── requirements-dev.txt  # 测试依赖（不进镜像）
│   ├── pytest.ini
│   ├── alembic.ini
│   ├── .dockerignore
│   └── Dockerfile            # 多阶段构建，非 root 运行
└── frontend/             # Next.js 前端
    ├── app/              # App Router 页面
    │   ├── page.tsx          # 记录页（Agent 活动流 + 乐观插入 + offset 分页）
    │   ├── layout.tsx        # 元信息 + PwaRegister + 主题防闪白内联脚本
    │   ├── manifest.ts       # PWA manifest（/manifest.webmanifest，含 shortcuts/share_target）
    │   ├── capture/page.tsx  # 分享目标接收页（query 预填 → 跳首页聚焦）
    │   ├── search/page.tsx   # 混合检索
    │   ├── projects/page.tsx # 项目空间
    │   ├── keys/page.tsx     # API Key 管理（弹窗含焦点陷阱）
    │   ├── logs/page.tsx     # Agent 调用日志 + 复用统计卡 + 复用标注
    │   ├── settings/page.tsx # 设置（外观主题切换 + 密钥/日志/导出入口）
    │   └── ideas/[id]/page.tsx # 详情（复用档案 + 相关灵感区块 + 标为已复用 + 上一条/下一条）
    ├── public/
    │   ├── sw.js             # 手写 Service Worker（离线外壳，/api/* 永不缓存）
    │   └── icons/            # PWA 图标（backend/scripts/generate_icons.py 一次性生成）
    ├── components/       # React 组件（含 agent-activity / theme-toggle / pwa-register；site-nav 主导航 + 移动端底部 tab bar + 全局离线待同步指示）
    ├── lib/
    │   ├── api.ts            # 前端 API 客户端（15s 超时 + AbortController 透传）
    │   ├── offline-drafts.ts # 离线草稿队列（localStorage，联网自动补发）+ remuse-capture-draft 输入快照 + 队列变更事件
    │   ├── idea-list-order.ts# 列表顺序快照（sessionStorage，供详情页上一条/下一条）
    │   ├── search-history.ts # 搜索历史（localStorage，最近 8 条）
    │   ├── types.ts          # TypeScript 类型
    │   └── time.ts           # 时间格式化工具
    ├── next.config.ts    # rewrite 配置（构建期固化，启动时校验 API_ORIGIN）
    ├── tsconfig.json
    ├── package.json
    └── Dockerfile
```

> 历史命名说明：数据卷 `flash_pgdata`、数据库默认用户/库名 `flash` 是项目更名前（曾用名「Flash 灵感库」）的遗留，为保证已有部署的数据不迁移、不丢失而有意保留。新部署无需在意。

## 4. 开发、构建与测试命令

### 4.1 一键启动（Docker Compose）

```bash
cp .env.example .env
# 编辑 .env，填入 POSTGRES_PASSWORD / ADMIN_TOKEN；LLM_API_KEY / EMBEDDING_API_KEY 不填也能跑（AI 结构化会标记失败，可重试）
docker compose up -d --build
```

访问：

- Web：<http://localhost:3000>
- API：<http://localhost:8001>（宿主编口由 `.env` 的 `API_PORT` 控制；容器内部恒为 8000）
- MCP：<http://localhost:8002/mcp>（宿主编口由 `MCP_PORT` 控制；容器内部恒为 8001；各 Agent 平台配置方法见 `docs/MCP接入指南.md`）

停止：`docker compose down`
清空数据重来：`docker compose down -v`
备份：`bash scripts/backup.sh`（pg_dump 到 `./backups`，保留最近 14 份）

### 4.2 后端本地开发

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt   # Windows Git Bash
# macOS / Linux: .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
docker compose up -d db                               # 只起数据库
DATABASE_URL=postgresql://flash:flash@localhost:5432/flash .venv\Scripts\python -m alembic upgrade head
DATABASE_URL=postgresql://flash:flash@localhost:5432/flash .venv\Scripts\python -m uvicorn app.main:app --port 8001 --reload
```

跑测试：

```bash
cd backend && .venv\Scripts\python -m pytest tests/ -q
```

测试需要可访问的数据库。`test_api.py` 在数据库不可用时自动跳过；`test_search.py` 在未配置 `EMBEDDING_API_KEY` 时跳过；`test_release.py::test_ai_success_path` 在未配置 `LLM_API_KEY` 时跳过。

### 4.3 前端本地开发

```bash
cd frontend
npm install
API_ORIGIN=http://localhost:8001 npm run dev
```

> 注意：`next.config.ts` 中的 `/api/*` rewrite 目标在构建期固化，所以 Docker 构建时必须通过 `ARG API_ORIGIN` 注入；运行时 `-e API_ORIGIN` 无效。配置时会校验 URL 合法性（去尾斜杠、强制 http/https）。

### 4.4 常用检查

- 后端类型检查：`cd backend && .venv\Scripts\python -m mypy app`（项目未强制配置 mypy，但建议保持类型注解准确）
- 前端 lint：`cd frontend && npm run lint`
- 性能实测：`cd backend && .venv\Scripts\python scripts/perf.py`
- MCP 端到端：`cd backend && .venv\Scripts\python scripts/verify_mcp.py`（需容器在跑）

## 5. 代码组织约定

### 5.1 后端

- **不用 SQLAlchemy ORM 走热路径**。pgvector 的 `<=>` 操作和复杂检索 SQL 用 `asyncpg` 直接执行，迁移也用手写 SQL。
- 配置统一在 `app/config.py` 的 `Settings` 中，通过环境变量 / `.env` 覆盖；新增配置项同步更新 `.env.example`。
- Pydantic 模型放在 `app/schemas.py`；业务逻辑放在 `app/services/`；HTTP 层放在 `app/routers/`。
- **管理面（Web 端点）一律要求 ADMIN_TOKEN**，由 `services/admin_auth.py` 的中间件强制（fail-closed：未配置则 503）；豁免仅 `/api/health` 与 `/api/agent/`。新增管理端点不得绕过。
- **触发计费/重查询的端点必须限流**，用 `services/ratelimit.py` 的滑窗实例（capture 20/min、search 60/min、export 5/5min），按调用方身份分键（Agent 用 key_id，Web 用 IP）。
- **任何 Agent 调用入口（MCP 工具/资源、REST `/api/agent/*`）都必须写审计日志**，统一走 `app/services/logs.py` 的 `log_call()`（含越权 `denied`）；新增 Agent 接口时不得绕过。REST 工具名加 `rest:` 前缀与 MCP 区分。
- **授权校验统一走 `services/keys.py`**：`guard_scope()`（scope）与 `check_project_access()`（项目），越权抛 `PermissionError`——REST 侧由 `main.py` 全局异常处理映射为 403，MCP 侧直接成为工具错误。
- Agent 接口与 Web 接口共享 `_BASE_SELECT` / `_to_out` 等辅助函数（定义在 `app/routers/ideas.py`，被 `agent.py` / `search.py` / `mcp_server.py` 导入）；相关灵感 SQL 共享 `services/search.py` 的 `fetch_related_ideas()`（MCP / Agent REST / Web 三处复用）。
- **Web 端点的检索不算复用**：`/api/ideas/{id}/related` 与 `/api/ideas/{id}/reuse-trace` 等管理面查询**严禁调用** `mark_retrieved()`（污染复用率分子）与 `log_call()`（日志表只记 Agent 调用）；`mark_retrieved` 在迁移状态时同步递增 `ideas.retrieved_count` / `last_retrieved_at`（计数对所有命中递增，状态迁移仍限定 `captured`）。
- 异步后台任务由 `services/structuring.py` 管理：CAS 条件 UPDATE 抢占任务（防重复处理），`asyncio.Semaphore(4)` 限制 LLM 并发；`app/main.py` 的 `lifespan` 会在启动时重新入队未完成的任务，并启动缺失向量的回填任务（失败行标记 `embedding_attempted_at`，1 小时内不重试）。
- 依赖锁定：`requirements.txt`（运行时，进镜像）与 `requirements-dev.txt`（测试，不进镜像）分离；升级依赖需跑全量测试后人工更新版本号。

### 5.2 前端

- 所有页面组件均为 Client Component（`"use client"`），因为需要直接调用浏览器 `fetch` 与状态管理。
- API 调用统一走 `lib/api.ts`（内置 15s 超时；`ApiError` 含 HTTP status 与 `aborted` 标记）。
- 并发请求防覆盖：轮询/筛选场景用请求序号 ref 或 AbortController（见 `app/page.tsx`、`app/search/page.tsx` 的既有模式）。
- 配色一律使用 `app/globals.css` `@theme` 定义的语义 token（surface/ink/primary/error/success/warning 等），禁止 `gray-*`/`indigo-*` 等原生色；`@theme` 的 `--color-*` 指向运行时 `--c-*` 变量（`:root` 浅色 / `[data-theme="dark"]` 深色 / 跟随系统），新增颜色须两套值同步定义，页面内禁止硬编码十六进制色值。主题三态由 `components/theme-toggle.tsx` 持久化到 localStorage `remuse-theme`，`layout.tsx` 内联脚本防闪白。
- 路径别名 `@/*` 映射到项目根目录（见 `tsconfig.json`）。

## 6. 代码风格指南

- 语言：代码中注释、文档字符串、错误提示以**中文**为主；技术术语、接口名、变量名保持英文。
- Python：使用类型注解；字符串插值优先用 f-string；使用 `ruff` / 类似风格保持一致的 import 顺序。
- TypeScript：开启 `strict: true`；避免 `any`；异步错误通过 `ApiError` 区分。
- 数据库 SQL：参数化查询，禁止拼接用户输入；手动构造 SQL 时仅拼接内部生成的白名单片段（如 `model_fields_set` 对应的字段名）。
- 最小变更原则：只改完成当前任务所必需的文件和行；不做附带重构或重命名。

## 7. 测试策略

- 现有测试覆盖：
  - `tests/test_api.py`：灵感生命周期、项目删除保护、AI 失败降级、离线记录时刻（captured_at）。
  - `tests/test_keys.py`：读写 scope 边界、无效/吊销 Key 拒绝、按项目授权隔离。
  - `tests/test_search.py`：语义召回、关键词精确召回、项目/时间过滤组合。
  - `tests/test_mcp.py`：真实 MCP client + Streamable HTTP 集成测试（不 mock 协议）：工具列表、搜索与调用日志、只读越权拒绝、写入授权、未授权 401、资源读取、日志 API、越权/不存在日志区分、并发 Principal 隔离、`find_related_ideas` 共享函数重构回归。
  - `tests/test_related_reuse.py`：Web 端 related/reuse-trace 端点（不改状态、不写日志的口径红线）、`mark_retrieved` 计数递增（含重复检索）。
  - `tests/test_security.py`：管理面认证与安全响应头。
  - `tests/test_release.py`：超长拒绝、retry 409、默认只读、日志保留期清理、AI 真实结构化成功路径、复用率口径、tags/health。
- MCP 测试在会话内共享一个随机端口的 uvicorn 实例（Windows 上反复启停 uvicorn 会触发端口竞态，勿改成每测试一实例）。
- 测试清理一律 try/finally（直接打真实库，失败也不能留脏数据）。
- 运行测试前确保数据库已启动并迁移到最新版本。提交前至少跑 `pytest tests/ -q`，并保证全部通过。

## 8. 安全设计要点

- **管理面认证（fail-closed）**：所有 Web 管理端点要求 `X-Admin-Token`（或 `Authorization: Bearer`）等于 `.env` 的 `ADMIN_TOKEN`；未配置时管理面整体 503。前端令牌存 localStorage，失效自动回门禁页。
- **原文不可变**：数据库触发器 `ideas_raw_immutable` 强制 `raw_content` 不可更新。
- **AI 失败降级**：LLM/Embedding 未配置或失败时，灵感原文永远可用，AI 状态标记为 `failed` 且可重试。
- **项目删除保护**：删除项目不会删除其下灵感，自动转为「无项目」。
- **Agent 默认只读**：写入接口需要 Key 显式包含 `write` scope。
- **Key 按项目授权**：`api_keys.project_ids` 为空表示可访问全部项目；非空则只能访问所列项目 + 无项目的个人全局灵感。越权查询返回「无权限或不存在」，不泄露存在性。
- **吊销即失效**：每次请求都查库校验 `revoked_at`，无缓存。
- **密钥只返回一次**：创建 Key 时返回完整 token，数据库存储 SHA-256 哈希。
- **灵感内容视为不可信输入**：返回给 Agent 的数据带 `UNTRUSTED_NOTE` 隔离标记（防 Prompt Injection）；LLM 结构化时原文以 ```raw``` 分隔符包裹并声明不可信。
- **调用日志即审计**：MCP 与 REST Agent 接口的每次调用（含越权 `denied` 尝试）都写入 `agent_call_logs`；读取失败对内区分「越权访问」（denied）与「不存在」（error），对外统一「无权限或不存在」不泄露存在性；默认保留 90 天（`AGENT_LOG_RETENTION_DAYS` 可配）。
- **速率限制**：写入/检索/导出端点滑窗限流（防 LLM 计费放大与 DoS），429 拒绝。
- **安全响应头**：API（X-Content-Type-Options / X-Frame-Options / Referrer-Policy，HSTS 按 `ENABLE_HSTS` 开关）与 Web（next.config.ts 含 CSP，Next 水合需 `script-src 'unsafe-inline'`）。
- **配置层 SSRF 防护**：`LLM_BASE_URL`/`EMBEDDING_BASE_URL` 启动时校验 scheme 并默认拒绝私网/回环地址（本地网关用 `ALLOW_PRIVATE_BASE_URL=true` 显式放行）。
- **数据库不出内网**：5432 仅绑定 127.0.0.1；`POSTGRES_PASSWORD` 必填无默认值。
- **MCP 无删除能力**：任何 Agent 都无法删除或改写灵感，删除权限永不开放。
- **离线记录时刻可信边界**：创建灵感接受客户端提交的 `captured_at`（离线草稿补发），客户端时间可伪造——单用户自部署场景下接受，服务端做范围校验（拒绝明显未来/过旧的值）。

## 9. 部署与运维

- 生产部署通过 `docker compose up -d --build`。
- **公网开放前置条件**：`ADMIN_TOKEN` 与 `POSTGRES_PASSWORD` 为高强度随机值；TLS 终结于反代；5432 不暴露（compose 已仅绑 127.0.0.1）；`ENABLE_HSTS=true`。
- 后端容器以非 root 用户（`app`，uid 1000）运行；启动时先执行 `alembic upgrade head`，健康检查通过即表示 schema 就绪。
- `mcp` 与 `web` 服务都依赖 `api` 的 `service_healthy`，避免迁移完成前接收流量。
- 数据库数据持久化在 Docker 卷 `flash_pgdata`（历史命名，见 §3 说明）。
- 备份：`bash scripts/backup.sh`（pg_dump → `./backups`，保留 14 份）。
- 后端 CORS 仅允许 `http://localhost:3000`（方法/头已收紧到实际所需），生产环境前端经 Next.js rewrite 同源访问。

## 10. AI Agent 注意事项

- 修改数据库 Schema 时，必须同步更新 `backend/alembic/versions/` 中的手写迁移，并考虑旧数据兼容性。
- 修改 Embedding 模型或维度时，必须同步修改 `.env.example` / `.env` 的 `EMBEDDING_DIM`，并重建 `ideas.embedding` 列与 IVFFlat 索引。
- 修改前端 API rewrite 目标时，必须重新构建前端 Docker 镜像；仅改环境变量不生效。
- 修改 MCP 工具/资源的签名或行为时，必须同步 `backend/tests/test_mcp.py` 与 `docs/MCP接入指南.md`。
- 修改 `db/Dockerfile` 中的 scws / zhparser 版本时，必须同步更新对应 SHA-256 校验和与根目录 `NOTICE` 的归属声明。
- 写测试时优先覆盖边界与安全场景（scope、越权、降级）。
- 不要在前端页面组件中直接写服务端逻辑；页面均为 Client Component，API 调用走 `lib/api.ts`。
- 品牌命名：产品对外的名称统一为 **ReMuse 溯游**；MCP 服务名、compose 项目名为 `remuse`；历史标识（数据卷 `flash_pgdata`、DB 默认用户/库名 `flash`）为有意保留的内部细节，不要改（见 §3 说明）。
