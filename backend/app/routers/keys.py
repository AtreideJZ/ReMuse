"""API Key 管理（F-011）：创建 / 列表 / 吊销。

面向用户自己的 Web 管理界面，不做额外认证（自部署单用户前提）。
Agent 访问时使用 Key 走 agent.py 的接口。
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import get_pool
from ..services.keys import generate_key

router = APIRouter(prefix="/keys", tags=["keys"])

_VALID_SCOPES = {"read", "write"}


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # 默认只读（AC-F011-02：创建时默认不勾 write）
    scopes: list[str] = ["read"]
    # 空 = 全部项目
    project_ids: list[UUID] = []


class KeyOut(BaseModel):
    id: UUID
    name: str
    prefix: str
    scopes: list[str]
    project_ids: list[UUID]
    created_at: str
    revoked_at: str | None


class KeyCreatedOut(KeyOut):
    key: str  # 完整密钥，仅此一次返回


def _to_out(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "prefix": row["prefix"],
        "scopes": list(row["scopes"]),
        "project_ids": list(row["project_ids"]),
        "created_at": row["created_at"].isoformat(),
        "revoked_at": row["revoked_at"].isoformat() if row["revoked_at"] else None,
    }


@router.get("")
async def list_keys():
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM api_keys ORDER BY created_at DESC"
    )
    return {"items": [_to_out(r) for r in rows]}


@router.post("", status_code=201)
async def create_key(body: KeyCreate):
    scopes = sorted(set(body.scopes))
    if not scopes or not set(scopes) <= _VALID_SCOPES:
        raise HTTPException(400, f"scopes 只能是 {sorted(_VALID_SCOPES)} 的子集")

    pool = await get_pool()
    if body.project_ids:
        found = await pool.fetch(
            "SELECT id FROM projects WHERE id = ANY($1)", body.project_ids
        )
        if len(found) != len(set(body.project_ids)):
            raise HTTPException(404, "包含不存在的项目")

    token, prefix, key_hash = generate_key()
    row = await pool.fetchrow(
        "INSERT INTO api_keys (name, prefix, key_hash, scopes, project_ids) "
        "VALUES ($1, $2, $3, $4, $5) RETURNING *",
        body.name.strip(),
        prefix,
        key_hash,
        scopes,
        list(set(body.project_ids)),
    )
    return {**_to_out(row), "key": token}


@router.post("/{key_id}/revoke")
async def revoke_key(key_id: UUID):
    pool = await get_pool()
    row = await pool.fetchrow(
        "UPDATE api_keys SET revoked_at = now() "
        "WHERE id = $1 AND revoked_at IS NULL RETURNING *",
        key_id,
    )
    if row is None:
        raise HTTPException(404, "密钥不存在或已吊销")
    return _to_out(row)
