from __future__ import annotations

from typing import TypeVar

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from cmart.config import get_settings
from cmart.services.llm.base import LLMClient

T = TypeVar("T", bound=BaseModel)

_MODEL = "gemini-2.5-flash"


class GeminiClient(LLMClient):
    def __init__(self) -> None:
        settings = get_settings()
        self._llm = ChatGoogleGenerativeAI(  # type: ignore[call-arg]
            model=_MODEL,
            google_api_key=settings.gemini_api_key,
            temperature=0,
        )

    async def invoke(self, prompt: str) -> str:
        response = await self._llm.ainvoke([HumanMessage(content=prompt)])
        return str(response.content)

    async def invoke_structured(self, prompt: str, schema: type[T]) -> T:
        chain = self._llm.with_structured_output(schema)  # type: ignore[arg-type]
        result = await chain.ainvoke([HumanMessage(content=prompt)])
        if isinstance(result, schema):
            return result
        if isinstance(result, dict):
            return schema(**result)
        # langchain-google-genai tool-call mode returns a list of {type, args} dicts
        if isinstance(result, list) and result and isinstance(result[0], dict):
            args = result[0].get("args", {})
            return schema(**args)
        raise ValueError(f"invoke_structured returned unexpected type {type(result)}: {result!r}")
