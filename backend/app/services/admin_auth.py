"""管理面认证（C1）：Web 管理端点统一要求 ADMIN_TOKEN，fail-closed。

- `/api/agent/*`（Agent 接口）由 services.keys 的 API Key 体系认证，不在此列
- `/api/health` 探活放行
- 未配置 ADMIN_TOKEN 时管理面整体 503（杜绝「忘了配 = 裸奔」）
"""

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..config import settings

_EXEMPT_PREFIXES = ("/api/health", "/api/agent/")


class AdminAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            request.method == "OPTIONS"  # CORS 预检不带凭据
            or not path.startswith("/api/")
            or path.startswith(_EXEMPT_PREFIXES)
        ):
            return await call_next(request)

        if not settings.admin_token:
            return JSONResponse(
                {"detail": "未配置 ADMIN_TOKEN，管理接口已禁用"}, status_code=503
            )

        token = request.headers.get("x-admin-token") or ""
        if not token:
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:].strip()

        if not token or not hmac.compare_digest(token, settings.admin_token):
            return JSONResponse({"detail": "管理令牌无效"}, status_code=401)
        return await call_next(request)
