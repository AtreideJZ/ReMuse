"""API Key：生成、校验、scope 与项目授权（F-009 / F-011）。

- 密钥只在创建时完整返回一次，库中存 SHA-256 哈希
- 吊销即失效（每次请求都查库，无缓存，满足 AC-F011-01 的即时性）
- 项目授权：project_ids 为空 = 全部项目；否则仅所列项目 + 无项目的个人全局灵感
"""

import hashlib
import secrets
from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException

from ..db import get_pool

KEY_PREFIX = "rm_"


@dataclass
class Principal:
    key_id: UUID
    name: str
    scopes: list[str]
    # None = 全部项目；列表 = 授权项目（另加无项目灵感）
    project_ids: list[UUID] | None

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def generate_key() -> tuple[str, str, str]:
    """返回 (完整密钥, 展示用前缀, 哈希)。"""
    token = KEY_PREFIX + secrets.token_urlsafe(32)
    return token, token[:12], hash_key(token)


def hash_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def get_principal(authorization: str | None = Header(default=None)) -> Principal:
    """Agent 接口的认证依赖（AC-F008-02：无 Key 或已吊销 → 401，不泄露内容）。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "缺少有效的 Bearer Token")
    token = authorization.removeprefix("Bearer ").strip()
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, scopes, project_ids FROM api_keys "
        "WHERE key_hash = $1 AND revoked_at IS NULL",
        hash_key(token),
    )
    if row is None:
        raise HTTPException(401, "Token 无效或已吊销")
    return Principal(
        key_id=row["id"],
        name=row["name"],
        scopes=list(row["scopes"]),
        project_ids=list(row["project_ids"]) if row["project_ids"] else None,
    )


async def guard_scope(
    principal: Principal, scope: str, *, tool: str, arguments: dict | None = None
) -> None:
    """scope 校验；越权时记 denied 日志（AC-F008-03）并抛 PermissionError。

    REST 接口经全局异常处理映射为 403；MCP 工具直接以工具错误返回。
    """
    if not principal.has_scope(scope):
        from .logs import log_call

        await log_call(
            principal, tool, arguments or {},
            status="denied", error=f"该密钥没有 {scope} 权限",
        )
        raise PermissionError(f"该密钥没有 {scope} 权限")


async def check_project_access(
    principal: Principal,
    project_id: UUID | None,
    *,
    tool: str | None = None,
    arguments: dict | None = None,
) -> None:
    """校验目标项目是否在授权范围内；越权时记 denied 日志并抛 PermissionError。

    注意：project_ids 为空数组与 None 语义相同——都表示「可访问全部项目」
    （当前产品不提供「零项目权限」的密钥形态，如需区分请另行约定）。
    """
    if principal.project_ids is None or project_id is None:
        return
    if project_id not in principal.project_ids:
        if tool:
            from .logs import log_call

            await log_call(
                principal, tool, arguments or {},
                status="denied", error="越权访问项目",
            )
        raise PermissionError("该密钥无权访问此项目")
