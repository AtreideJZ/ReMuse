# ReMuse 溯游 — Agent 接入指南

> 适用版本：v0.1.0（MCP Server）| 更新：2026-09-12
> 信息来源：各平台官方文档（见文末），配置细节截至 2026-08-01 核实

## 0. 准备

1. 启动服务：`docker compose up -d`（MCP 端口默认 **8002**，可用 `.env` 的 `MCP_PORT` 修改）
2. 打开 Web 界面 `http://localhost:3000` →「密钥」页 → 创建密钥：
   - **名字建议按 Agent 命名**（如 `claude-code`、`trae`）——调用日志里显示的就是这个名字
   - 默认**只读**即可满足「搜索/读取灵感」；想让 Agent 也能记灵感再勾「写入」
   - 可按项目授权（留空 = 全部项目 + 个人灵感）
3. 复制生成的密钥（`rm_` 开头，**只显示一次**）

MCP 地址统一为：

```
http://localhost:8002/mcp        # 传输：Streamable HTTP；认证：Authorization: Bearer <YOUR_KEY>
```

以下各平台示例中 `<YOUR_KEY>` 替换为你的密钥。

---

## 1. Claude Code（CLI）✅ 原生支持

```bash
claude mcp add --transport http remuse http://localhost:8002/mcp \
  --header "Authorization: Bearer <YOUR_KEY>"
```

- 作用域：默认 `--scope local`（仅当前项目）；`--scope user` 全局；`--scope project` 写入项目 `.mcp.json`（支持 `${VAR}` 展开，可提交共享）
- 配置文件等价写法（`~/.claude.json` 或项目 `.mcp.json`）：

```json
{ "mcpServers": { "remuse": { "type": "http", "url": "http://localhost:8002/mcp",
  "headers": { "Authorization": "Bearer <YOUR_KEY>" } } } }
```

- 验证：`claude mcp list`；会话内 `/mcp` 查看工具列表

## 2. Cursor ✅ 原生支持

配置文件：项目级 `<项目>/.cursor/mcp.json` 或全局 `~/.cursor/mcp.json`
（GUI：`Cursor Settings → Tools & MCP → New MCP Server` 会打开该文件编辑器）

```json
{ "mcpServers": { "remuse": { "url": "http://localhost:8002/mcp",
  "headers": { "Authorization": "Bearer <YOUR_KEY>" } } } }
```

- 远程服务器只写 `url` 即可（Streamable HTTP 优先、SSE 回退，自动协商）；支持 `${env:REMUSE_API_KEY}` 插值
- 验证：`Settings → Tools & MCP` 看状态与 Available Tools

## 3. OpenAI Codex ✅ 原生支持

`~/.codex/config.toml`（CLI / IDE 插件 / 桌面 App 共享）：

```toml
[mcp_servers.remuse]
url = "http://localhost:8002/mcp"
bearer_token_env_var = "REMUSE_API_KEY"   # 推荐：密钥放环境变量
# 或静态写法：http_headers = { "Authorization" = "Bearer <YOUR_KEY>" }
```

- 也可命令行：`codex mcp add remuse --url http://localhost:8002/mcp`
- 仅支持 Streamable HTTP（不支持 SSE）；旧版如遇 `missing field command` 报错，加顶层 `experimental_use_rmcp_client = true`
- 验证：`codex mcp list`；TUI 内 `/mcp`

## 4. OpenCode ✅ 原生支持

`~/.config/opencode/opencode.json`（全局）或项目级 `opencode.json`：

```json
{ "$schema": "https://opencode.ai/config.json",
  "mcp": { "remuse": { "type": "remote", "url": "http://localhost:8002/mcp",
    "oauth": false,
    "headers": { "Authorization": "Bearer {env:REMUSE_API_KEY}" } } } }
```

- 注意：环境变量插值语法是 `{env:VAR}`（不是 `${VAR}`）；**建议显式 `oauth: false`**，避免 OpenCode 收到 401 后误入 OAuth 发现流程
- 验证：`opencode mcp list`；`opencode mcp debug remuse` 排障

## 5. Claude Desktop ⚠️ 需桥接（GUI Connector 只走 OAuth，无静态 Token 字段）

配置文件（`设置 → 开发者 → Edit Config` 打开，或 `%APPDATA%\Claude\claude_desktop_config.json` / macOS `~/Library/Application Support/Claude/claude_desktop_config.json`），用 `mcp-remote` 桥接：

```json
{ "mcpServers": { "remuse": { "command": "npx",
  "args": [ "-y", "mcp-remote@latest", "http://localhost:8002/mcp",
            "--allow-http", "--header", "Authorization: Bearer <YOUR_KEY>" ] } } }
```

- **`--allow-http` 必须加**：mcp-remote 默认拒绝非 HTTPS（本地 http 例外也要显式允许）
- 验证：完全退出并重启 Claude Desktop → 输入框左下角图标 → Connectors → 应看到 remuse 及工具；异常查 `%APPDATA%\Claude\logs`（macOS `~/Library/Logs/Claude/mcp*.log`）

## 6. Kimi Code CLI（月之暗面）✅ 原生支持

```bash
kimi mcp add --transport http remuse http://localhost:8002/mcp \
  --header "Authorization: Bearer <YOUR_KEY>"
```

或编辑 `~/.kimi/mcp.json`（项目级 `.kimi-code/mcp.json`；如不一致以本机 `kimi mcp list` 输出为准）：

```json
{ "mcpServers": { "remuse": { "url": "http://localhost:8002/mcp",
  "headers": { "Authorization": "Bearer <YOUR_KEY>" } } } }
```

- 注意：`--transport` 取值是 `http`（不是 `streamableHttp`）
- 验证：`kimi mcp test remuse` 直接列出工具数量与名称；会话内 `/mcp`
- 另：**Kimi Playground**（platform.kimi.com）对话页 →「MCP 服务器设置」→ 添加 URL/传输协议/认证方式亦可。**消费级 Kimi App/网页版不支持自定义 MCP**

## 7. WorkBuddy（腾讯 CodeBuddy 团队）✅ 原生支持

GUI：左侧导航「连接器」→「自定义连接器」→「配置 MCP」→ 粘贴 JSON → 保存 → 回到列表点「启用」：

```json
{ "mcpServers": { "remuse": { "url": "http://localhost:8002/mcp", "transport": "http",
  "headers": { "Authorization": "Bearer <YOUR_KEY>" }, "disabled": false } } }
```

- 如 GUI 编辑器不认 `headers`，用底层 CLI：`codebuddy mcp add --transport http --header "Authorization: Bearer <YOUR_KEY>" -- remuse http://localhost:8002/mcp`
- 验证：MCP 列表 🟢 绿灯；聊天框输入「列出 remuse 下的所有工具」

## 8. Qoder（阿里巴巴）✅ 原生支持

`Qoder 设置 → MCP → 我的服务 → + 添加` → 粘贴 JSON：

```json
{ "mcpServers": { "remuse": { "type": "sse", "url": "http://localhost:8002/mcp",
  "headers": { "Authorization": "Bearer <YOUR_KEY>" } } } }
```

- Qoder 文档只列 STDIO/SSE 两种类型，但**对 Streamable HTTP 按 SSE 方式填 URL 即可，自动识别**；若 `sse` 不生效试 `"type": "http"`
- 验证：「我的服务」列表出现链接图标，展开可见工具；Agent 模式对话触发调用

## 9. Trae（字节跳动，国内/国际版）✅ 原生支持

`设置 → MCP → 添加 → 手动添加` → 填入 JSON（项目级：`.trae/mcp.json` 且需在设置中启用项目级 MCP）：

```json
{ "mcpServers": { "remuse": { "url": "http://localhost:8002/mcp",
  "headers": { "Authorization": "Bearer <YOUR_KEY>" } } } }
```

- Trae CLI：`traecli config edit` 编辑 `trae_cli.yaml`：

```yaml
mcp_servers:
  - name: "remuse"
    type: "http"          # Streamable HTTP 固定取值 http；SSE 为 sse
    url: "http://localhost:8002/mcp"
    headers: { Authorization: "Bearer <YOUR_KEY>" }
```

- 验证：MCP 列表显示已连接、可展开看工具；用 Builder with MCP 对话触发；CLI 会话内 `/mcp`

## 10. Cherry Studio ✅ 原生支持

`设置 → MCP 服务器 → 添加服务器 → 快速创建`：

- 类型：**可流式传输的HTTP（streamableHttp）**
- URL：`http://localhost:8002/mcp`
- 请求头：`Authorization=Bearer <YOUR_KEY>`（GUI 语法为 `Key=Value`，多个头 `;` 分隔）

或 JSON 导入：`{ "mcpServers": { "remuse": { "type": "streamableHttp", "url": "...", "headers": { "Authorization": "Bearer <YOUR_KEY>" } } } }`
（旧版本 JSON 导入有丢 headers 的 bug，遇此走 GUI 请求头框手填）

- 验证：列表中打开开关，显示工具列表；对话中「MCP 设置」勾选后让模型调用

---

## 汇总

| 平台 | 原生远程 HTTP | Bearer 认证 | 推荐方式 |
|---|---|---|---|
| Claude Code | ✅ `type: "http"` | ✅ | `claude mcp add --transport http … --header …` |
| Cursor | ✅ 自动协商 | ✅ `headers` | `mcp.json` 填 url+headers |
| Codex | ✅ 仅 Streamable HTTP | ✅ `bearer_token_env_var` | `~/.codex/config.toml` |
| OpenCode | ✅ `type: "remote"` | ✅，记得 `oauth: false` | `opencode.json` |
| Claude Desktop | ⚠️ 配置文件仅 stdio | 经桥接 | `mcp-remote` + `--allow-http --header …` |
| Kimi Code CLI | ✅ `transport: http` | ✅ | `kimi mcp add … --header …` |
| Kimi Playground | ✅ | ✅ | 网页面板添加（消费级 App 不支持） |
| WorkBuddy | ✅ `transport: "http"` | ✅（GUI 不认 headers 时用 codebuddy CLI） | 连接器 → 自定义连接器 → 配置 MCP |
| Qoder | ✅ 填 URL 自动识别 | ✅（type 先试 `sse` 再试 `http`） | 设置 → MCP → 我的服务 → 添加 |
| Trae | ✅ | ✅ | 设置 → MCP → 手动添加 JSON |
| Cherry Studio | ✅ `streamableHttp` | ✅ 请求头框 `Authorization=Bearer …` | 设置 → MCP 服务器 → 添加 |

## 验证清单（任一平台）

1. 客户端显示工具列表：capture_idea / search_ideas / get_idea / list_recent_ideas / find_related_ideas / mark_idea_as_used
2. 让 Agent 执行：「搜索我的灵感库里关于 XX 的想法」→ 应返回带「不可信内容」提示的结果
3. 打开 Web「日志」页 → 能看到这次调用（agent 名 = 密钥名、工具、参数、返回的灵感数）

## 排障

- **401**：密钥错误/已吊销 →「密钥」页重新创建；确认请求头格式是 `Bearer rm_...`（Bearer 与密钥间一个空格）
- **连接失败**：`docker compose ps` 确认 `mcp` 服务在跑；`curl http://localhost:8002/health` 应返回 `{"status":"ok"}`
- **Claude Desktop 连不上**：检查是否漏了 `--allow-http`；日志在 `%APPDATA%\Claude\logs`
- **OpenCode 反复跳 OAuth**：确认配置里 `"oauth": false`
- **工具搜不到灵感**：确认该密钥的项目授权范围；到「搜索」页用同样关键词先验证

## 安全提醒

- 默认只读：写入权限（capture_idea）按需单独开启；**删除权限永不开放**
- 按项目授权：敏感商业想法所在的项目可以完全不开放给任何 Agent
- 所有调用（含越权尝试）都在「日志」页可查，默认保留 90 天（`AGENT_LOG_RETENTION_DAYS` 可配）

## 来源

- Claude Code / Desktop：code.claude.com/docs/en/mcp、modelcontextprotocol.io、github.com/geelen/mcp-remote
- Cursor：cursor.com/docs/context/mcp
- Codex：developers.openai.com/codex/mcp
- OpenCode：opencode.ai/docs/mcp-servers
- Kimi：moonshotai.github.io/kimi-cli/zh/customization/mcp.html、platform.kimi.com 文档
- WorkBuddy：codebuddy.cn/docs/cli/mcp（同引擎）、cloud.tencent.com 腾讯云文档
- Qoder：docs.qoder.com/zh/user-guide/chat/model-context-protocol、help.aliyun.com 阿里云文档
- Trae：docs.trae.cn/ide_add-mcp-servers、docs.trae.cn/cli_model-context-protocol
- Cherry Studio：docs.cherry-ai.com/advanced-basic/mcp
