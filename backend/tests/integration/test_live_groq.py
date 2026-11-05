import os

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool

from app.core.config import Settings
from app.services.llm_provider import GroqProvider


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_GROQ") != "1" or not os.getenv("GROQ_API_KEY"),
    reason="Set RUN_LIVE_GROQ=1 and GROQ_API_KEY to run the live Groq smoke test",
)
async def test_live_groq_provider_smoke() -> None:
    async def ping() -> str:
        return "pong"

    tool = StructuredTool.from_function(
        coroutine=ping,
        name="ping",
        description="Return pong for a provider smoke test.",
    )
    provider = GroqProvider(Settings())
    response = await provider.ainvoke(
        [HumanMessage(content="Respond with one short sentence about code review.")],
        [tool],
    )
    assert response.content

