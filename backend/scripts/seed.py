"""搜索验收种子数据：插入 30 条真实感灵感 + 2 个项目。

直接写库（不触发 LLM 结构化，节省调用），Embedding 由 backfill 补齐。
幂等：ideas 表已有 >= 20 条时跳过。

用法（在 backend/ 下）：
    set -a && source ../.env && set +a
    .venv/Scripts/python scripts/seed.py
"""

import asyncio
import os

import asyncpg

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://flash:flash@localhost:5432/flash"
)

PROJECTS = [
    ("校园效率工具", "面向大学生的学习效率产品"),
    ("Agent 基础设施", "Agent 开发与记忆相关探索"),
]

# (内容, 项目名或 None)
IDEAS: list[tuple[str, str | None]] = [
    # —— AC-F005-01 语义召回目标（查询「学生学习计划」应进前 5）
    ("做一个根据考试日期自动规划复习的Agent", "校园效率工具"),
    # —— AC-F005-02 关键词精确召回目标（查询「pgvector」应排第 1）
    ("用 pgvector 的 IVFFlat 索引做个人知识库的向量检索，小数据量记得调 probes", "Agent 基础设施"),
    # —— 校园/学习方向
    ("课程表拍照自动识别并生成日历提醒", "校园效率工具"),
    ("根据作业截止时间自动拆分每天的学习任务", "校园效率工具"),
    ("考试周自动屏蔽娱乐 App 的专注工具", "校园效率工具"),
    ("用 Anki 卡片自动生成器帮医学生背书", "校园效率工具"),
    ("小组作业协作时自动汇总每个人进度的机器人", "校园效率工具"),
    ("图书馆座位占用预测，结合课程表数据", "校园效率工具"),
    # —— Agent 方向
    ("给 Claude Code 加一个跨 session 的长期记忆层", "Agent 基础设施"),
    ("Agent 调用工具前先查历史成功率，动态选工具", "Agent 基础设施"),
    ("用 RRF 融合 BM25 和向量检索提升记忆召回", "Agent 基础设施"),
    ("MCP Server 的权限设计：默认只读、按项目授权", "Agent 基础设施"),
    ("把每天的 Agent 对话自动提炼成决策日志", "Agent 基础设施"),
    ("本地 ONNX 跑 bge 中文向量模型，隐私场景不用出域", "Agent 基础设施"),
    ("Prompt Injection 防御：Agent 读到的笔记都按不可信数据处理", "Agent 基础设施"),
    # —— 内容创作方向
    ("做一期视频：我如何让 AI 记住我三个月前的想法", None),
    ("写一篇对比：Mem、Obsidian、Notion AI 的 Agent 支持现状", None),
    ("灵感复用率这个概念值得单独写篇文章", None),
    ("把失败的副业项目复盘做成 newsletter 系列", None),
    # —— 生活/效率方向
    ("每周日晚上自动生成下周三件最重要的事", None),
    ("记账 App 太复杂了，想要一个语音一句话记账", None),
    ("健身计划根据睡眠数据自动调整强度", None),
    ("读书笔记自动关联到正在写的文章草稿", None),
    ("用 vision 模型整理手机截图里的灵感", None),
    ("家庭共享的购物清单，Agent 自动按超市分区排序", None),
    ("旅行规划 Agent：输入预算和天数输出每日行程", None),
    ("睡前语音记录想法，早上生成待办清单", None),
    ("一个帮你拒绝无效会议的日历助手", None),
    ("代码 review 时自动关联历史类似 bug 的记录", None),
    ("给父母用的语音问答：怎么用手机、怎么挂号", None),
    ("微信读书划线的内容自动同步到灵感库", None),
]


async def main() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        count = await conn.fetchval("SELECT COUNT(*) FROM ideas")
        if count >= 20:
            print(f"已有 {count} 条灵感，跳过种子插入")
            return

        project_ids: dict[str, str] = {}
        for name, desc in PROJECTS:
            pid = await conn.fetchval(
                "INSERT INTO projects (name, description) VALUES ($1, $2) "
                "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
                name,
                desc,
            )
            project_ids[name] = pid

        inserted = 0
        for content, project_name in IDEAS:
            await conn.execute(
                "INSERT INTO ideas (raw_content, project_id, source, ai_status) "
                "VALUES ($1, $2, 'web', 'done')",
                content,
                project_ids.get(project_name) if project_name else None,
            )
            inserted += 1
        print(f"插入 {inserted} 条种子灵感，项目：{list(project_ids)}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
