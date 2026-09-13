"""W2：混合检索基础设施 + API Key 表

- ideas.embedding 维度对齐 EMBEDDING_DIM（当前配置 bge-m3 = 1024）
- ideas.tsv 中文全文检索生成列 + GIN 索引
- embedding IVFFlat 索引（个人规模下查询设 probes=100 近似精确召回；数据量大后再调优）
- api_keys：Agent 访问密钥（哈希存储，吊销即失效）
"""

import os

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# 维度必须与 .env 的 EMBEDDING_DIM 一致；换模型改维度后需重建该列数据
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1536"))


def upgrade() -> None:
    # 向量维度对齐当前 Embedding 模型（旧数据 embedding 均为 NULL，直接改类型无损）
    op.execute(f"ALTER TABLE ideas ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM})")

    # 中文全文检索生成列 + GIN 索引（关键词侧，AC-F005-02 的精确召回保障）
    op.execute(
        """
        ALTER TABLE ideas
        ADD COLUMN tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('chinese_zh', raw_content)) STORED
        """
    )
    op.execute("CREATE INDEX ideas_tsv_gin ON ideas USING GIN (tsv)")

    # 向量索引（lists=100 对应 < 数十万行规模；小数据量下查询需 probes=100 保证召回）
    op.execute(
        "CREATE INDEX ideas_embedding_ivfflat ON ideas "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # Agent 访问密钥（F-011）
    op.execute(
        """
        CREATE TABLE api_keys (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        TEXT NOT NULL,
            prefix      TEXT NOT NULL,
            key_hash    TEXT NOT NULL UNIQUE,
            scopes      TEXT[] NOT NULL DEFAULT '{read}',
            -- 空数组 = 可访问全部项目；否则仅所列项目 + 个人全局灵感（F-009）
            project_ids UUID[] NOT NULL DEFAULT '{}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at  TIMESTAMPTZ
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS api_keys")
    op.execute("DROP INDEX IF EXISTS ideas_embedding_ivfflat")
    op.execute("DROP INDEX IF EXISTS ideas_tsv_gin")
    op.execute("ALTER TABLE ideas DROP COLUMN IF EXISTS tsv")
    # 与 upgrade 保持同一维度来源，避免降级后类型与配置不符
    op.execute(f"ALTER TABLE ideas ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM})")
