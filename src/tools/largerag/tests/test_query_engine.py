"""
查询引擎单元测试
注意：这些测试需要已构建的索引和 DASHSCOPE_API_KEY
"""

import pytest
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.query_engine import LargeRAGQueryEngine
from core.indexer import LargeRAGIndexer


class TestLargeRAGQueryEngine:
    """LargeRAGQueryEngine 单元测试"""

    @pytest.fixture
    def indexer(self):
        """创建索引器"""
        try:
            return LargeRAGIndexer()
        except ValueError as e:
            pytest.skip(f"Skipping test: {e}")

    @pytest.fixture
    def index(self, indexer):
        """加载或跳过测试"""
        idx = indexer.load_index()
        if idx is None:
            pytest.skip("No index found. Please build index first.")
        return idx

    @pytest.fixture
    def query_engine(self, index):
        """创建查询引擎"""
        try:
            return LargeRAGQueryEngine(index)
        except ValueError as e:
            pytest.skip(f"Skipping test: {e}")

    def test_query_engine_initialization(self, query_engine):
        """测试：查询引擎初始化成功"""
        assert query_engine is not None
        assert query_engine.llm is not None
        assert query_engine.query_engine is not None

    def test_reranker_configuration(self, query_engine):
        """测试：Reranker 配置"""
        # 根据配置检查 reranker
        if query_engine.settings.reranker.enabled:
            assert query_engine.reranker is not None
        else:
            assert query_engine.reranker is None

    @pytest.mark.slow
    def test_get_similar_documents(self, query_engine):
        """测试：检索相似文档（不生成回答）"""
        query = "deep eutectic solvents"
        docs = query_engine.get_similar_documents(query, top_k=3)

        assert isinstance(docs, list)
        if len(docs) > 0:
            assert "text" in docs[0]
            assert "score" in docs[0]
            assert "metadata" in docs[0]

    @pytest.mark.slow
    def test_query_with_llm(self, query_engine):
        """测试：LLM 生成回答（需要 API 调用）"""
        query = "What are deep eutectic solvents?"
        answer = query_engine.query(query)

        assert isinstance(answer, str)
        assert len(answer) > 0


if __name__ == "__main__":
    # 运行测试（跳过 slow 测试）
    pytest.main([__file__, "-v", "-m", "not slow"])
