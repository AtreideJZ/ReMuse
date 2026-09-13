"""复用档案（T1.1）：ideas 冗余累计列 + agent_call_logs 命中明细 GIN 索引

retrieved_count / last_retrieved_at 永久保留累计值——调用日志有保留期清理
（services/logs.py: purge_old_logs），直接聚合日志会让「被检索 N 次」随时间缩水；
GIN 索引支撑「某条灵感被谁检索过」的明细查询（$1 = ANY(returned_idea_ids)），
否则随日志增长退化为全表扫描。
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ideas ADD COLUMN retrieved_count INT NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE ideas ADD COLUMN last_retrieved_at TIMESTAMPTZ")
    op.execute(
        "CREATE INDEX agent_call_logs_returned_ids_idx "
        "ON agent_call_logs USING GIN (returned_idea_ids)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS agent_call_logs_returned_ids_idx")
    op.execute("ALTER TABLE ideas DROP COLUMN IF EXISTS retrieved_count")
    op.execute("ALTER TABLE ideas DROP COLUMN IF EXISTS last_retrieved_at")
