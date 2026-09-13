# 更新日志

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

`0.x` 阶段：接口（MCP 工具签名、`/api/agent/*`、数据库 schema）可能变更，破坏性变更会在此标注并附迁移说明。

## [0.1.0] - 2026-09-13

首个公开发布版本。

### 功能

- 快速记录灵感（原文不可变，数据库触发器强制），AI 异步结构化（标题 / 摘要 / 标签 / 项目建议，失败可重试）
- 项目空间 CRUD、标签筛选
- 混合检索：中文全文（zhparser）+ 向量（pgvector）+ RRF 融合
- MCP Server（Streamable HTTP，六个工具 + `ideas://` 资源）与 Agent REST 接口（`/api/agent/*`）
- API Key 管理：只读默认 / 按项目授权 / 吊销即失效
- Agent 调用日志（含越权记录）与灵感复用率统计
- 复用追踪闭环：Agent 命中自动记 retrieved，`mark_idea_as_used` 回写归因
- 全量数据导出（JSON，含原文与向量）
- PWA：添加到主屏、离线草稿联网自动补发、分享目标（Android）
