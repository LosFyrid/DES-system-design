"""
查询引擎模块
要求：
1. 两阶段检索：向量召回 → Reranker 精排
2. 支持自定义查询参数（top_k, threshold）
3. 返回格式化结果（含来源信息）
"""

from typing import List, Dict, Any, Optional
from llama_index.core import VectorStoreIndex
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.postprocessor.dashscope_rerank import DashScopeRerank
from llama_index.llms.dashscope import DashScope, DashScopeGenerationModels
import logging

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import SETTINGS, DASHSCOPE_API_KEY

logger = logging.getLogger(__name__)


class LargeRAGQueryEngine:
    """查询引擎封装"""

    def __init__(self, index: VectorStoreIndex):
        self.index = index
        self.settings = SETTINGS
        self.api_key = DASHSCOPE_API_KEY

        if not self.api_key:
            raise ValueError(
                "DASHSCOPE_API_KEY is required for query engine. "
                "Please set it in .env file."
            )

        # 初始化 LLM
        self.llm = DashScope(
            model_name=DashScopeGenerationModels.QWEN_MAX,
            api_key=self.api_key,
            temperature=self.settings.llm.temperature,
            max_tokens=self.settings.llm.max_tokens,
        )

        # 初始化 Reranker
        self.reranker = None
        if self.settings.reranker.enabled:
            self.reranker = DashScopeRerank(
                model=self.settings.reranker.model,
                api_key=self.api_key,
                top_n=self.settings.retrieval.rerank_top_n,
            )

        # 构建查询引擎
        self._build_query_engine()

    def _build_query_engine(self):
        """构建查询引擎（含 Reranker）"""
        # Retriever
        retriever = VectorIndexRetriever(
            index=self.index,
            similarity_top_k=self.settings.retrieval.similarity_top_k,
        )

        # Query Engine
        postprocessors = [self.reranker] if self.reranker else []
        self.query_engine = RetrieverQueryEngine.from_args(
            retriever=retriever,
            node_postprocessors=postprocessors,
            llm=self.llm,
        )

    def query(self, query_text: str, **kwargs) -> str:
        """
        执行查询

        Args:
            query_text: 查询文本
            **kwargs: 自定义参数（如 top_k）

        Returns:
            LLM 生成的回答
        """
        logger.info(f"Querying: {query_text}")
        response = self.query_engine.query(query_text)
        return str(response)

    def get_similar_documents(
        self,
        query_text: str,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取相似文档（不使用 LLM 生成）

        Args:
            query_text: 查询文本
            top_k: 返回数量（默认使用配置值）

        Returns:
            文档列表，格式：[{"text": ..., "score": ..., "metadata": ...}]
        """
        top_k = top_k or self.settings.retrieval.rerank_top_n
        retriever = VectorIndexRetriever(
            index=self.index,
            similarity_top_k=self.settings.retrieval.similarity_top_k,
        )

        nodes = retriever.retrieve(query_text)

        # Reranker
        if self.reranker:
            nodes = self.reranker.postprocess_nodes(nodes, query_str=query_text)

        # 格式化结果
        results = []
        for node in nodes[:top_k]:
            results.append({
                "text": node.get_content(),
                "score": node.score,
                "metadata": node.metadata,
            })

        return results
