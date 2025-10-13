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
from llama_index.llms.dashscope import DashScope
import logging

from ..config.settings import SETTINGS, DASHSCOPE_API_KEY

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

        # 初始化 LLM（使用配置文件中的模型）
        self.llm = DashScope(
            model_name=self.settings.llm.model,
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
        # Retriever（支持相似度阈值）
        retriever_kwargs = {
            "index": self.index,
            "similarity_top_k": self.settings.retrieval.similarity_top_k,
        }

        # 如果设置了相似度阈值（> 0），则启用过滤
        if self.settings.retrieval.similarity_threshold > 0:
            retriever_kwargs["similarity_cutoff"] = self.settings.retrieval.similarity_threshold
            logger.info(f"Similarity threshold enabled: {self.settings.retrieval.similarity_threshold}")

        retriever = VectorIndexRetriever(**retriever_kwargs)

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
            top_k: 最终返回数量（默认使用 rerank_top_n 配置值）

        Returns:
            文档列表，格式：[{"text": ..., "score": ..., "metadata": ...}]

        工作流程：
            1. 向量召回 similarity_top_k 个候选文档
            2. Reranker 精排（如果启用）
            3. 返回前 top_k 个结果
        """
        # 确定最终返回数量
        final_top_k = top_k or self.settings.retrieval.rerank_top_n

        # 动态调整候选池大小（确保足够）
        # 如果用户要的数量超过配置的候选池，自动扩大候选池
        required_candidates = max(
            final_top_k * 2,  # 候选池至少是最终返回数的2倍（给 Reranker 足够选择空间）
            self.settings.retrieval.similarity_top_k
        )

        # 向量召回（支持相似度阈值）
        retriever_kwargs = {
            "index": self.index,
            "similarity_top_k": required_candidates,
        }

        # 如果动态调整了候选池，记录日志
        if required_candidates > self.settings.retrieval.similarity_top_k:
            logger.info(
                f"Auto-adjusted similarity_top_k from {self.settings.retrieval.similarity_top_k} "
                f"to {required_candidates} to satisfy top_k={final_top_k}"
            )

        # 如果设置了相似度阈值（> 0），则启用过滤
        if self.settings.retrieval.similarity_threshold > 0:
            retriever_kwargs["similarity_cutoff"] = self.settings.retrieval.similarity_threshold

        retriever = VectorIndexRetriever(**retriever_kwargs)
        nodes = retriever.retrieve(query_text)

        # Reranker 精排（如果启用）
        if self.reranker:
            # 创建临��� reranker 实例，确保返回足够多的结果
            from llama_index.postprocessor.dashscope_rerank import DashScopeRerank
            reranker = DashScopeRerank(
                model=self.settings.reranker.model,
                api_key=self.api_key,
                top_n=max(final_top_k, self.settings.retrieval.rerank_top_n),
            )
            nodes = reranker.postprocess_nodes(nodes, query_str=query_text)

        # 格式化结果并返回前 top_k 个
        results = []
        for node in nodes[:final_top_k]:
            results.append({
                "text": node.get_content(),
                "score": node.score,
                "metadata": node.metadata,
            })

        return results
