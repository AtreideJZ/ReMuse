FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS runner
WORKDIR /app
RUN useradd -m -u 1000 app
COPY --from=builder /root/.local /home/app/.local
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY app/ ./app/
ENV PATH=/home/app/.local/bin:$PATH
USER app
# 启动前先跑数据库迁移，保证 compose up 一键可用
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
