try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover - older standalone CoreRAG envs
    from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate

try:
    from autology_constructor.idea.common.llm_provider import _wrap_with_retry
except Exception:  # pragma: no cover
    _wrap_with_retry = None

# 全局LLM实例（可配置参数和复用实例）
_llm_instance = ChatOpenAI(model="gpt-4o", temperature=0.7, max_retries=0)
llm_instance = (
    _wrap_with_retry(_llm_instance, "CoreRAG helper ChatOpenAI model=gpt-4o")
    if _wrap_with_retry
    else _llm_instance
)

_reasoning_llm_instance = ChatOpenAI(model="o3-mini", max_retries=0)
reasoning_llm_instance = (
    _wrap_with_retry(_reasoning_llm_instance, "CoreRAG helper ChatOpenAI model=o3-mini")
    if _wrap_with_retry
    else _reasoning_llm_instance
)
    
