"""
35篇文献完整性能基准测试
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from largerag import LargeRAG

def main():
    print("=" * 70)
    print("LargeRAG 性能基准测试 (35篇文献)")
    print("=" * 70)

    # 完整文献目录
    literature_dir = str(Path(__file__).parent / "data" / "literature")

    # 1. 初始化
    print("\n[步骤 1/5] 初始化 LargeRAG...")
    rag = LargeRAG()
    print("  ✓ 初始化成功")

    # 2. 构建索引（性能关键指标）
    print(f"\n[步骤 2/5] 从 {literature_dir} 构建索引...")
    print("  📊 性能目标: < 3分钟 (180秒)")

    start_time = time.time()
    success = rag.index_from_folders(literature_dir)
    index_time = time.time() - start_time

    if not success:
        print("  ✗ 索引构建失败")
        return False

    print(f"  ✓ 索引构建成功")
    print(f"  ⏱️  实际耗时: {index_time:.2f} 秒 ({index_time/60:.2f} 分钟)")

    if index_time < 180:
        print(f"  ✅ 性能达标！（目标: <180秒）")
    else:
        print(f"  ⚠️  超出目标 {index_time-180:.1f} 秒")

    # 3. 查询测试（性能关键指标）
    print("\n[步骤 3/5] 执行查询测试...")
    print("  📊 性能目标: < 10秒")

    queries = [
        "What are deep eutectic solvents?",
        "DES applications in chemistry",
        "Properties and advantages of DES"
    ]

    query_times = []
    for i, query in enumerate(queries, 1):
        print(f"\n  查询 {i}/{len(queries)}: {query}")

        start_time = time.time()
        answer = rag.query(query)
        query_time = time.time() - start_time
        query_times.append(query_time)

        print(f"    ⏱️  耗时: {query_time:.2f} 秒")
        print(f"    📝 回答: {len(answer)} 字符")

        if query_time < 10:
            print(f"    ✅ 性能达标")
        else:
            print(f"    ⚠️  超时 {query_time-10:.1f} 秒")

    avg_query_time = sum(query_times) / len(query_times)
    print(f"\n  平均查询时间: {avg_query_time:.2f} 秒")

    # 4. 相似文档检索
    print("\n[步骤 4/5] 检索相似文档...")
    docs = rag.get_similar_docs("DES synthesis and characterization", top_k=5)

    print(f"  ✓ 检索到 {len(docs)} 个相似文档")
    for i, doc in enumerate(docs, 1):
        print(f"    [{i}] score={doc['score']:.3f}")
        print(f"        doc: {doc['metadata']['doc_hash'][:12]}... page={doc['metadata']['page_idx']}")

    # 5. 统计信息和验收
    print("\n[步骤 5/5] 统计信息和验收...")
    stats = rag.get_stats()

    index_stats = stats['index_stats']
    doc_stats = stats['doc_processing_stats']

    print(f"\n  📊 索引统计:")
    print(f"    - Collection: {index_stats.get('collection_name', 'N/A')}")
    print(f"    - 索引节点数: {index_stats.get('document_count', 0)}")
    print(f"    - 存储位置: {index_stats.get('persist_directory', 'N/A')}")

    print(f"\n  📊 处理统计:")
    print(f"    - 已处理文档段落: {doc_stats.get('processed', 0)}")
    print(f"    - 已跳过: {doc_stats.get('skipped', 0)}")
    print(f"    - 总计: {doc_stats.get('total', 0)}")

    total = doc_stats.get('total', 0)
    processed = doc_stats.get('processed', 0)
    if total > 0:
        success_rate = (processed / total) * 100
        print(f"    - 成功率: {success_rate:.2f}%")

        if success_rate >= 95:
            print(f"    ✅ 成功率达标！（目标: >95%）")
        else:
            print(f"    ⚠️  成功率不足 {95-success_rate:.1f}%")

    # 最终验收报告
    print("\n" + "=" * 70)
    print("📋 验收报告")
    print("=" * 70)

    checks = []

    # 检查1: 索引耗时
    check1 = index_time < 180
    checks.append(check1)
    status1 = "✅ PASS" if check1 else "❌ FAIL"
    print(f"{status1} | 索引耗时 < 3分钟: {index_time:.1f}s / 180s")

    # 检查2: 平均查询时间
    check2 = avg_query_time < 10
    checks.append(check2)
    status2 = "✅ PASS" if check2 else "❌ FAIL"
    print(f"{status2} | 平均查询 < 10秒: {avg_query_time:.1f}s / 10s")

    # 检查3: 文档加载成功率
    check3 = success_rate >= 95
    checks.append(check3)
    status3 = "✅ PASS" if check3 else "❌ FAIL"
    print(f"{status3} | 成功率 > 95%: {success_rate:.1f}% / 95%")

    # 检查4: 索引文档数
    check4 = index_stats.get('document_count', 0) > 0
    checks.append(check4)
    status4 = "✅ PASS" if check4 else "❌ FAIL"
    print(f"{status4} | 索引文档数 > 0: {index_stats.get('document_count', 0)}")

    print("=" * 70)

    if all(checks):
        print("🎉 所有验收标准通过！")
        print("=" * 70)
        return True
    else:
        failed = sum(1 for c in checks if not c)
        print(f"⚠️  {failed}/{len(checks)} 项未通过验收")
        print("=" * 70)
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
