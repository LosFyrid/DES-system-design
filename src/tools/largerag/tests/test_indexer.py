"""
索引构建器单元测试
注意：这些测试需要 DASHSCOPE_API_KEY 和 Redis（如果启用缓存）
"""

import pytest
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.indexer import LargeRAGIndexer
from llama_index.core import Document


class TestLargeRAGIndexer:
    """LargeRAGIndexer 单元测试"""

    @pytest.fixture
    def indexer(self):
        """创建 LargeRAGIndexer 实例（需要 API Key）"""
        try:
            return LargeRAGIndexer()
        except ValueError as e:
            pytest.skip(f"Skipping test: {e}")

    @pytest.fixture
    def sample_documents(self):
        """创建测试文档"""
        docs = [
            Document(
                text="Deep eutectic solvents are a new class of green solvents.",
                metadata={"doc_hash": "test1", "page_idx": 0}
            ),
            Document(
                text="DES consists of hydrogen bond acceptors and donors.",
                metadata={"doc_hash": "test2", "page_idx": 1}
            ),
        ]
        return docs

    def test_indexer_initialization(self, indexer):
        """测试：索引器初始化成功"""
        assert indexer is not None
        assert indexer.embed_model is not None
        assert indexer.chroma_client is not None
        assert indexer.pipeline is not None

    def test_pipeline_configuration(self, indexer):
        """测试：Pipeline 配置正确"""
        assert indexer.pipeline is not None
        assert len(indexer.pipeline.transformations) >= 2  # SentenceSplitter + Embedding

    def test_get_index_stats_no_index(self, indexer):
        """测试：索引不存在时返回错误信息"""
        stats = indexer.get_index_stats()
        # 可能返回 error 或者 document_count = 0
        assert isinstance(stats, dict)

    @pytest.mark.slow
    def test_build_small_index(self, indexer, sample_documents):
        """
        测试：构建小规模索引（需要 API Key）
        标记为 slow 因为需要调用 API
        """
        index = indexer.build_index(sample_documents)
        assert index is not None

        # 验证索引统计
        stats = indexer.get_index_stats()
        assert "document_count" in stats or "error" not in stats


if __name__ == "__main__":
    # 运行测试（跳过 slow 测试）
    pytest.main([__file__, "-v", "-m", "not slow"])
