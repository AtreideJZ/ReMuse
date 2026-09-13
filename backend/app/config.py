import ipaddress
from urllib.parse import urlparse

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。全部可通过环境变量或 .env 覆盖。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://flash:flash@localhost:5432/flash"

    # 管理面认证令牌（Web 管理端点必填；未配置时管理接口整体禁用，fail-closed）
    admin_token: str = ""

    # HTTPS 部署时置 true 启用 HSTS（本地 http 下启用会导致浏览器报错）
    enable_hsts: bool = False

    # 允许 LLM/Embedding base_url 指向私网/回环地址（本地自建网关如 Ollama 时开启）
    # 注意：本字段必须位于两个 base_url 之前，校验器按声明顺序读取它
    allow_private_base_url: bool = False

    # LLM（AI 结构化），兼容 OpenAI Chat Completions 接口
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # Embedding，兼容 OpenAI Embeddings 接口
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # 灵感原文长度上限（AC-F001-03）
    max_content_length: int = 10000

    # Agent 调用日志保留天数（AC-F010-03，超期自动清理）
    agent_log_retention_days: int = 90

    # AI 结构化请求超时（秒）
    llm_timeout: float = 60.0
    embedding_timeout: float = 30.0

    @field_validator("llm_base_url", "embedding_base_url")
    @classmethod
    def _check_base_url(cls, v: str, info: ValidationInfo) -> str:
        """校验 LLM/Embedding 服务地址：scheme 合法 + 默认拒绝私网/回环（防配置层 SSRF）。

        本地自建网关（如 Ollama）可设 ALLOW_PRIVATE_BASE_URL=true 显式放行。
        """
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(f"非法 base_url（仅支持 http/https）: {v}")

        host = parsed.hostname
        if host == "localhost" or host.endswith(".localhost"):
            is_private = True
        else:
            try:
                ip = ipaddress.ip_address(host)
                is_private = (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_reserved
                    or ip.is_multicast
                    or ip.is_unspecified
                )
            except ValueError:
                is_private = False  # 域名，DNS 解析层面的风险不在此校验范围

        allow_private = bool(info.data.get("allow_private_base_url", False))
        if is_private and not allow_private:
            raise ValueError(
                f"base_url 禁止指向私网/回环地址: {v}"
                "（本地自建网关请显式设置 ALLOW_PRIVATE_BASE_URL=true）"
            )
        return v.rstrip("/")


settings = Settings()
