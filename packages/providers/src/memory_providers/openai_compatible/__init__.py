from collections.abc import Sequence
from typing import Any

import httpx
from memory_application.ports import EmbeddingBatch, ModelResult, ProviderError


class OpenAICompatibleProvider:
    def __init__(
        self, *, base_url: str, model: str, embedding_model: str, api_key: str | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embedding_model = embedding_model
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def generate_structured(
        self, *, prompt: str, schema: dict[str, Any], timeout_seconds: float
    ) -> ModelResult:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract durable memory candidates from the user content. "
                        "Extract only information explicitly stated about the speaker. "
                        "Never add related knowledge, implications, or background facts. "
                        "The candidate text must faithfully restate the user's statement. "
                        "Return at most one concise candidate. Return only JSON matching the "
                        "supplied schema. Confidence and importance must be numeric values from "
                        "0 to 1. Use only enum values allowed by the schema."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "formation", "schema": schema},
            },
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=self._headers()
                )
            if response.status_code == 429:
                raise ProviderError("rate_limited", retryable=True)
            if response.status_code >= 500:
                raise ProviderError("provider_unavailable", retryable=True)
            response.raise_for_status()
            body = response.json()
            import json

            value = json.loads(body["choices"][0]["message"]["content"])
            usage = body.get("usage", {})
            return ModelResult(
                value,
                "openai_compatible",
                self.model,
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)),
            )
        except httpx.TimeoutException as error:
            raise ProviderError("timeout", retryable=True) from error
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise ProviderError("malformed_output", retryable=False) from error

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    json={"model": self.embedding_model, "input": list(texts)},
                    headers=self._headers(),
                )
            if response.status_code == 429 or response.status_code >= 500:
                raise ProviderError("embedding_unavailable", retryable=True)
            response.raise_for_status()
            vectors = [item["embedding"] for item in response.json()["data"]]
            dimensions = len(vectors[0]) if vectors else 0
            return EmbeddingBatch(vectors, "openai_compatible", self.embedding_model, dimensions)
        except httpx.TimeoutException as error:
            raise ProviderError("timeout", retryable=True) from error
