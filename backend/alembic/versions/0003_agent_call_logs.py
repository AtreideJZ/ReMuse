"""W3：Agent 调用日志表（F-010）"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE agent_call_logs (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            api_key_id        UUID REFERENCES api_keys(id) ON DELETE SET NULL,
            agent_name        TEXT NOT NULL,
            tool_name         TEXT NOT NULL,
            arguments         JSONB NOT NULL DEFAULT '{}',
            returned_idea_ids UUID[] NOT NULL DEFAULT '{}',
            status            TEXT NOT NULL DEFAULT 'ok'
                              CHECK (status IN ('ok', 'denied', 'error')),
            error             TEXT,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX agent_call_logs_created_idx ON agent_call_logs (created_at DESC)"
    )
    op.execute(
        "CREATE INDEX agent_call_logs_agent_idx ON agent_call_logs (agent_name, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_call_logs")
