import os
from langchain_openai import ChatOpenAI
from langchain_community.chat_models.tongyi import ChatTongyi
# from langchain_anthropic import ChatAnthropic

import logging
from typing import Any, Dict, Optional

try:
    from agent.utils.llm_retry import (
        LLMRetryPolicy,
        async_call_with_retry,
        call_with_retry,
        coerce_retry_policy,
    )
except Exception:  # pragma: no cover - standalone CoreRAG usage outside DES
    LLMRetryPolicy = None  # type: ignore[assignment]
    async_call_with_retry = None  # type: ignore[assignment]
    call_with_retry = None  # type: ignore[assignment]
    coerce_retry_policy = None  # type: ignore[assignment]


try:
    from config.settings import LLM_CONFIG, OPENAI_API_KEY
except ImportError as e:
    print(f"Error: Could not import configuration from config.settings: {e}. ")

logger = logging.getLogger(__name__)


class RetryableLLMRunnable:
    """Delegate wrapper that applies DES LLM retry policy to LangChain calls."""

    def __init__(
        self,
        inner: Any,
        *,
        retry_policy: Optional[Any] = None,
        operation_name: str = "CoreRAG LLM call",
    ):
        self._inner = inner
        self._retry_policy = retry_policy
        self._operation_name = operation_name

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        def _invoke_once() -> Any:
            return self._inner.invoke(*args, **kwargs)

        if call_with_retry and self._retry_policy is not None:
            return call_with_retry(
                _invoke_once,
                policy=self._retry_policy,
                operation_name=self._operation_name,
                logger=logger,
            )
        return _invoke_once()

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        async def _ainvoke_once() -> Any:
            return await self._inner.ainvoke(*args, **kwargs)

        if async_call_with_retry and self._retry_policy is not None:
            return await async_call_with_retry(
                _ainvoke_once,
                policy=self._retry_policy,
                operation_name=f"{self._operation_name} async",
                logger=logger,
            )
        return await _ainvoke_once()

    def stream(self, *args: Any, **kwargs: Any) -> Any:
        def _stream_once() -> Any:
            return self._inner.stream(*args, **kwargs)

        if call_with_retry and self._retry_policy is not None:
            return call_with_retry(
                _stream_once,
                policy=self._retry_policy,
                operation_name=f"{self._operation_name} stream",
                logger=logger,
            )
        return _stream_once()

    def batch(self, *args: Any, **kwargs: Any) -> Any:
        def _batch_once() -> Any:
            return self._inner.batch(*args, **kwargs)

        if call_with_retry and self._retry_policy is not None:
            return call_with_retry(
                _batch_once,
                policy=self._retry_policy,
                operation_name=f"{self._operation_name} batch",
                logger=logger,
            )
        return _batch_once()

    def bind_tools(self, *args: Any, **kwargs: Any) -> "RetryableLLMRunnable":
        return RetryableLLMRunnable(
            self._inner.bind_tools(*args, **kwargs),
            retry_policy=self._retry_policy,
            operation_name=f"{self._operation_name} tools",
        )

    def with_structured_output(self, *args: Any, **kwargs: Any) -> "RetryableLLMRunnable":
        return RetryableLLMRunnable(
            self._inner.with_structured_output(*args, **kwargs),
            retry_policy=self._retry_policy,
            operation_name=f"{self._operation_name} structured output",
        )


def _current_retry_policy() -> Optional[Any]:
    if coerce_retry_policy is None:
        return None
    return coerce_retry_policy()


def _wrap_with_retry(inner: Any, operation_name: str) -> RetryableLLMRunnable:
    return RetryableLLMRunnable(
        inner,
        retry_policy=_current_retry_policy(),
        operation_name=operation_name,
    )


class ReasoningCompatibleChatOpenAI(ChatOpenAI):
    """
    ChatOpenAI always includes `temperature` in its request payload.

    OpenAI GPT-5.* models raise an error when `reasoning_effort` is enabled
    (i.e., not "none") *and* sampling params like `temperature/top_p/logprobs`
    are present. We therefore strip these fields from the payload whenever
    reasoning is enabled.
    """

    @property
    def _default_params(self) -> Dict[str, Any]:
        params = super()._default_params

        reasoning_effort = params.get("reasoning_effort")
        if reasoning_effort is None and hasattr(self, "model_kwargs"):
            reasoning_effort = (self.model_kwargs or {}).get("reasoning_effort")

        if reasoning_effort is not None and str(reasoning_effort).strip().lower() != "none":
            # GPT-5.* parameter compatibility: remove unsupported sampling params.
            params.pop("temperature", None)
            params.pop("top_p", None)
            params.pop("logprobs", None)
            params.pop("top_logprobs", None)

        return params


def get_default_llm():
    """Instantiates and returns the default LLM based on configuration."""
    model_name = LLM_CONFIG.get('model', 'gpt-4.1-mini')
    temperature = LLM_CONFIG.get('temperature', 0)
    openai_api_key_to_use = OPENAI_API_KEY if OPENAI_API_KEY and OPENAI_API_KEY != "default_api_key" else None

    if model_name:
        if not openai_api_key_to_use:
            # Check env var as a last resort if needed, or raise error
            openai_api_key_to_use = os.getenv("OPENAI_API_KEY")
            if not openai_api_key_to_use:
                 raise ValueError("OpenAI API Key is not configured in  environment variables.")
        # Extract openai_api_base if present in config.
        # Keep model/temperature as explicit args, and handle OpenAI-only fields
        # (reasoning_effort/verbosity) via model_kwargs.
        llm_params = {
            k: v
            for k, v in LLM_CONFIG.items()
            if k not in ['model', 'temperature', 'reasoning_effort', 'verbosity']
        }

        # Rename openai_api_base to base_url for newer ChatOpenAI versions
        if 'openai_api_base' in llm_params:
            llm_params['base_url'] = llm_params.pop('openai_api_base')

        # OpenAI-only reasoning knobs (safe to ignore for non-OpenAI endpoints)
        reasoning_effort = LLM_CONFIG.get("reasoning_effort")
        verbosity = LLM_CONFIG.get("verbosity")

        # Ensure we keep any existing model_kwargs (if provided) and append.
        model_kwargs: Dict[str, Any] = llm_params.get("model_kwargs") or {}
        if reasoning_effort is not None:
            model_kwargs["reasoning_effort"] = reasoning_effort
        if verbosity is not None:
            model_kwargs["verbosity"] = verbosity
        if model_kwargs:
            llm_params["model_kwargs"] = model_kwargs

        retry_policy = _current_retry_policy()
        if retry_policy is not None and retry_policy.sdk_max_retries is not None:
            llm_params.setdefault("max_retries", int(retry_policy.sdk_max_retries))

        llm = ReasoningCompatibleChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            openai_api_key=openai_api_key_to_use,
            **llm_params
        )
        return _wrap_with_retry(llm, f"CoreRAG ChatOpenAI model={model_name}")
    else:
        raise ValueError(f"Only support OpenAI models, model name specified in LLM_CONFIG: {model_name}")

def get_qwen_llm():
    # return ChatOllama(
    #         model="myaniu/qwen2.5-1m:14b",
    #         base_url="https://30a6-36-5-153-246.ngrok-free.app",
    #         temperature=0,
    #         max_tokens=8192,
    #     )
    llm = ChatTongyi(
            model_name="qwen3-14b",
            model_kwargs={
                "temperature": 0,
                "enable_thinking": False,
                "max_tokens": 8192,
            }
        )
    return _wrap_with_retry(llm, "CoreRAG ChatTongyi model=qwen3-14b")
# Cached instance logic
DEFAULT_LLM_INSTANCE = None
def get_cached_default_llm(qwen=False):
    """Returns a cached instance of the default LLM."""
    global DEFAULT_LLM_INSTANCE
    if DEFAULT_LLM_INSTANCE is None:
        if qwen:
            DEFAULT_LLM_INSTANCE = get_qwen_llm()
        else:
            DEFAULT_LLM_INSTANCE = get_default_llm()
    return DEFAULT_LLM_INSTANCE 
