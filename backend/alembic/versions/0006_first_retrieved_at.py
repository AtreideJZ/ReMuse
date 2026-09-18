"""第三轮趣味体验（E3）：ideas 增加 first_retrieved_at 冗余列

复用档案「沉睡叙事」需要真实的首次检索时间。日志有保留期清理
（services/logs.py: purge_old_logs），用 events 最早一条近似会把不准确的
数字讲成事实，故与 retrieved_count / last_retrieved_at 同族冗余：
mark_retrieved 时以 COALESCE(first_retrieved_at, now()) 赋值。
老数据不回填（真实首次时间已无法还原），前端对 NULL 退回两段式展示。
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ideas ADD COLUMN first_retrieved_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE ideas DROP COLUMN IF EXISTS first_retrieved_at")
