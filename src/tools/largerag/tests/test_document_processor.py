"""
文档处理器单元测试
"""

import pytest
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.document_processor import DocumentProcessor


class TestDocumentProcessor:
    """DocumentProcessor 单元测试"""

    @pytest.fixture
    def processor(self):
        """创建 DocumentProcessor 实例"""
        return DocumentProcessor()

    @pytest.fixture
    def test_literature_dir(self):
        """测试数据目录"""
        return str(Path(__file__).parent.parent / "data" / "literature")

    def test_process_from_folders_success(self, processor, test_literature_dir):
        """测试：成功从文件夹加载文档"""
        documents = processor.process_from_folders(test_literature_dir)

        # 验证加载了文档
        assert len(documents) > 0, "应该加载至少一个文档"

        # 验证 Document 对象结构
        first_doc = documents[0]
        assert hasattr(first_doc, 'text'), "Document 应该有 text 属性"
        assert hasattr(first_doc, 'metadata'), "Document 应该有 metadata 属性"
        assert len(first_doc.text) > 0, "Document text 不应为空"

    def test_document_metadata(self, processor, test_literature_dir):
        """测试：元数据正确提取"""
        documents = processor.process_from_folders(test_literature_dir)

        # 检查前 5 个文档的元数据
        for doc in documents[:5]:
            metadata = doc.metadata
            assert "doc_hash" in metadata, "应包含 doc_hash"
            assert "page_idx" in metadata, "应包含 page_idx"
            assert "source_file" in metadata, "应包含 source_file"

            # 验证 source_file 值
            assert metadata["source_file"] in [
                "content_list_process.json",
                "article.json"
            ], f"source_file 应该是有效值，实际为: {metadata['source_file']}"

    def test_statistics(self, processor, test_literature_dir):
        """测试：统计信息正确"""
        documents = processor.process_from_folders(test_literature_dir)
        stats = processor.get_statistics()

        assert "processed" in stats
        assert "skipped" in stats
        assert "total" in stats

        # 验证统计数值
        assert stats["processed"] > 0, "应该处理了一些文档"
        assert stats["processed"] == len(documents), "processed 应该等于文档数量"
        assert stats["total"] >= stats["processed"], "total 应该 >= processed"

    def test_nonexistent_directory(self, processor):
        """测试：目录不存在时抛出异常"""
        with pytest.raises(FileNotFoundError):
            processor.process_from_folders("/nonexistent/path")

    def test_text_only_extraction(self, processor, test_literature_dir):
        """测试：只提取 text 类型（忽略 image, table 等）"""
        documents = processor.process_from_folders(test_literature_dir)

        # 所有文档都应该有非空文本
        for doc in documents[:10]:
            assert isinstance(doc.text, str), "text 应该是字符串"
            assert len(doc.text.strip()) > 0, "text 不应为空字符串"


if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v"])
