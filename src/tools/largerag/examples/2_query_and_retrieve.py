"""
LargeRAG 示例 2: 查询和检索
====================================

功能展示：
1. 加载已有索引
2. 执行查询（query）- LLM 生成回答
3. 检索相似文档（get_similar_docs）- 不使用 LLM
4. 查看检索细节（分数、元数据、来源）
5. 对比不同查询方式
6. 展示 Reranker 的作用

运行方式：
    python examples/2_query_and_retrieve.py

前置条件：
    需要先运行 1_build_index.py 构建索引
"""

import sys
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from largerag import LargeRAG


def print_section(title: str):
    """打印分隔线"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_subsection(title: str):
    """打印子标题"""
    print(f"\n--- {title} ---")


def main():
    print_section("LargeRAG 查询和检索示例")

    # ============================================================
    # 1. 初始化并加载已有索引
    # ============================================================
    print_section("步骤 1: 初始化 LargeRAG")

    print("\n加载已有索引...")

    start_time = time.time()
    rag = LargeRAG()
    init_time = time.time() - start_time

    if rag.query_engine is None:
        print("\n✗ 错误: 未找到索引")
        print("  请先运行: python examples/1_build_index.py")
        return False

    print(f"✓ 索引加载成功 (耗时: {init_time:.2f}秒)")

    # 显示索引信息
    stats = rag.get_stats()
    index_stats = stats['index_stats']
    print(f"\n索引信息:")
    print(f"  Collection: {index_stats.get('collection_name', 'N/A')}")
    print(f"  节点数:     {index_stats.get('document_count', 0)}")

    # ============================================================
    # 2. 方式 1: query() - 生成完整回答
    # ============================================================
    print_section("步骤 2: 使用 query() 生成回答")

    print("\nquery() 工作流程:")
    print("  [1] 向量召回    - 检索 top_k=20 个相似文档")
    print("  [2] Reranker    - 精排并选出 top_n=5 个最相关文档")
    print("  [3] LLM 生成    - 基于检索到的文档生成回答")
    print("  [4] 返回结果    - 返回 LLM 生成的文本")

    query1 = "What are deep eutectic solvents and what are their main properties?"

    print(f"\n查询: {query1}")
    print("处理中...\n")

    start_time = time.time()
    answer = rag.query(query1)
    query_time = time.time() - start_time

    print(f"回答 (耗时: {query_time:.2f}秒):")
    print("-" * 70)
    print(answer)
    print("-" * 70)

    print(f"\n回答长度: {len(answer)} 字符")

    if query_time < 10:
        print(f"✅ 查询性能达标 (目标: <10秒)")
    else:
        print(f"⚠️  查询较慢 (超时 {query_time-10:.1f}秒)")

    # ============================================================
    # 3. 方式 2: get_similar_docs() - 获取文档片段
    # ============================================================
    print_section("步骤 3: 使用 get_similar_docs() 检索文档")

    print("\nget_similar_docs() 工作流程:")
    print("  [1] 向量召回    - 检索 similarity_top_k 个相似文档")
    print("  [2] Reranker    - 精排并返回 top_k 个文档")
    print("  [3] 格式化      - 返回 [{'text': ..., 'score': ..., 'metadata': ...}]")
    print("  [4] 不使用 LLM  - 直接返回原始文档片段")

    query2 = "Applications of DES in chemistry"
    top_k = 5

    print(f"\n查询: {query2}")
    print(f"返回数量: top_k={top_k}")
    print("处理中...\n")

    start_time = time.time()
    docs = rag.get_similar_docs(query2, top_k=top_k)
    retrieve_time = time.time() - start_time

    print(f"✓ 检索完成 (耗时: {retrieve_time:.2f}秒)")
    print(f"检索到 {len(docs)} 个文档片段\n")

    # 展示每个文档的详细信息
    for i, doc in enumerate(docs, 1):
        print_subsection(f"文档 {i}/{len(docs)}")

        # 相似度分数
        score = doc['score']
        print(f"\n相似度分数: {score:.4f}")
        print("  (Reranker 精排后的分数，越高越相关)")

        # 元数据
        metadata = doc['metadata']
        print(f"\n来源信息:")
        print(f"  文档哈希: {metadata.get('doc_hash', 'N/A')[:16]}...")
        print(f"  来源文件: {metadata.get('source_file', 'N/A')}")
        print(f"  页码:     page {metadata.get('page_idx', 'N/A')}")
        print(f"  文本层级: level {metadata.get('text_level', 'N/A')}")

        if metadata.get('has_citations'):
            print(f"  引用:     ✓ 含引用")

        # 文本内容
        text = doc['text']
        print(f"\n文本内容:")
        print("-" * 60)
        # 显示前 300 字符
        if len(text) > 300:
            print(text[:300] + "...")
            print(f"[... 总长度: {len(text)} 字符]")
        else:
            print(text)
        print("-" * 60)

    # ============================================================
    # 4. 对比两种查询方式
    # ============================================================
    print_section("步骤 4: 两种查询方式对比")

    print("\n")
    print("┌─────────────────────┬─────────────────────┬─────────────────────┐")
    print("│       特性          │    query()          │ get_similar_docs()  │")
    print("├─────────────────────┼─────────────────────┼─────────────────────┤")
    print("│ 使用 LLM            │   ✓ 是              │   ✗ 否              │")
    print("│ 返回格式            │   自然语言回答      │   文档片段列表      │")
    print("│ 速度                │   较慢 (~5-10秒)    │   较快 (~2-5秒)     │")
    print("│ 返回来源信息        │   ✗ 否*             │   ✓ 是              │")
    print("│ 适用场景            │   最终用户查询      │   Agent/开发者调试  │")
    print("└─────────────────────┴─────────────────────┴─────────────────────┘")

    print("\n* 注: query() 可以配置返回来源，但当前实现只返回文本")

    # ============================================================
    # 5. 展示 Reranker 的作用
    # ============================================================
    print_section("步骤 5: Reranker 精排机制")

    print("\n检索流程详解:")
    print("  第一阶段 - 向量召回 (Vector Retrieval):")
    print("    - 使用余弦相似度快速检索")
    print("    - 召回 similarity_top_k=20 个候选文档")
    print("    - 速度快但精度有限")

    print("\n  第二阶段 - Reranker 精排 (Reranking):")
    print("    - 使用 DashScope gte-rerank 模型")
    print("    - 对 20 个候选文档重新打分")
    print("    - 返回 rerank_top_n=5 个最相关文档")
    print("    - 精度高但速度较慢")

    print("\n配置参数 (config/settings.yaml):")
    print("  retrieval:")
    print("    similarity_top_k: 20    # 向量召回数量")
    print("    rerank_top_n: 5         # Reranker 返回数量")

    print("\n  reranker:")
    print("    enabled: true           # 是否启用 Reranker")
    print("    model: gte-rerank       # Reranker 模型")

    print("\n性能影响:")
    print("  - 启用 Reranker:  精度 ↑↑, 速度 ↓")
    print("  - 禁用 Reranker:  精度 ↓,  速度 ↑↑")
    print("  (建议: 生产环境启用，开发调试可禁用)")

    # ============================================================
    # 6. 更多查询示例
    # ============================================================
    print_section("步骤 6: 更多查询示例")

    example_queries = [
        "How to synthesize deep eutectic solvents?",
        "Advantages of DES compared to traditional solvents",
        "DES viscosity and temperature relationship"
    ]

    print("\n快速测试多个查询:\n")

    for i, query in enumerate(example_queries, 1):
        print(f"{i}. {query}")

        start_time = time.time()
        answer = rag.query(query)
        query_time = time.time() - start_time

        # 只显示回答的前100字符
        answer_preview = answer[:100] + "..." if len(answer) > 100 else answer
        print(f"   回答: {answer_preview}")
        print(f"   耗时: {query_time:.2f}秒\n")

    # ============================================================
    # 7. 统计信息总结
    # ============================================================
    print_section("步骤 7: 统计信息总结")

    stats = rag.get_stats()

    print("\n📊 系统统计:")
    print(f"  索引节点数:     {stats['index_stats'].get('document_count', 0)}")
    print(f"  处理文档数:     {stats['doc_processing_stats'].get('processed', 0)}")
    print(f"  向量存储:       Chroma (持久化)")
    print(f"  缓存系统:       本地文件缓存")

    print("\n⏱️  性能参考:")
    print(f"  查询延迟:       ~{query_time:.1f}秒 (目标: <10秒)")
    print(f"  检索延迟:       ~{retrieve_time:.1f}秒 (不使用LLM)")

    # ============================================================
    # 8. 使用建议
    # ============================================================
    print_section("使用建议")

    print("\n💡 选择查询方式:")
    print("  - 需要自然语言回答 → 使用 query()")
    print("  - 需要原始文档片段 → 使用 get_similar_docs()")
    print("  - 需要来源信息     → 使用 get_similar_docs()")

    print("\n💡 性能优化:")
    print("  - 调整 similarity_top_k 可以平衡精度和速度")
    print("  - 调整 rerank_top_n 控制返回文档数量")
    print("  - 禁用 Reranker 可以显著提速（精度下降）")

    print("\n💡 Agent 集成:")
    print("  - Agent 应该调用 get_similar_docs() 获取文档")
    print("  - Agent 自己整合多个工具的结果")
    print("  - Agent 根据来源信息（doc_hash, page_idx）追溯文献")

    print("\n💡 调试技巧:")
    print("  - 查看 get_similar_docs() 的分数判断检索质量")
    print("  - 检查元数据中的 doc_hash 确认来源文献")
    print("  - 对比不同查询的 score 分布调整检索参数")

    # ============================================================
    # 完成
    # ============================================================
    print_section("完成！")

    print("\n✅ 已展示 LargeRAG 所有功能:")
    print("  ✓ query() - LLM 生成回答")
    print("  ✓ get_similar_docs() - 检索文档片段")
    print("  ✓ get_stats() - 统计信息")
    print("  ✓ 元数据和来源信息")
    print("  ✓ Reranker 精排机制")
    print("  ✓ 性能指标展示")

    print("\n下一步:")
    print("  - 查看配置文件: config/settings.yaml")
    print("  - 查看缓存说明: docs/cache_guide.md")
    print("  - 集成到 Agent: 使用 get_similar_docs() 获取文档")

    print("\n" + "=" * 70 + "\n")

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
