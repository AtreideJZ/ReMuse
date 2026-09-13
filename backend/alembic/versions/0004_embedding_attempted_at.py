"""回填失败标记：ideas.embedding_attempted_at

配合 backfill_embeddings（code review B5 修复）：
失败的灵感标记尝试时间，1 小时内不重试，避免坏数据阻断/死循环。
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ideas ADD COLUMN embedding_attempted_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE ideas DROP COLUMN IF EXISTS embedding_attempted_at")
