FROM pgvector/pgvector:pg16

# 编译安装 scws + zhparser，为 PostgreSQL 提供中文全文检索分词。
# 这是混合检索（BM25 + 向量）的关键词侧基础：PG 内置分词对中文几乎不可用。
#
# 供应链约定（开源发布要求）：
# - 全部走 HTTPS，且下载后校验 SHA-256，防中间人替换
# - zhparser 固定 commit（而非浮动 master），保证构建可复现、NOTICE 归属可固定
# 升级任一组件时：同步更新版本/commit 与对应校验和，并更新根目录 NOTICE。
ARG SCWS_VERSION=1.2.3
ARG SCWS_SHA256=60d50ac3dc42cff3c0b16cb1cfee47d8cb8c8baa142a58bc62854477b81f1af5
ARG ZHPARSER_COMMIT=2e995c4df672563992b4d7a147b8fa2d0d4cda6c
ARG ZHPARSER_SHA256=ce5d5e21a1c1f8b3f466998fba0efe51928aad6e12026b5e30ecd2afbfa3285e

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential ca-certificates wget postgresql-server-dev-16; \
    cd /tmp; \
    # scws（zhparser 依赖的中文分词库）
    wget -q -O scws.tar.bz2 "https://www.xunsearch.com/scws/down/scws-${SCWS_VERSION}.tar.bz2"; \
    echo "${SCWS_SHA256}  scws.tar.bz2" | sha256sum -c -; \
    tar xjf scws.tar.bz2; \
    cd "scws-${SCWS_VERSION}"; \
    ./configure; \
    make install; \
    # zhparser（PostgreSQL 中文分词扩展）
    cd /tmp; \
    wget -q -O zhparser.tar.gz "https://codeload.github.com/amutu/zhparser/tar.gz/${ZHPARSER_COMMIT}"; \
    echo "${ZHPARSER_SHA256}  zhparser.tar.gz" | sha256sum -c -; \
    tar xzf zhparser.tar.gz; \
    cd "zhparser-${ZHPARSER_COMMIT}"; \
    SCWS_HOME=/usr/local make; \
    SCWS_HOME=/usr/local make install; \
    # 清理编译工具链，保持镜像精简
    cd /; \
    rm -rf /tmp/scws-"${SCWS_VERSION}" /tmp/scws.tar.bz2 /tmp/zhparser-"${ZHPARSER_COMMIT}" /tmp/zhparser.tar.gz; \
    apt-get purge -y build-essential wget postgresql-server-dev-16; \
    apt-get autoremove -y; \
    rm -rf /var/lib/apt/lists/*

COPY init/ /docker-entrypoint-initdb.d/
