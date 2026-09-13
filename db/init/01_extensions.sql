-- 向量检索
CREATE EXTENSION IF NOT EXISTS vector;

-- 中文全文检索分词
CREATE EXTENSION IF NOT EXISTS zhparser;
-- PG16 不支持 CREATE TEXT SEARCH CONFIGURATION IF NOT EXISTS，用 DO 块保证幂等
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_ts_config WHERE cfgname = 'chinese_zh'
    ) THEN
        CREATE TEXT SEARCH CONFIGURATION chinese_zh (PARSER = zhparser);
    END IF;
END
$$;
ALTER TEXT SEARCH CONFIGURATION chinese_zh ADD MAPPING FOR n,v,a,i,e,l,j,t WITH simple;
