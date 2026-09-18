from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

AIStatus = Literal["pending", "processing", "done", "failed"]
IdeaStatus = Literal["captured", "retrieved", "used", "merged", "dropped"]
Source = Literal["web", "pwa", "mcp"]


# ---------- Ideas ----------


class IdeaCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    project_id: UUID | None = None
    # 离线草稿补发时携带的记录时刻。客户端时间可伪造，单用户自部署场景下
    # 接受这一取舍（见 docs 决策），服务端仍做范围校验挡掉离谱值
    captured_at: datetime | None = None

    @field_validator("captured_at")
    @classmethod
    def _check_captured_at(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v > datetime.now(timezone.utc) + timedelta(minutes=10):
            raise ValueError("记录时刻不能是未来时间")
        if v < datetime(2020, 1, 1, tzinfo=timezone.utc):
            raise ValueError("记录时刻超出合理范围")
        return v


class IdeaUpdate(BaseModel):
    """允许修改的字段。raw_content 不在内——原文不可变（F-004）。"""

    project_id: UUID | None = None
    status: IdeaStatus | None = None
    importance: int | None = Field(default=None, ge=1, le=5)
    ai_title: str | None = None
    ai_summary: str | None = None


class IdeaOut(BaseModel):
    id: UUID
    raw_content: str
    ai_title: str | None
    ai_summary: str | None
    ai_maturity: str | None
    ai_key_assumption: str | None
    ai_confidence: float | None
    ai_status: AIStatus
    ai_error: str | None
    ai_suggested_project: str | None
    source: Source
    status: IdeaStatus
    importance: int
    project_id: UUID | None
    project_name: str | None
    tags: list[str]
    created_at: datetime


class IdeaListOut(BaseModel):
    items: list[IdeaOut]
    total: int


class ReuseTraceEvent(BaseModel):
    """单次被 Agent 检索命中的明细（来自 agent_call_logs，受日志保留期影响）。"""

    at: datetime
    agent_name: str
    tool_name: str


class ReuseTraceOut(BaseModel):
    """复用档案（T1.1）：累计计数永久保留在 ideas 冗余列，不随日志清理缩水。"""

    status: IdeaStatus
    retrieved_count: int
    last_retrieved_at: datetime | None
    # 首次被 Agent 检索时间（E3）；老数据未回填时为 None，前端退回两段式展示
    first_retrieved_at: datetime | None = None
    events: list[ReuseTraceEvent]


class SearchIdeaListOut(BaseModel):
    """Web 混合检索响应（E7）：零结果时 near_miss 给出无阈值向量近邻 top-1。"""

    items: list[IdeaOut]
    near_miss: IdeaOut | None = None


# ---------- Projects ----------


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class ProjectOut(BaseModel):
    id: UUID
    name: str
    description: str
    idea_count: int
    created_at: datetime


class ProjectListOut(BaseModel):
    items: list[ProjectOut]


# ---------- Tags ----------


class TagCount(BaseModel):
    name: str
    count: int


class TagListOut(BaseModel):
    items: list[TagCount]
