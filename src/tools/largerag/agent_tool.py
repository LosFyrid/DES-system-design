"""
LargeRAG Agent 工具封装 - 精简版

设计原则：
- 最小化：只实现必需功能
- 一个文件：包含所有核心逻辑
- 直接可用：开箱即用，无需配置
- 易扩展：预留清晰的扩展点

版本：1.0
"""

from typing import Optional
from langchain_core.tools import tool
import logging

from .largerag import LargeRAG

logger = logging.getLogger(__name__)


class LargeRAGTool:
    """
    LargeRAG 工具封装类

    功能：
    - 将 LargeRAG 适配为 LangGraph Agent 可调用的工具
    - 提供简洁的检索接口
    - 返回 Agent 友好的格式化结果

    最简用法：
        tool = LargeRAGTool()
        langchain_tool = tool.as_tool()
        agent = create_react_agent(llm, tools=[langchain_tool])
    """

    def __init__(self):
        """
        初始化 LargeRAG 工具

        自动加载已有索引（如果存在）
        如果索引不存在，会输出警告信息
        """
        self.rag = LargeRAG()

        if self.rag.query_engine is None:
            logger.warning(
                "LargeRAG index not loaded. "
                "Please build index first: rag.index_from_folders('data/literature')"
            )

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0
    ) -> str:
        """
        检索 DES 相关文献

        Args:
            query: 检索查询文本（描述需要什么信息）
            top_k: 返回文档数量（默认 5）
            min_score: 最低相似度分数，0.0-1.0（默认 0.0，不过滤）

        Returns:
            str: 格式化的检索结果，Agent 可直接理解

        扩展点：
        - 修改返回格式：调整 _format_results()
        - 添加过滤逻辑：在此方法中添加
        - 添加缓存：使用 @lru_cache 装饰
        """
        # 检查索引状态
        if self.rag.query_engine is None:
            return "Error: Index not initialized. Please build index first."

        try:
            # 调用 LargeRAG 核心检索
            docs = self.rag.get_similar_docs(query, top_k=top_k)

            # 过滤低分文档
            docs = [d for d in docs if d['score'] >= min_score]

            if not docs:
                return f"No relevant documents found for query: '{query}'"

            # 格式化输出（Agent 友好）
            return self._format_results(query, docs)

        except Exception as e:
            error_msg = f"Retrieval failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return f"Error: {error_msg}"

    def _format_results(self, query: str, docs: list) -> str:
        """
        格式化检索结果（内部方法）

        Args:
            query: 原始查询
            docs: 检索到的文档列表

        Returns:
            str: 格式化的结果字符串

        扩展点：
        - 修改输出格式：编辑此方法
        - 支持多种格式：添加 format_style 参数
        """
        # 构建结果头部
        avg_score = sum(d['score'] for d in docs) / len(docs)
        result = [
            f"=== Literature Retrieval Results ===",
            f"Query: {query}",
            f"Retrieved: {len(docs)} documents (avg score: {avg_score:.3f})",
            ""
        ]

        # 添加每个文档
        for i, doc in enumerate(docs, 1):
            doc_hash = doc['metadata'].get('doc_hash', 'unknown')[:8]
            page = doc['metadata'].get('page_idx', 'N/A')

            result.append(f"[Document {i}] Score: {doc['score']:.3f}")
            result.append(f"Source: {doc_hash}... | Page: {page}")

            # 截断长文本
            text = doc['text']
            if len(text) > 300:
                text = text[:300] + "..."

            result.append(f"Content: {text}")
            result.append("")  # 空行分隔

        return "\n".join(result)

    def as_tool(self):
        """
        转换为 LangChain Tool（供 LangGraph 使用）

        Returns:
            LangChain Tool 对象（可直接传给 create_react_agent）

        扩展点：
        - 修改工具名称和描述：编辑 @tool 装饰器的 docstring
        - 添加更多参数：在内部函数签名中添加
        """
        # 使用闭包捕获 self
        retrieve_func = self.retrieve

        @tool
        def retrieve_des_literature(query: str, top_k: int = 5) -> str:
            """
            Retrieve background knowledge about Deep Eutectic Solvents (DES) from 10,000+ scientific papers.

            Use this tool when you need:
            - Literature facts about DES properties (viscosity, melting point, etc.)
            - Experimental conditions from published research
            - Information about specific DES components or applications
            - Supporting evidence for formulation design decisions

            Args:
                query: Description of what information you need (e.g., "DES viscosity at low temperature")
                top_k: Number of documents to retrieve (default: 5, range: 1-20)

            Returns:
                Formatted retrieval results with document texts and source information
            """
            return retrieve_func(query, top_k)

        return retrieve_des_literature


# ============================================================
# 便捷函数（推荐使用方式）
# ============================================================

def create_largerag_tool():
    """
    便捷函数：一行创建 LargeRAG 工具

    这是推荐的使用方式，简洁明了。

    Returns:
        LangChain Tool 对象

    使用示例：
        from largerag.agent_tool import create_largerag_tool
        from langgraph.prebuilt import create_react_agent

        # 一行创建工具
        tool = create_largerag_tool()

        # 用于 LangGraph Agent
        agent = create_react_agent(llm, tools=[tool])

    扩展点：
    - 添加配置参数：在函数签名中添加
    - 支持多实例：返回 LargeRAGTool 实例而非 Tool
    """
    return LargeRAGTool().as_tool()


# ============================================================
# 扩展示例（注释掉，需要时取消注释）
# ============================================================

# def create_largerag_tool_with_config(
#     default_top_k: int = 5,
#     default_min_score: float = 0.0,
#     max_text_length: int = 300
# ):
#     """
#     带配置的工具创建函数（扩展示例）
#
#     使用方式：
#         tool = create_largerag_tool_with_config(
#             default_top_k=10,
#             default_min_score=0.5
#         )
#     """
#     class ConfiguredLargeRAGTool(LargeRAGTool):
#         def __init__(self):
#             super().__init__()
#             self.default_top_k = default_top_k
#             self.default_min_score = default_min_score
#             self.max_text_length = max_text_length
#
#         def retrieve(self, query: str, top_k: int = None, min_score: float = None) -> str:
#             top_k = top_k or self.default_top_k
#             min_score = min_score or self.default_min_score
#             return super().retrieve(query, top_k, min_score)
#
#     return ConfiguredLargeRAGTool().as_tool()
