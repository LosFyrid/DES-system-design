"""
5篇文献快速测试
用于验证完整工作流
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from largerag import LargeRAG

def main():
    print("=" * 60)
    print("LargeRAG 快速测试 (5篇文献)")
    print("=" * 60)

    # 测试文献目录
    literature_dir = str(Path(__file__).parent / "data" / "test_5papers")

    # 1. 初始化
    print("\n[步骤 1/5] 初始化 LargeRAG...")
    rag = LargeRAG()
    print("  ✓ 初始化成功")

    # 2. 构建索引
    print(f"\n[步骤 2/5] 从 {literature_dir} 构建索引...")
    start_time = time.time()
    success = rag.index_from_folders(literature_dir)
    index_time = time.time() - start_time

    if not success:
        print("  ✗ 索引构建失败")
        return False

    print(f"  ✓ 索引构建成功")
    print(f"  ⏱️  耗时: {index_time:.2f} 秒")

    # 3. 查询测试
    print("\n[步骤 3/5] 执行查询测试...")
    query = "What are deep eutectic solvents?"
    print(f"  查询: {query}")

    start_time = time.time()
    answer = rag.query(query)
    query_time = time.time() - start_time

    print(f"  ✓ 查询成功")
    print(f"  ⏱️  耗时: {query_time:.2f} 秒")
    print(f"  📝 回答长度: {len(answer)} 字符")
    print(f"  📄 回答预览: {answer[:200]}...")

    # 4. 相似文档检索
    print("\n[步骤 4/5] 检索相似文档...")
    docs = rag.get_similar_docs("DES properties and applications", top_k=3)

    print(f"  ✓ 检索到 {len(docs)} 个相似文档")
    for i, doc in enumerate(docs, 1):
        print(f"    [{i}] score={doc['score']:.3f}, doc_hash={doc['metadata']['doc_hash'][:8]}...")
        print(f"        {doc['text'][:100]}...")

    # 5. 统计信息
    print("\n[步骤 5/5] 获取统计信息...")
    stats = rag.get_stats()

    print(f"  索引统计:")
    print(f"    - Collection: {stats['index_stats'].get('collection_name', 'N/A')}")
    print(f"    - 文档数: {stats['index_stats'].get('document_count', 0)}")

    print(f"  处理统计:")
    print(f"    - 已处理: {stats['doc_processing_stats'].get('processed', 0)}")
    print(f"    - 已跳过: {stats['doc_processing_stats'].get('skipped', 0)}")

    total = stats['doc_processing_stats'].get('total', 0)
    processed = stats['doc_processing_stats'].get('processed', 0)
    if total > 0:
        success_rate = (processed / total) * 100
        print(f"    - 成功率: {success_rate:.1f}%")

    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)

    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
