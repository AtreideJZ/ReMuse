"""Embedding 抽象层。

MVP 默认 OpenAI 兼容 Embeddings API；后续本地 ONNX（fastembed/bge）
只需新增一个 Embedder 实现并在 get_embedder() 中切换（方案 §2.6-2）。
"""

from abc import ABC, abstractmethod

import httpx

from ..config import settings


class Embedder(ABC):
    @abstractmethod
    def configured(self) -> bool:
        """是否已配置可用（如 API Key 是否存在）。"""

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...


class OpenAIEmbedder(Embedder):
    def __init__(self) -> None:
        self._base_url = settings.embedding_base_url.rstrip("/")
        self._api_key = settings.embedding_api_key
        self._model = settings.embedding_model

    def configured(self) -> bool:
        return bool(self._api_key)

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=settings.embedding_timeout) as client:
            resp = await client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": text},
            )
            resp.raise_for_status()
            data = resp.json()["data"][0]["embedding"]
            if len(data) != settings.embedding_dim:
                raise ValueError(
                    f"embedding 维度 {len(data)} 与配置 EMBEDDING_DIM={settings.embedding_dim} 不一致"
                )
            return data


def get_embedder() -> Embedder:
    return OpenAIEmbedder()


def to_vector_literal(vec: list[float]) -> str:
    """asyncpg 不认识 pgvector 类型，以字符串字面量 + ::vector 显式转换写入。"""
    return "[" + ",".join(f"{x:.8g}" for x in vec) + "]"
