"""初始数据模型：projects / ideas / tags / idea_tags

对应《产品方案与开发计划》§3.3 定稿模型。
原文不可变由触发器在数据库层强制（F-004）。

注意：asyncpg 不支持单条 execute 内多语句，需逐句执行。
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE projects (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE ideas (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            raw_content     TEXT NOT NULL,
            -- AI 派生内容，与原文物理分列，允许为空（异步填充）
            ai_title        TEXT,
            ai_summary      TEXT,
            ai_maturity     TEXT,
            ai_key_assumption TEXT,
            ai_confidence   REAL,
            ai_status       TEXT NOT NULL DEFAULT 'pending'
                            CHECK (ai_status IN ('pending', 'processing', 'done', 'failed')),
            ai_error        TEXT,
            -- AI 建议的项目名（未绑定，需用户确认后才写入 project_id）
            ai_suggested_project TEXT,
            source          TEXT NOT NULL DEFAULT 'web',
            status          TEXT NOT NULL DEFAULT 'captured'
                            CHECK (status IN ('captured', 'retrieved', 'used', 'merged', 'dropped')),
            importance      SMALLINT NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
            project_id      UUID REFERENCES projects(id) ON DELETE SET NULL,
            embedding       vector(1536),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ideas_created_at_idx ON ideas (created_at DESC)")
    op.execute(
        "CREATE INDEX ideas_project_idx ON ideas (project_id) WHERE project_id IS NOT NULL"
    )
    op.execute(
        """
        CREATE TABLE tags (
            id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL UNIQUE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE idea_tags (
            idea_id UUID NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
            tag_id  UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (idea_id, tag_id)
        )
        """
    )
    # F-004：原文不可变，数据库层强制
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_raw_content_update() RETURNS trigger AS $$
        BEGIN
            IF NEW.raw_content IS DISTINCT FROM OLD.raw_content THEN
                RAISE EXCEPTION 'raw_content is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER ideas_raw_immutable
            BEFORE UPDATE ON ideas
            FOR EACH ROW EXECUTE FUNCTION prevent_raw_content_update()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS ideas_raw_immutable ON ideas")
    op.execute("DROP FUNCTION IF EXISTS prevent_raw_content_update()")
    op.execute("DROP TABLE IF EXISTS idea_tags")
    op.execute("DROP TABLE IF EXISTS tags")
    op.execute("DROP TABLE IF EXISTS ideas")
    op.execute("DROP TABLE IF EXISTS projects")
