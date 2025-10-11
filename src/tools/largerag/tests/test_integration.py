"""
集成测试模块
端到端测试 LargeRAG 完整工作流
"""

import pytest
import sys
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from largerag import LargeRAG


class TestIntegration:
    """LargeRAG 端到端集成测试"""

    @pytest.fixture
    def literature_dir(self):
        """测试文献目录（35篇测试文献）"""
        return str(Path(__file__).parent.parent / "data" / "literature")

    @pytest.mark.integration
    def test_end_to_end_workflow(self, literature_dir):
        """
        端到端工作流测试

        测试步骤：
        1. 初始化 LargeRAG
        2. 从文件夹构建索引
        3. 执行查询
        4. 检索相似文档
        5. 验证统计信息
        """
        print("\n=== 开始端到端工作流测试 ===")

        # 1. 初始化 LargeRAG
        print("步骤 1: 初始化 LargeRAG...")
        rag = LargeRAG()
        assert rag is not None

        # 2. 构建索引（使用 35 篇测试文献）
        print(f"步骤 2: 从 {literature_dir} 构建索引...")
        start_time = time.time()
        success = rag.index_from_folders(literature_dir)
        index_time = time.time() - start_time

        assert success == True, "索引构建应该成功"
        print(f"  ✓ 索引构建成功，耗时: {index_time:.2f} 秒")

        # 性能验证：35 篇文献应在 3 分钟内完成
        assert index_time < 180, f"索引耗时应 < 3分钟，实际: {index_time:.2f}秒"

        # 3. 查询测试
        print("步骤 3: 执行查询测试...")
        query = "What are deep eutectic solvents?"

        start_time = time.time()
        answer = rag.query(query)
        query_time = time.time() - start_time

        assert isinstance(answer, str), "查询应返回字符串"
        assert len(answer) > 0, "查询回答不应为空"
        print(f"  ✓ 查询成功，耗时: {query_time:.2f} 秒")
        print(f"  回答长度: {len(answer)} 字符")

        # 性能验证：查询应在 10 秒内完成
        assert query_time < 10, f"查询耗时应 < 10秒，实际: {query_time:.2f}秒"

        # 4. 相似文档检索
        print("步骤 4: 检索相似文档...")
        docs = rag.get_similar_docs("DES properties", top_k=5)

        assert isinstance(docs, list), "应返回列表"
        assert len(docs) == 5, f"应返回 5 个文档，实际: {len(docs)}"

        # 验证文档结构
        for i, doc in enumerate(docs):
            assert "text" in doc, f"文档 {i} 应包含 text"
            assert "score" in doc, f"文档 {i} 应包含 score"
            assert "metadata" in doc, f"文档 {i} 应包含 metadata"
            assert len(doc["text"]) > 0, f"文档 {i} text 不应为空"

        print(f"  ✓ 检索到 {len(docs)} 个相似文档")

        # 5. 统计信息
        print("步骤 5: 验证统计信息...")
        stats = rag.get_stats()

        assert "index_stats" in stats
        assert "doc_processing_stats" in stats

        index_stats = stats["index_stats"]
        doc_stats = stats["doc_processing_stats"]

        print(f"  索引文档数: {index_stats.get('document_count', 0)}")
        print(f"  处理成功: {doc_stats.get('processed', 0)}")
        print(f"  跳过文档: {doc_stats.get('skipped', 0)}")

        # 验证统计数据
        assert index_stats.get("document_count", 0) > 0, "应有索引文档"
        assert doc_stats.get("processed", 0) > 0, "应有已处理文档"

        # 验证加载成功率 > 95%
        total = doc_stats.get("total", 0)
        processed = doc_stats.get("processed", 0)
        if total > 0:
            success_rate = (processed / total) * 100
            print(f"  文档加载成功率: {success_rate:.1f}%")
            assert success_rate > 95, f"成功率应 > 95%，实际: {success_rate:.1f}%"

        print("=== 端到端工作流测试完成 ===\n")

    @pytest.mark.integration
    def test_folder_structure_handling(self, literature_dir):
        """
        测试文件夹结构处理

        验证：
        1. 正确加载文献文件夹
        2. 元数据提取正确
        3. 统计信息准确
        """
        print("\n=== 文件夹结构处理测试 ===")

        from core.document_processor import DocumentProcessor

        processor = DocumentProcessor()
        documents = processor.process_from_folders(literature_dir)

        # 验证文档加载
        assert len(documents) > 0, "应该加载至少一个文档"
        print(f"  ✓ 加载了 {len(documents)} 个文档段落")

        # 验证元数据（检查前 5 个文档）
        print("  验证元数据...")
        for i, doc in enumerate(documents[:5]):
            metadata = doc.metadata
            assert "doc_hash" in metadata, f"文档 {i} 应包含 doc_hash"
            assert "page_idx" in metadata, f"文档 {i} 应包含 page_idx"
            assert "source_file" in metadata, f"文档 {i} 应包含 source_file"

            # 验证 source_file 值
            assert metadata["source_file"] in [
                "content_list_process.json",
                "article.json"
            ], f"文档 {i} source_file 无效"

        print("  ✓ 元数据验证通过")

        # 验证统计信息
        stats = processor.get_statistics()
        assert stats["processed"] > 0, "应该有已处理文档"
        assert stats["processed"] == len(documents), "统计应匹配文档数量"

        print(f"  统计信息: {stats}")
        print("=== 文件夹结构处理测试完成 ===\n")

    @pytest.mark.integration
    def test_multiple_queries(self, literature_dir):
        """
        测试多个查询

        验证：
        1. 连续查询正常工作
        2. 不同查询返回不同结果
        """
        print("\n=== 多查询测试 ===")

        rag = LargeRAG()

        # 确保有索引（可能已从前一个测试创建）
        try:
            rag.get_stats()
        except:
            print("  构建索引...")
            rag.index_from_folders(literature_dir)

        queries = [
            "What are deep eutectic solvents?",
            "DES applications in chemistry",
            "Properties of DES"
        ]

        results = []
        for i, query in enumerate(queries):
            print(f"  查询 {i+1}: {query}")
            answer = rag.query(query)
            results.append(answer)
            assert len(answer) > 0, f"查询 {i+1} 应返回非空结果"

        print(f"  ✓ 成功执行 {len(queries)} 个查询")
        print("=== 多查询测试完成 ===\n")


if __name__ == "__main__":
    # 运行集成测试
    pytest.main([__file__, "-v", "-m", "integration", "-s"])
