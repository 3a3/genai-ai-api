"""Azure OpenAI クライアント。Managed Identity 経由で chat / embeddings を呼ぶ。"""

from __future__ import annotations

import json
import logging

from azure.core.credentials import TokenCredential
from azure.identity import get_bearer_token_provider
from openai import AzureOpenAI

logger = logging.getLogger(__name__)


class AOAIClient:
    def __init__(
        self,
        endpoint: str,
        chat_deployment: str,
        embedding_deployment: str,
        api_version: str,
        credential: TokenCredential,
    ) -> None:
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        self._client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_version=api_version,
            azure_ad_token_provider=token_provider,
        )
        self._chat_deployment = chat_deployment
        self._embedding_deployment = embedding_deployment

    def chat(
        self,
        system: str,
        user: str,
        temperature: float = 1.0,
        max_tokens: int = 2048,
    ) -> str:
        # gpt-5 系は max_completion_tokens を要求し、temperature は 1.0 のみ許容
        resp = self._client.chat.completions.create(
            model=self._chat_deployment,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_completion_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def chat_json(
        self,
        system: str,
        user: str,
        temperature: float = 1.0,
        max_tokens: int = 2048,
    ) -> dict:
        """JSON モード（response_format=json_object）で呼んで dict を返す。"""
        resp = self._client.chat.completions.create(
            model=self._chat_deployment,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_completion_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        content = (resp.choices[0].message.content or "").strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            logger.warning("failed to parse JSON from LLM: %s; content=%r", exc, content[:300])
            return {}

    def embed(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(
            model=self._embedding_deployment,
            input=[text],
        )
        return resp.data[0].embedding
