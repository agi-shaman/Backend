import tenacity
from llama_index.llms.gemini.base import Gemini
from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    ChatResponseAsyncGen,
    ChatResponseGen,
    CompletionResponse,
    CompletionResponseAsyncGen,
    CompletionResponseGen,
)
from typing import Any, Sequence, Optional, Dict, Union, List
import google.api_core.exceptions

# Import the retry decorator from our wrappers module
from .api_wrappers import retry_gemini_api_call, RETRY_EXCEPTIONS

class RateLimitedGemini(Gemini):
    """
    Custom Gemini LLM class that incorporates retry logic with exponential backoff.
    """

    @retry_gemini_api_call
    def complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        return super().complete(prompt, formatted=formatted, **kwargs)

    @retry_gemini_api_call
    async def acomplete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        return await super().acomplete(prompt, formatted=formatted, **kwargs)

    @retry_gemini_api_call
    def stream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponseGen:
        # Note: Retrying a generator might restart the entire generation.
        # This is a limitation of applying retry at this level.
        return super().stream_complete(prompt, formatted=formatted, **kwargs)

    @retry_gemini_api_call
    async def astream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponseAsyncGen:
        # Note: Retrying a generator might restart the entire generation.
        # This is a limitation of applying retry at this level.
        return await super().astream_complete(prompt, formatted=formatted, **kwargs)

    @retry_gemini_api_call
    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        return super().chat(messages, **kwargs)

    @retry_gemini_api_call
    async def achat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponse:
        return await super().achat(messages, **kwargs)

    @retry_gemini_api_call
    def stream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponseGen:
        # Note: Retrying a generator might restart the entire generation.
        # This is a limitation of applying retry at this level.
        return super().stream_chat(messages, **kwargs)

    async def astream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponseAsyncGen:
        # Implement retry logic for the async generator iteration
        retrier = tenacity.Retrying(
            wait=tenacity.wait_exponential(multiplier=2, min=10, max=300),
            retry=tenacity.retry_if_exception_type(RETRY_EXCEPTIONS),
            before_sleep=lambda retry_state: print(
                f"Retrying astream_chat iteration after {{retry_state.seconds_since_start:.2f}}s, "
                f"attempt {{retry_state.attempt_number}} failed with {{retry_state.outcome.exception()}}"
            )
        )
        async for attempt in retrier:
            with attempt:
                # This block will be retried
                async_generator = await super().astream_chat(messages, **kwargs)
                async for chunk in async_generator:
                    yield chunk
                # If the loop finishes without exception, the attempt is successful

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)