"""
MinerU 解析服务 HTTP 客户端

主后端通过此客户端调用独立部署的 MinerU 服务 (POST /parse)。
仅依赖 httpx，不引入 magic-pdf 等重依赖。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger


@dataclass
class MinerUResponse:
    """MinerU 解析服务返回结构"""
    markdown: str
    pages: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    parser_version: str
    elapsed_ms: int


class MinerUClient:
    """MinerU 解析服务 HTTP 客户端"""

    MAX_RETRIES = 2

    def __init__(self, base_url: str, timeout: int = 120, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def parse(self, pdf_path: str) -> MinerUResponse:
        """将 PDF 文件发送到 MinerU 服务解析，返回 MinerUResponse。

        失败时抛出异常，由调用方决定是否降级。
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    with open(pdf_path, "rb") as f:
                        resp = await client.post(
                            f"{self.base_url}/parse",
                            files={"file": (pdf_path.split("/")[-1], f, "application/pdf")},
                            headers=self._headers(),
                        )

                if resp.status_code == 200:
                    data = resp.json()
                    return MinerUResponse(
                        markdown=data["markdown"],
                        pages=data.get("pages", []),
                        metadata=data.get("metadata", {}),
                        parser_version=data.get("parser_version", "unknown"),
                        elapsed_ms=data.get("elapsed_ms", 0),
                    )

                error_detail = resp.text[:200]
                if resp.status_code in (413, 503, 504):
                    raise MinerUServiceError(
                        resp.status_code, error_detail
                    )
                raise MinerUServiceError(resp.status_code, error_detail)

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                logger.warning(
                    f"MinerU request attempt {attempt}/{self.MAX_RETRIES} failed: {e}"
                )
                if attempt == self.MAX_RETRIES:
                    raise MinerUServiceError(
                        504, f"Connection failed after {self.MAX_RETRIES} attempts: {e}"
                    ) from e

        raise last_error  # type: ignore[misc]

    async def health_check(self) -> bool:
        """检查 MinerU 服务健康状态"""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{self.base_url}/health",
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False


class MinerUServiceError(Exception):
    """MinerU 服务调用失败"""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        # Map HTTP codes to fallback_reason values
        self._reason_map = {
            413: "file_too_large",
            503: "service_busy",
            504: "service_timeout",
        }
        super().__init__(f"MinerU service error {status_code}: {detail}")

    @property
    def fallback_reason(self) -> str:
        return self._reason_map.get(self.status_code, f"service_error_{self.status_code}")
